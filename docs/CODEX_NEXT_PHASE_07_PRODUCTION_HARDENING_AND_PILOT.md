# Codex Next Phase 07 — Production Hardening, Pilot Rollout and Operations

## Цель этапа

Подготовить Leadgen Agent к безопасному ограниченному production-пилоту: устранить оставшиеся блокирующие дефекты Phase 06, подтвердить миграции и CI, усилить безопасность, наблюдаемость, резервное копирование и провести sandbox-проверку полного цикла без массовой отправки.

Массовая отправка по умолчанию должна оставаться отключенной.

---

## 1. Обязательные исправления перед продолжением

### 1.1. Исправить CSRF parsing в Admin UI

В текущей реализации нельзя использовать:

```python
request.form.get("csrf_token")
```

`request.form` является методом/асинхронным API.

Предпочтительный вариант:

- передавать `csrf_token: str = Form(...)` непосредственно в изменяющие endpoint;
- затем вызывать `validate_csrf_token(csrf_token)`;
- либо перевести endpoint в `async def` и использовать `form = await request.form()`.

Покрыть тестами:

- правильный CSRF token разрешает действие;
- отсутствующий token возвращает 403;
- неверный token возвращает 403;
- approve/reject landing;
- approve/reject outreach message;
- DNC и consent admin actions;
- template management actions.

### 1.2. Проверить политику invalid WhatsApp webhook signature

Текущий обработчик возвращает HTTP 200 при неверной подписи. Это допустимо только как осознанная защита от повторных доставок, но событие не должно обрабатываться.

Требования:

- `processed=false`;
- не создавать `InboundMessage`;
- не создавать `OutreachEvent`;
- не менять Lead;
- увеличивать метрику `webhook_invalid_signature_total`;
- писать audit/security log без payload и номера телефона;
- поведение должно быть явно описано в `WEBHOOK_SECURITY.md`.

### 1.3. Проверить HMAC реализацию

Использовать единый helper:

```python
hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
```

или эквивалентный корректный вызов.

Не дублировать реализацию в `security.py` и `whatsapp_routes.py`. Создать один модуль, например:

```text
app/security/webhook_signature.py
```

Покрыть official-style test vectors.

### 1.4. Исправить типы моделей

Проверить модели на несоответствия аннотаций и колонок, например:

- `OutreachEvent.id` сейчас аннотирован как `int`, но хранится в `String(50)`;
- даты в `Lead` не должны быть аннотированы как `str`;
- все UUID/string IDs должны иметь `Mapped[str]`;
- все datetime поля должны иметь `Mapped[datetime]` или `Mapped[datetime | None]`.

Добавить mypy/pyright-compatible проверку или минимум SQLAlchemy mapper test.

---

## 2. CI как обязательный источник истины

Обновить GitHub Actions.

Jobs:

1. `lint`
   - Ruff;
   - compileall;
   - проверка миграций на несколько heads.

2. `unit-tests`
   - SQLite/mock providers;
   - coverage threshold не ниже 80% для Phase 06 модулей.

3. `postgres-tests`
   - PostgreSQL service container;
   - `alembic upgrade head`;
   - запуск ключевых integration tests.

4. `docker-smoke`
   - `docker compose build`;
   - полный mock pipeline;
   - WhatsApp sandbox webhook simulation;
   - teardown всегда.

5. `security`
   - `pip-audit`;
   - secret scan;
   - Bandit для Python;
   - npm audit для Wrangler dependencies без автоматического изменения lockfile.

Branch protection для `master` должна требовать успешные jobs.

---

## 3. Проверка миграций 001–006

Добавить тест миграционной цепочки:

```text
empty database
→ upgrade 001
→ upgrade 002
→ ...
→ upgrade 006
→ downgrade 005
→ upgrade 006
```

Проверить:

- отсутствие нескольких Alembic heads;
- наличие всех индексов;
- уникальность `provider_message_id` там, где требуется;
- уникальность webhook event key;
- внешние ключи;
- nullable/default значения для старых данных.

Добавить команду:

```bash
scripts/check_migrations.sh
```

---

## 4. Production readiness endpoint

Добавить:

```http
GET /readiness
```

Он должен возвращать структурированный результат:

```json
{
  "ready": false,
  "checks": {
    "postgres": "ok",
    "redis": "ok",
    "migrations": "ok",
    "workers": "ok",
    "outreach_mode": "disabled",
    "whatsapp_config": "missing",
    "webhook_security": "ok",
    "admin_security": "ok"
  }
}
```

Правила:

- `/health` остается простым liveness;
- `/readiness` не вызывает Meta API;
- секреты никогда не возвращаются;
- production readiness `true` только при корректной конфигурации;
- `OUTREACH_MODE=production` при отсутствующих secrets должен считаться ошибкой.

---

## 5. Worker heartbeat и queue monitoring

Добавить модель или Redis heartbeat для workers:

- worker name;
- queue;
- last_seen_at;
- current_job_id;
- status;
- version/commit SHA.

Добавить API:

```http
GET /workers
GET /queues
```

Показывать:

- количество queued/started/failed/dead-letter;
- oldest job age;
- worker heartbeat age;
- stuck jobs;
- retry backlog.

Добавить admin page:

```text
/admin/operations
```

---

## 6. Dead-letter management

Реализовать полноценный DLQ workflow:

```http
GET  /outreach/dead-letter
POST /outreach/dead-letter/{message_id}/requeue
POST /outreach/dead-letter/{message_id}/cancel
```

Требования:

- только retryable failures можно requeue;
- requeue требует ручного admin action;
- повторно проверить DNC, consent, quiet hours, sandbox и template status;
- сбросить только retry-related поля;
- сохранить полный audit trail;
- запретить бесконечное requeue.

