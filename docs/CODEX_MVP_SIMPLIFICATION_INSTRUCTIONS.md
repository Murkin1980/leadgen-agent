# Codex Instructions — Safe MVP Simplification

## Цель

Упростить текущий `leadgen-agent` в этом же репозитории. Не создавать второй репозиторий и не переписывать проект с нуля.

Главный принцип:

> Сначала сократить количество одновременно работающих сервисов и активных сценариев. Удалять код только после подтверждения, что упрощённый MVP полностью работает.

Итоговый MVP должен выполнять только один бизнес-сценарий:

1. импортировать или вручную добавить компании;
2. отфильтровать компании без нормального сайта;
3. сгенерировать простой лендинг;
4. показать лендинг администратору;
5. после ручного одобрения опубликовать его;
6. создать одно WhatsApp-сообщение;
7. после ручного одобрения отправить его в sandbox;
8. сохранить простой статус лида и ответ.

---

## 1. Не удалять всё сразу

Сделать упрощение в два прохода.

### Проход A — отключение без удаления

Сначала сохранить существующие модули и миграции, но исключить лишние сервисы из стандартного запуска.

### Проход B — физическое удаление

Удалять файлы только после того, как упрощённый режим прошёл тесты и был проверен вручную.

Миграции `001–006` не удалять и не переписывать. История базы должна оставаться последовательной.

---

## 2. Целевая архитектура MVP

В стандартном `docker compose up` оставить только:

1. `postgres`;
2. `redis`;
3. `migrate`;
4. `api`;
5. `worker` — один RQ worker, слушающий все нужные MVP-очереди;
6. `preview` — Nginx для просмотра опубликованных лендингов.

Итого: 6 сервисов вместо текущих 12.

Универсальный worker должен слушать:

```text
collect enrich generate_content publish outreach_generate outreach_send
```

Команда может выглядеть так:

```yaml
command:
  [
    "python",
    "-m",
    "rq",
    "worker",
    "--url",
    "redis://redis:6379/0",
    "collect",
    "enrich",
    "generate_content",
    "publish",
    "outreach_generate",
    "outreach_send"
  ]
```

Очереди `generate`, `deploy`, `outreach_status` в стандартном MVP не запускать.

---

## 3. Что оставить обязательно

### Инфраструктура

- PostgreSQL;
- Redis;
- Alembic migrations;
- FastAPI;
- один RQ worker;
- Nginx preview;
- один обычный `Dockerfile`.

### Сбор лидов

Оставить:

- `CsvCollectorAdapter`;
- ручное создание/импорт лида;
- `MockCollectorAdapter` для тестов.

`TwoGisCollectorAdapter` оставить в коде, но отключить по умолчанию. Не развивать его до появления рабочего API-ключа и подтверждённой необходимости.

### Генерация контента

Оставить:

- `template` provider как стандартный;
- `mock` provider для тестов;
- текущую JSON-схему лендинга;
- рендеринг HTML;
- ручное редактирование;
- ручное approve.

OpenAI provider оставить в коде, но не использовать по умолчанию.

### Публикация

Оставить:

- локальную публикацию в `sites/public`;
- preview через Nginx;
- ручной approve перед публикацией.

Cloudflare deployment не должен быть частью стандартного MVP-запуска.

### Outreach

Оставить только:

- WhatsApp;
- mock provider;
- WhatsApp sandbox provider;
- ручное approve сообщения;
- DNC;
- sandbox allowlist;
- входящий webhook;
- простой статус `sent/delivered/read/replied/failed`;
- consent/contact basis в минимальном виде.

---

## 4. Что отключить через Docker Compose profiles

Не удалять код сразу. Перенести следующие сервисы в профиль `advanced`:

- отдельный `collector`;
- отдельный `enricher`;
- legacy `generator`;
- отдельный `content-generator`;
- отдельный `publisher`;
- `deployer`;
- отдельный `outreach-generator`;
- отдельный `outreach-sender`;
- `outreach-status`.

Стандартный запуск:

