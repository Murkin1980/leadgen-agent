# Codex Next Phase 06 — WhatsApp Cloud API and Production Operations

## Цель этапа

Подключить настоящий WhatsApp Cloud API к существующей outreach-архитектуре, сохранить обязательное ручное одобрение сообщений, добавить надежную обработку webhook, production-настройки, наблюдаемость и безопасный режим запуска.

Этап считается успешным, если система может отправить одно вручную одобренное тестовое сообщение через WhatsApp Cloud API, получить статусы доставки через webhook и корректно обновить CRM, при этом массовая отправка по умолчанию остается отключенной.

---

## 1. Сначала провести аудит Phase 05

Перед изменениями проверить:

- миграции `001`–`005` применяются последовательно;
- `OUTREACH_ENABLED=false` по умолчанию;
- без ручного approve сообщение нельзя поставить в отправку;
- `do_not_contact=true` блокирует генерацию follow-up и отправку;
- тихие часы считаются в `Asia/Almaty`;
- один и тот же webhook event не применяется дважды;
- CSRF включен для всех изменяющих admin-форм;
- API-токены и полные номера телефонов не попадают в логи.

Найденные проблемы исправить до подключения реального провайдера.

---

## 2. Реальный WhatsAppCloudProvider

Заменить stub в `app/outreach/whatsapp_provider.py` на полноценную реализацию.

Использовать официальный Graph API Meta.

Поддержать:

- отправку template message;
- отправку free-form text только внутри разрешенного customer-care window;
- получение `provider_message_id`;
- обработку HTTP 4xx/5xx;
- таймауты;
- retry только для временных ошибок;
- idempotency на уровне `OutreachMessage`;
- сохранение безопасного фрагмента ответа без секретов.

Интерфейс результата:

```python
@dataclass
class OutreachSendResult:
    success: bool
    provider_message_id: str | None
    provider_status: str | None
    error_code: str | None
    error_message: str | None
    retryable: bool
    raw_metadata: dict[str, Any]
```

Не сохранять access token в базе данных.

---

## 3. WhatsApp template messages

Добавить модель `WhatsAppTemplate`:

- `id`;
- `name`;
- `language_code`;
- `category`;
- `status`;
- `body_template`;
- `header_type`;
- `footer_text`;
- `button_schema_json`;
- `provider_template_id`;
- `created_at`;
- `updated_at`.

Статусы:

- `draft`;
- `pending`;
- `approved`;
- `rejected`;
- `disabled`.

Добавить API:

```http
GET  /whatsapp/templates
POST /whatsapp/templates
GET  /whatsapp/templates/{id}
PUT  /whatsapp/templates/{id}
POST /whatsapp/templates/sync
```

Для production-отправки первого контакта использовать только шаблон со статусом `approved`.

Не реализовывать автоматическую отправку свободного текста незнакомому контакту.

---

## 4. Нормализация и защита телефонных номеров

Создать единый сервис `PhoneNumberService`.

Требования:

- поддержка Казахстана `+7`;
- хранение в E.164;
- отделение отображаемого номера от нормализованного;
- маскирование в логах;
- отклонение коротких, служебных и явно некорректных номеров;
- запрет отправки на номер без успешной нормализации;
- тесты для `8 707`, `+7 707`, `7707`, пробелов, скобок и дефисов.

В логах показывать, например:

```text
+7******1234
```

---

## 5. Webhook verification и подпись

Реализовать официальный verification flow:

```http
GET /webhooks/whatsapp
```

Проверять:

- `hub.mode`;
- `hub.verify_token`;
- возвращать `hub.challenge` только при совпадении токена.

Для POST webhook:

```http
POST /webhooks/whatsapp
```

Проверять подпись `X-Hub-Signature-256` через app secret.

Добавить переменную:

```env
WHATSAPP_APP_SECRET=
```

Требования:

- constant-time comparison;
- отклонять неподписанные production-запросы;
- в development разрешать mock webhook только при явном флаге;
- сохранять уникальный event key;
- повторный webhook должен возвращать 200, но не менять данные повторно.

---

## 6. Обработка входящих сообщений

Добавить модель `InboundMessage`:

- `id`;
- `provider`;
- `provider_message_id`;
- `lead_id`;
- `from_phone`;
- `message_type`;
- `text_body`;
- `media_id`;
- `raw_metadata_json`;
- `received_at`;
- `processed_at`;
- `status`.

При входящем сообщении:

1. найти Lead по нормализованному номеру;
2. создать `InboundMessage`;
3. создать `OutreachEvent` типа `replied`;
4. перевести Lead в стадию `replied`, если переход допустим;
5. остановить все ожидающие follow-up для этого Lead;
6. показать входящее сообщение в admin UI.

Не добавлять автоматический AI-ответ на этом этапе.

---

## 7. Customer-care window

Добавить поля к Lead или отдельной модели conversation:

- `last_inbound_at`;
- `service_window_expires_at`;
- `last_outbound_at`.

Правило:

- free-form outbound разрешен только пока service window активно;
- вне окна разрешены только approved template messages;
- проверка должна находиться в domain service, а не только в UI;
- попытка нарушить правило возвращает понятную ошибку и записывается в audit log.

Точную длительность окна вынести в конфигурацию:

```env
WHATSAPP_SERVICE_WINDOW_HOURS=24
```

---

## 8. Очередь отправки и retry policy

Доработать `outreach_sender_worker`.

Добавить:

- job timeout;
- exponential backoff;
- jitter;
- максимум повторов;
- dead-letter queue;
- поле `next_retry_at`;
- поле `attempt_count`;
- сохранение последней безопасной ошибки;
- блокировку параллельной отправки одного сообщения.

Переменные:

```env
OUTREACH_SEND_MAX_RETRIES=5
OUTREACH_SEND_RETRY_BASE_SECONDS=30
OUTREACH_SEND_JOB_TIMEOUT_SECONDS=60
```

Не повторять:

- ошибки авторизации;
- неподтвержденный template;
- неверный номер;
- DNC;
- permanent policy error.

Повторять:

- timeout;
- temporary network error;
- HTTP 429;
- временные 5xx.

---

## 9. Consent и законность контакта

Добавить к Lead:

- `contact_basis`;
- `consent_status`;
- `consent_source`;
- `consent_recorded_at`;
- `consent_notes`.

Статусы consent:

- `unknown`;
- `legitimate_interest_reviewed`;
- `consented`;
- `withdrawn`;
- `blocked`.

Production-отправка должна требовать явно допустимый статус, задаваемый политикой.

Добавить `docs/CONSENT_AND_CONTACT_POLICY.md` с описанием:

- какие источники данных допустимы;
- когда можно отправлять первое сообщение;
- как обрабатывается отказ;
- как удалить контакт;
- как хранится доказательство согласия;
- запрет скрывать отправителя;
- обязательная идентификация компании в сообщении.

Не утверждать юридическую допустимость автоматически. Система должна требовать ручное подтверждение основания контакта.

---

## 10. Safe rollout modes

Добавить режимы:

```env
OUTREACH_MODE=disabled
```

Варианты:

- `disabled` — отправка запрещена;
- `sandbox` — только номера из allowlist;
- `production` — разрешена production-логика.

Allowlist:

```env
OUTREACH_SANDBOX_ALLOWLIST=+77000000001,+77000000002
```

В режиме `sandbox` любые другие номера блокировать на уровне service и worker.

`OUTREACH_ENABLED` оставить для обратной совместимости, но постепенно заменить на `OUTREACH_MODE`.

---

## 11. Admin UI

Добавить страницы:

```text
/admin/inbox
/admin/inbox/{lead_id}
/admin/whatsapp/templates
/admin/whatsapp/templates/{id}
/admin/outreach/failed
/admin/outreach/dead-letter
```

В карточке Lead показать:

- CRM stage;
- consent status;
- DNC;
- service window;
- исходящие сообщения;
- статусы доставки;
- входящие сообщения;
- scheduled follow-up;
- ошибки отправки.

Добавить ручные действия:

- approve template message;
- send approved message;
- cancel queued message;
- retry failed retryable message;
- move to DNC;
- update consent status;
- mark message handled.

Все изменяющие действия должны иметь CSRF и audit log.

---

## 12. API

Добавить или уточнить endpoints:

```http
GET  /inbound-messages
GET  /inbound-messages/{id}
POST /inbound-messages/{id}/mark-handled
GET  /leads/{id}/conversation
POST /outreach/messages/{id}/retry
POST /outreach/messages/{id}/cancel
GET  /outreach/dead-letter
POST /outreach/dead-letter/{id}/requeue
PUT  /leads/{id}/consent
GET  /whatsapp/templates
POST /whatsapp/templates/sync
```

Для списков добавить pagination и фильтры.

---

## 13. Метрики и health checks

Расширить `/health`:

- Postgres;
- Redis;
- queue workers;
- WhatsApp config readiness;
- webhook config readiness.

Не выполнять реальный outbound API call в health check.

Добавить метрики:

- messages approved;
- queued;
- sent;
- delivered;
- read;
- replied;
- failed;
- retrying;
- DNC blocks;
- quiet-hour blocks;
- sandbox blocks;
- webhook duplicates;
- average delivery latency;
- response rate.

Добавить correlation ID для campaign/message/webhook.

---

## 14. Секреты и production configuration

Обновить `.env.example`:

```env
OUTREACH_MODE=disabled
OUTREACH_SANDBOX_ALLOWLIST=

WHATSAPP_GRAPH_API_VERSION=
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_BUSINESS_ACCOUNT_ID=
WHATSAPP_VERIFY_TOKEN=
WHATSAPP_APP_SECRET=
WHATSAPP_SERVICE_WINDOW_HOURS=24

OUTREACH_SEND_MAX_RETRIES=5
OUTREACH_SEND_RETRY_BASE_SECONDS=30
OUTREACH_SEND_JOB_TIMEOUT_SECONDS=60
```

Требования:

- приложение не стартует в `production` с `OUTREACH_MODE=production`, если обязательные секреты отсутствуют;
- секреты не отображаются в `/providers`, `/health`, admin UI и логах;
- добавить `.env.production.example` без настоящих значений;
- документировать Docker secrets или VPS secret file.

---

## 15. Миграция

Создать миграцию `006_whatsapp_production.py`.

Она должна добавить:

- `whatsapp_templates`;
- `inbound_messages`;
- consent fields;
- service-window fields;
- retry/dead-letter fields;
- нужные индексы и уникальные ограничения.

Обязательные уникальные ограничения:

- provider + provider_message_id для inbound;
- provider + external_event_id для webhook events;
- один provider message id для outbound.

Проверить upgrade и downgrade на чистой Postgres базе.

---

## 16. Тесты

Все тесты должны работать без реального Meta API.

Добавить тесты:

1. phone normalization;
2. masked logging;
3. sandbox allowlist;
4. DNC blocking;
5. consent blocking;
6. manual approval requirement;
7. template-only outside service window;
8. free-form inside service window;
9. webhook verification;
10. webhook signature validation;
11. webhook idempotency;
12. inbound message creates reply event;
13. inbound reply cancels follow-up;
14. temporary API failure retries;
15. permanent failure does not retry;
16. dead-letter after maximum attempts;
17. duplicate send prevention;
18. CSRF admin actions;
19. secrets absent from logs;
20. migration upgrade/downgrade.

Использовать `httpx.MockTransport` или аналогичный mock transport.

---

## 17. Docker smoke test

Расширить `scripts/smoke_test.sh` сценарием:

1. запустить stack;
2. создать mock lead;
3. установить sandbox consent;
4. создать campaign;
5. сгенерировать сообщение;
6. вручную approve;
7. отправить через mock WhatsApp adapter;
8. отправить подписанный mock webhook `delivered`;
9. отправить подписанный mock inbound message;
10. проверить `replied` stage;
11. проверить отмену follow-up;
12. проверить метрики;
13. завершить без внешней сети.

---

## 18. Документация

Создать:

- `docs/WHATSAPP_PRODUCTION_RUNBOOK.md`;
- `docs/WEBHOOK_SECURITY.md`;
- `docs/CONSENT_AND_CONTACT_POLICY.md`;
- `docs/OUTREACH_INCIDENT_RUNBOOK.md`;
- `docs/PRODUCTION_DEPLOYMENT.md`.

В production runbook описать:

- создание Meta app;
- добавление WhatsApp product;
- получение phone number ID;
- настройку permanent token;
- webhook URL;
- verify token;
- app secret;
- регистрацию templates;
- sandbox test;
- переход в production;
- отключение отправки аварийным флагом.

---

## 19. Критерии готовности

Этап завершен, если:

1. mock и real WhatsApp providers используют общий интерфейс;
2. production provider действительно вызывает Graph API;
3. первый контакт использует approved template;
4. free-form сообщение вне service window блокируется;
5. webhook проверяется verify token и подписью;
6. webhook события идемпотентны;
7. входящий ответ обновляет CRM и отменяет follow-up;
8. retry не создает дублей;
9. permanent errors не повторяются;
10. failed messages попадают в dead-letter;
11. sandbox не отправляет на номера вне allowlist;
12. DNC и withdrawn consent блокируют отправку;
13. все admin actions защищены CSRF;
14. секреты не попадают в ответы и логи;
15. миграция проходит upgrade/downgrade;
16. unit tests проходят;
17. Docker smoke test проходит без внешнего API;
18. реальная отправка остается выключенной по умолчанию.

---

## Ограничения

- Не включать массовую отправку автоматически.
- Не обходить ограничения WhatsApp/Meta.
- Не использовать неофициальные WhatsApp-библиотеки и эмуляцию WhatsApp Web.
- Не отправлять сообщения без ручного approve.
- Не добавлять автоматический AI-ответ входящим контактам на этом этапе.
- Не хранить секреты в Git.
- Не отправлять тестовые сообщения на реальные номера без sandbox allowlist.
- Не считать наличие номера автоматическим согласием на контакт.

---

## Отчет Codex после выполнения

Предоставить:

1. список измененных файлов;
2. миграцию и ее проверку;
3. схему WhatsApp send/webhook flow;
4. описание retry и idempotency;
5. команды sandbox-запуска;
6. примеры API-запросов;
7. результат unit tests;
8. результат Docker smoke test;
9. перечень обязательных production secrets;
10. список действий, которые остаются ручными в Meta Business Manager.