---

## 7. WhatsApp template sync hardening

Реализовать реальную синхронизацию templates с Meta API.

Требования:

- pagination;
- timeout/retry;
- не удалять локальные записи автоматически;
- обновлять provider status;
- различать `approved`, `pending`, `rejected`, `paused`, `disabled`;
- хранить `last_synced_at`;
- сохранять безопасную provider metadata;
- production sender использует только свежо синхронизированный approved template;
- configurable max staleness, например 24 часа.

Добавить:

```env
WHATSAPP_TEMPLATE_MAX_STALENESS_HOURS=24
```

---

## 8. Conversation inbox для оператора

Доработать admin inbox:

```text
/admin/inbox
/admin/inbox/{lead_id}
```

Функции:

- список новых входящих;
- unread/handled;
- conversation timeline;
- masked phone;
- lead profile и landing preview;
- service window countdown;
- approved templates;
- отправка free-form только внутри service window;
- отправка template вне окна;
- mark handled;
- assign operator;
- notes;
- DNC;
- consent update.

Не добавлять автоматический AI-ответ.

---

## 9. Database backup and restore

Добавить scripts:

```text
scripts/backup_postgres.sh
scripts/restore_postgres.sh
scripts/verify_backup.sh
```

Требования:

- timestamped compressed backup;
- retention setting;
- checksum;
- restore только с явным подтверждением;
- исключить secrets;
- документировать volume/site backup отдельно;
- еженедельный restore drill в staging.

Переменные:

```env
BACKUP_DIR=/backups
BACKUP_RETENTION_DAYS=14
```

---

## 10. Data retention and privacy operations

Добавить policy и команды:

- удалить/анонимизировать lead;
- экспортировать данные lead;
- удалить message body после retention срока при необходимости;
- сохранить DNC hash/marker, чтобы контакт не импортировался повторно;
- не удалять audit/security events раньше установленного срока.

API только для admin:

```http
GET    /leads/{id}/data-export
DELETE /leads/{id}/personal-data
```

Добавить `docs/DATA_RETENTION_POLICY.md`.

---

## 11. Observability

Добавить Prometheus-compatible endpoint:

```http
GET /metrics/prometheus
```

Метрики:

- jobs by status/provider;
- queue length;
- worker heartbeat;
- landing generation duration;
- deployment duration;
- outreach sent/delivered/read/replied/failed;
- retry count;
- DLQ size;
- webhook invalid signatures;
- duplicate webhook events;
- sandbox/consent/DNC/quiet-hour blocks;
- Meta API latency and error codes;
- OpenAI usage/cost.

Не использовать company names, phone numbers или lead IDs как metric labels.

---

## 12. Rate limiting and API authentication

Admin UI basic auth недостаточно для public production API.

Добавить:

- API key authentication для admin API;
- hashed API keys в БД;
- scopes: `read`, `review`, `outreach`, `admin`;
- key rotation;
- `last_used_at`;
- revoke;
- rate limit через Redis;
- separate webhook endpoints without API key, но с signature verification.

Не хранить raw API key после создания.

---

## 13. Pilot rollout workflow

Создать `docs/PILOT_ROLLOUT_CHECKLIST.md`.

### Stage A — local mock

- all tests pass;
- migrations pass;
- mock outreach only;
- no external calls.

### Stage B — staging sandbox

- отдельная PostgreSQL база;
- `OUTREACH_MODE=sandbox`;
- allowlist максимум 3 тестовых номера;
- одно approved template message;
- webhook delivered/read simulation;
- реальный inbound reply;
- verify service window.

### Stage C — limited production pilot

- максимум 5 вручную проверенных B2B leads;
- documented contact basis;
- все сообщения approved вручную;
- не больше 1 первого сообщения на lead;
- follow-up отключен;
- daily manual review of failures/replies;
- emergency kill switch tested.

### Stage D — review

До расширения пилота собрать:

- delivery rate;
- reply rate;
- opt-out rate;
- error rate;
- complaints;
- operator workload;
- cost.

Никакого автоматического перехода к массовой отправке.

---

## 14. Tests

Добавить тесты минимум для:

- CSRF form parsing;
- HMAC valid/invalid/missing signature;
- invalid signature causes zero DB changes;
- webhook duplicate idempotency;
- migration 001–006 chain;
- model mapper types;
- readiness states;
- worker heartbeat;
- DLQ requeue rules;
- template staleness;
- service window boundary;
- sandbox allowlist;
- production consent policy;
- backup script dry-run;
- data export/anonymization;
- API key scopes and rotation;
- Prometheus metrics do not leak PII.

Все тесты должны использовать mock Meta API.

---

## 15. Definition of Done

Этап завершен, если:

1. Исправлен CSRF parsing bug.
2. Подпись webhook проверяется единым helper и покрыта тестами.
3. Invalid webhook не меняет данные.
4. Миграции 001–006 проверяются автоматически.
5. CI реально проходит и является required check.
6. `/readiness` отражает production readiness.
7. Есть worker/queue monitoring и DLQ management.
8. Template sync работает через mock integration test.
9. Admin inbox поддерживает ручную работу оператора.
10. Backup/restore документирован и проверен.
11. Есть privacy/data-retention операции.
12. API защищен ключами и rate limits.
13. Pilot rollout checklist готов.
14. Массовая отправка остается отключенной.
15. README и production runbooks обновлены.

После выполнения предоставить:

- список измененных файлов;
- результаты unit/integration/smoke tests;
- migration check output;
- CI run URL;
- readiness sample;
- pilot checklist;
- перечень оставшихся рисков.