```bash
docker compose up --build
```

Должен запускать только упрощённый MVP.

Расширенный режим для диагностики старой архитектуры:

```bash
docker compose --profile advanced up --build
```

Не допускать одновременного запуска универсального worker и отдельных workers, слушающих те же очереди, если это создаёт дублирование обработки.

---

## 5. Что можно удалить после проверки упрощённого режима

Физическое удаление разрешено только во втором коммите после успешных тестов.

### Можно удалить

1. Legacy pipeline генерации, если он полностью заменён `generate_content`:
   - `app/workers/generator_worker.py`;
   - старый endpoint `/leads/{id}/generate`;
   - legacy queue `generate`;
   - старые generation-классы, которые нигде не используются.

2. Отдельный deployer runtime, если Cloudflare не используется в MVP:
   - `Dockerfile.deployer`;
   - сервис `deployer` из стандартного compose;
   - scripts, которые дублируют публикацию;
   - queue `deploy`.

   При этом модели Deployment и миграции пока оставить, чтобы не ломать существующую БД.

3. Email outreach stub, если он нигде не используется:
   - `app/outreach/email_provider.py`;
   - email env-переменные;
   - email webhook route;
   - email provider option из UI/API.

4. Telegram outreach stub, если он нигде не используется:
   - `app/outreach/telegram_provider.py`;
   - Telegram env-переменные;
   - Telegram webhook route;
   - Telegram provider option из UI/API.

5. Автоматический status polling worker, если WhatsApp delivery statuses уже приходят через webhook:
   - `app/workers/outreach_status_worker.py`;
   - queue `outreach_status`;
   - polling-specific settings.

6. Незавершённые Phase 07 enterprise-заготовки, если они не подключены к MVP:
   - Prometheus;
   - API keys/scopes;
   - pilot framework;
   - сложный DLQ UI;
   - backup service внутри приложения;
   - retention engine;
   - advanced readiness worker topology.

   Простые эксплуатационные скрипты backup можно хранить отдельно в `scripts/`, но не включать их в runtime приложения.

### Пока не удалять

- таблицы и модели, уже присутствующие в миграциях;
- Alembic revisions;
- базовые audit logs;
- DNC;
- consent fields;
- inbound messages;
- WhatsApp templates;
- landing versions;
- review status;
- webhook signature validation;
- phone normalization;
- retry limit для единичной отправки.

---

## 6. Упростить пользовательский интерфейс

Главная админ-панель должна содержать только пять разделов:

1. **Лиды**;
2. **Лендинги на проверке**;
3. **Сообщения на одобрение**;
4. **Входящие ответы**;
5. **Настройки MVP**.

Скрыть из основной навигации:

- deployment dashboard;
- сложную историю генераций;
- API usage dashboard;
- расширенные security pages;
- dead-letter dashboard;
- campaign analytics;
- provider diagnostics.

Данные не удалять. Достаточно убрать ссылки из стандартного интерфейса.

---

## 7. Упростить CRM

Оставить только стадии:

```text
new
landing_ready
message_approved
contacted
replied
interested
won
lost
do_not_contact
```

Не удалять старые enum-значения из базы немедленно. Добавить слой отображения, который сводит старые стадии к этим восьми рабочим стадиям.

Не строить сложные автоматические переходы. Все важные переходы делает оператор вручную, кроме:

- успешная отправка → `contacted`;
- входящий ответ → `replied`;
- DNC → `do_not_contact`.

---

## 8. Упростить настройки

Создать отдельный `.env.mvp.example`.

В нём оставить только необходимые переменные:

```env
APP_ENV=development
DATABASE_URL=postgresql+psycopg://leadgen:leadgen@postgres:5432/leadgen
REDIS_URL=redis://redis:6379/0

COLLECTOR_PROVIDER=csv
CSV_FILE_PATH=import/companies.csv

TEXT_GENERATOR_PROVIDER=template
DEFAULT_LANGUAGE=ru

PUBLIC_BASE_URL=http://localhost:8080

ADMIN_USERNAME=admin
ADMIN_PASSWORD=change-me

OUTREACH_PROVIDER=mock
OUTREACH_ENABLED=false
OUTREACH_MODE=disabled
OUTREACH_SANDBOX_ALLOWLIST=
OUTREACH_TIMEZONE=Asia/Almaty

WHATSAPP_CLOUD_API_TOKEN=
WHATSAPP_CLOUD_PHONE_NUMBER_ID=
WHATSAPP_WEBHOOK_VERIFY_TOKEN=
WHATSAPP_APP_SECRET=
```

Остальные настройки оставить в `.env.production.example` или advanced documentation, но не показывать новичку в MVP quick start.

---

## 9. Упростить API

Основные MVP endpoints:

```text
GET  /health
POST /jobs
GET  /jobs/{id}
GET  /leads
GET  /leads/{id}
POST /leads/{id}/content-generations
GET  /landings
GET  /landings/{id}
POST /landings/{id}/approve
POST /landings/{id}/publish
GET  /outreach-messages
POST /outreach-messages/{id}/approve
POST /outreach-messages/{id}/send
GET  /inbound-messages
POST /webhooks/whatsapp
```

Все остальные endpoints не обязательно удалять. Пометить их тегом `advanced` и скрыть из основного README.

---

## 10. Тесты упрощённого режима

Добавить отдельный файл:

```text
tests/test_mvp_flow.py
```

Он должен проверять один полный сценарий:

1. создать/импортировать лид;
2. создать лендинг через template provider;
3. статус лендинга `needs_review`;
4. approve;
5. publish;
6. создать outreach message;
7. approve;
8. отправить через mock provider;
9. получить mock inbound reply;
10. проверить, что lead стал `replied`.

Добавить `scripts/mvp_smoke_test.sh`, который запускает этот же сценарий через HTTP в Docker.

Критерий успеха — один работающий end-to-end сценарий, а не максимальное число сервисов.

---

## 11. Порядок реализации

### Коммит 1 — безопасное отключение

- добавить универсальный `worker`;
- перевести отдельные workers в profile `advanced`;
- добавить `.env.mvp.example`;
- упростить README;
- добавить MVP smoke test;
- ничего физически не удалять.

Сообщение коммита:

```text
refactor(mvp): simplify default runtime without deleting features
```

### Проверка после коммита 1

Запустить:

```bash
python -m compileall app -q
pytest tests/ -v
docker compose config
docker compose up --build -d
bash scripts/mvp_smoke_test.sh
docker compose down -v
```

### Коммит 2 — удаление очевидного legacy

Только после успешной проверки:

- удалить legacy generator;
- удалить неиспользуемые Email/Telegram stubs;
- удалить status polling worker;
- удалить deployer runtime из стандартной поставки;
- удалить неиспользуемые env-переменные из `.env.mvp.example`;
- удалить мёртвые импорты и тесты.

Сообщение коммита:

```text
refactor(mvp): remove verified unused runtime components
```

---

## 12. Запреты

- не создавать новый репозиторий;
- не создавать отдельную версию приложения копированием папок;
- не удалять миграции;
- не менять существующие primary keys;
- не удалять данные пользователя;
- не включать production outreach;
- не включать автоматическую массовую рассылку;
- не подключать новые инфраструктурные сервисы;
- не добавлять Kubernetes, Celery, Kafka, Prometheus или отдельную CRM;
- не переписывать backend на другой framework;
- не усложнять frontend.

---

## 13. Итоговый отчёт

Создать:

```text
docs/MVP_SIMPLIFICATION_REPORT.md
```

В отчёте указать:

- сервисы до и после;
- какие сервисы отключены;
- какие файлы удалены;
- какие модули сохранены, но скрыты;
- какие endpoints считаются основными;
- результат полного MVP smoke test;
- количество тестов;
- известные ограничения;
- точную команду запуска MVP.

Главный результат:

```bash
docker compose up --build
```

должен поднимать понятный и рабочий MVP без ручного запуска десяти отдельных workers.
