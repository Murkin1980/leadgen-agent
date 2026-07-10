# Leadgen Agent

Автоматический пайплайн поиска компаний без сайта, генерации и публикации лендингов.

## About

Автоматический пайплайн для генерации лендингов SMB-компаний:
сбор данных → обогащение → AI-генерация контента → публикация на Cloudflare Pages → outreach через WhatsApp/Email/Telegram.

**Demo:** [leadgen-agent.pages.dev](https://leadgen-agent.pages.dev)

## Архитектура

```
POST /jobs → Redis [collect] → CollectorWorker
                                  ↓ Lead IDs
                            Redis [enrich] → EnricherWorker
                                               ↓ Lead IDs
                                         [manual or auto]
                                           POST /leads/{id}/content-generations
                                                 ↓
                                        Redis [generate_content] → ContentGeneratorWorker
                                                                      ↓ LandingPage (needs_review)
                                                                 POST /landings/{id}/approve
                                                                      ↓
                                                                 POST /landings/{id}/publish
                                                                      ↓
                                                                 sites/public/{slug}/
                                                                      ↓
                                                                 Nginx :8080 (preview)

POST /jobs/{id}/deploy → Redis [deploy] → DeployerWorker
                                              ↓ (Cloudflare Pages or Mock)
                                         Deployment record in PostgreSQL

                                         → Redis [outreach_generate] → OutreachGeneratorWorker
                                                                        ↓ OutreachMessage (needs_review)
                                                                   POST /campaigns/{id}/messages/{msg_id}/approve
                                                                        ↓
                                                                   Redis [outreach_send] → OutreachSenderWorker
                                                                                              ↓ OutreachMessage (sent)
                                                                                         POST /webhooks/whatsapp
                                                                                              ↓ OutreachEvent (delivered)
```

### Сервисы

| Сервис | Описание | Dockerfile |
|---|---|---|
| `migrate` | Применяет Alembic миграции при старте | `Dockerfile` |
| `api` | FastAPI — REST API + Admin UI | `Dockerfile` |
| `collector` | RQ worker — сбор компаний | `Dockerfile` |
| `enricher` | RQ worker — обогащение лидов | `Dockerfile` |
| `generator` | RQ worker — генерация JSON (legacy) | `Dockerfile` |
| `content-generator` | RQ worker — AI/template генерация контента | `Dockerfile` |
| `publisher` | RQ worker — копирование в sites/public | `Dockerfile` |
| `deployer` | RQ worker — деплой на Cloudflare Pages | `Dockerfile.deployer` |
| `outreach-generator` | RQ worker — генерация outreach-сообщений | `Dockerfile` |
| `outreach-sender` | RQ worker — отправка через провайдеры | `Dockerfile` |
| `outreach-status` | RQ worker — проверка статусов доставки | `Dockerfile` |
| `postgres` | PostgreSQL 16 | — |
| `redis` | Redis 7 | — |
| `preview` | Nginx — статический сервер лендингов | — |

## Быстрый старт

```bash
cp .env.example .env
docker compose up --build -d
curl http://localhost:8000/health
```

Миграции применяются автоматически через сервис `migrate`.

### Создание задания

```bash
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "city": "Алматы",
    "category": "мебель на заказ",
    "limit": 10
  }'
```

### Генерация контента

```bash
# Сгенерировать контент для лида
curl -X POST http://localhost:8000/leads/{lead_id}/content-generations \
  -H "Content-Type: application/json" \
  -d '{"language": "ru", "provider": "template"}'

# Проверить статус генерации
curl http://localhost:8000/content-generations/{generation_id}
```

### Утверждение лендинга

```bash
# Утвердить
curl -X POST http://localhost:8000/landings/{landing_id}/approve

# Отклонить
curl -X POST http://localhost:8000/landings/{landing_id}/reject \
  -H "Content-Type: application/json" \
  -d '{"reason": "Слишком общие преимущества"}'
```

### Публикация

```bash
# Только утвержденные лендинги могут быть опубликованы
curl -X POST http://localhost:8000/landings/{landing_id}/publish
```

### Админ-интерфейс

```
http://localhost:8000/admin/leads
http://localhost:8000/admin/landings
http://localhost:8000/admin/landings/{id}
http://localhost:8000/admin/generations/{id}
http://localhost:8000/admin/campaigns
http://localhost:8000/admin/campaigns/{id}
http://localhost:8000/admin/leads/{id}
http://localhost:8000/admin/do-not-contact
```

## API Endpoints

| Метод | Путь | Описание |
|---|---|---|
| GET | `/health` | Проверка здоровья |
| GET | `/providers` | Список провайдеров |
| POST | `/jobs` | Создание задания |
| GET | `/jobs/{id}` | Получение задания |
| POST | `/jobs/{id}/cancel` | Отмена задания |
| POST | `/jobs/{id}/retry` | Повтор задания |
| POST | `/jobs/{id}/deploy` | Деплой на Cloudflare Pages |
| GET | `/leads` | Список лидов |
| GET | `/leads/{id}` | Карточка лида |
| POST | `/leads/{id}/content-generations` | Генерация контента |
| GET | `/content-generations` | Список генераций |
| GET | `/content-generations/{id}` | Детали генерации |
| GET | `/landings` | Список лендингов |
| GET | `/landings/{id}` | Карточка лендинга |
| POST | `/landings/{id}/approve` | Утверждение |
| POST | `/landings/{id}/reject` | Отклонение |
| PUT | `/landings/{id}/profile` | Редактирование профиля |
| GET | `/landings/{id}/versions` | История версий |
| GET | `/landings/{id}/versions/{n}` | Версия |
| POST | `/landings/{id}/versions/{n}/restore` | Восстановление версии |
| POST | `/landings/{id}/publish` | Публикация |
| GET | `/deployments` | Список деплоев |
| GET | `/deployments/{id}` | Статус деплоя |
| GET | `/usage/openai` | Использование OpenAI |
| POST | `/campaigns` | Создание кампании |
| GET | `/campaigns` | Список кампаний |
| GET | `/campaigns/{id}` | Детали кампании |
| POST | `/campaigns/{id}/generate-messages` | Генерация outreach-сообщений |
| GET | `/campaigns/{id}/messages` | Сообщения кампании |
| POST | `/campaigns/{id}/messages/{msg_id}/approve` | Утверждение сообщения |
| POST | `/campaigns/{id}/messages/{msg_id}/reject` | Отклонение сообщения |
| POST | `/campaigns/{id}/messages/{msg_id}/send` | Отправка сообщения |
| GET | `/campaigns/{id}/follow-up-candidates` | Кандидаты на follow-up |
| POST | `/leads/{id}/stage` | Переход по этапу воронки |
| POST | `/leads/{id}/do-not-contact` | Блокировка лида |
| DELETE | `/leads/{id}/do-not-contact` | Снятие блокировки |
| POST | `/webhooks/whatsapp` | Webhook WhatsApp |
| POST | `/webhooks/email` | Webhook Email |
| POST | `/webhooks/telegram` | Webhook Telegram |
| GET | `/metrics` | Метрики outreach |
| GET | `/audit-log` | Журнал аудита |
| GET | `/providers` | Список outreach-провайдеров |

## Переменные окружения

| Переменная | Описание | По умолчанию |
|---|---|---|
| `APP_ENV` | Режим (`development`/`production`) | `development` |
| `DATABASE_URL` | URL PostgreSQL | — |
| `REDIS_URL` | URL Redis | — |
| `TEXT_GENERATOR_PROVIDER` | `template`, `openai`, `mock` | `template` |
| `OPENAI_API_KEY` | Ключ OpenAI | — |
| `OPENAI_MODEL` | Модель OpenAI | `gpt-4o-mini` |
| `OPENAI_TIMEOUT_SECONDS` | Таймаут запроса | `45` |
| `OPENAI_MAX_RETRIES` | Макс. повторов | `3` |
| `OPENAI_TEMPERATURE` | Температура | `0.4` |
| `OPENAI_MAX_OUTPUT_TOKENS` | Макс. токенов | `2500` |
| `OPENAI_DAILY_BUDGET_USD` | Дневной лимит ($) | `5` |
| `OPENAI_MAX_REQUESTS_PER_JOB` | Лимит запросов на задание | `30` |
| `PUBLIC_BASE_URL` | Базовый URL для превью | `http://localhost:8080` |
| `COLLECTOR_PROVIDER` | `mock`, `csv`, `two_gis` | `mock` |
| `DEPLOYMENT_PROVIDER` | `mock` или `cloudflare` | `mock` |
| `DEFAULT_LANGUAGE` | Язык по умолчанию (`ru`/`kk`) | `ru` |
| `ADMIN_USERNAME` | Логин админки | `admin` |
| `ADMIN_PASSWORD` | Пароль админки | — |
| `OUTREACH_PROVIDER` | Провайдер outreach (`mock`/`whatsapp`/`email`/`telegram`) | `mock` |
| `OUTREACH_ENABLED` | Включить отправку | `false` |
| `OUTREACH_MAX_PER_HOUR` | Лимит сообщений в час | `50` |
| `OUTREACH_QUIET_HOURS_START` | Начало тихих часов (HH:MM) | `09:00` |
| `OUTREACH_QUIET_HOURS_END` | Конец тихих часов (HH:MM) | `20:00` |
| `OUTREACH_TIMEZONE` | Часовой пояс | `Asia/Almaty` |
| `WHATSAPP_API_VERSION` | Версия WhatsApp API | `v18.0` |
| `WHATSAPP_PHONE_NUMBER_ID` | ID телефона WhatsApp | — |
| `WHATSAPP_ACCESS_TOKEN` | Токен доступа WhatsApp | — |
| `WHATSAPP_BUSINESS_ACCOUNT_ID` | ID бизнес-аккаунта WhatsApp | — |
| `WHATSAPP_VERIFY_TOKEN` | Токен верификации webhook | — |
| `EMAIL_SMTP_HOST` | SMTP хост | — |
| `EMAIL_SMTP_PORT` | SMTP порт | `587` |
| `EMAIL_USERNAME` | SMTP логин | — |
| `EMAIL_PASSWORD` | SMTP пароль | — |
| `EMAIL_FROM_ADDRESS` | Email отправителя | — |
| `TELEGRAM_BOT_TOKEN` | Токен Telegram бота | — |
| `FOLLOW_UP_DELAY_HOURS` | Задержка между follow-up (часы) | `48` |
| `FOLLOW_UP_MAX_COUNT` | Макс. количество follow-up | `3` |

## Тесты

```bash
pip install -r requirements.txt
pip install pytest
TEXT_GENERATOR_PROVIDER=mock DEPLOYMENT_PROVIDER=mock COLLECTOR_PROVIDER=mock pytest tests/ -v
```

239 tests, включая CRM pipeline, outreach providers, message generation, webhook handling, security (CSRF, rate limiting).

## CI

GitHub Actions запускает:
1. **Unit-тесты** — pytest + compile check
2. **Docker build** — `docker compose build` всех образов
3. **Smoke test** — полный пайплайн в Docker (mock-провайдеры)

## Структура проекта

```
app/
├── api/
│   ├── routes.py           # FastAPI endpoints
│   ├── outreach_routes.py  # Outreach API endpoints
│   └── admin.py            # Admin UI (Jinja2)
├── collector/              # Сбор данных
│   ├── adapter.py
│   ├── base.py
│   ├── mock.py
│   ├── csv.py
│   ├── factory.py
│   └── adapters/
│       └── two_gis.py
├── content_validator.py    # Валидация контента (deprecated, use generation/validator.py)
├── deployment/             # Абстракция деплоя
│   ├── adapter.py
│   ├── base.py
│   ├── mock.py
│   └── cloudflare.py
├── enrichment/
│   └── enricher.py         # Обогащение лидов
├── generation/
│   ├── base.py             # TextGenerationAdapter Protocol + GeneratedProfile
│   ├── context.py          # GenerationContext dataclass
│   ├── factory.py          # Provider factory
│   ├── mock.py             # MockTextGenerationAdapter
│   ├── openai.py           # OpenAITextGenerationAdapter
│   ├── template.py         # TemplateTextGenerationAdapter (ru/kk)
│   ├── usage.py            # UsageTracker (budget/limits)
│   ├── validator.py        # GeneratedContentValidator
│   └── prompts/
│       ├── system_v1.txt
│       └── landing_profile_v1.txt
├── landing/
│   ├── schema.py           # LandingProfile Pydantic schema
│   └── renderer.py         # Jinja2 HTML renderer
├── logging/
│   └── structured.py       # JSON structured logging
├── models/
│   ├── lead.py             # Lead model (CRM fields)
│   ├── stage.py            # LeadStage enum + LeadStageHistory
│   ├── search_job.py       # SearchJob model
│   ├── landing_page.py     # LandingPage + LandingPageVersion
│   ├── content_generation.py # ContentGeneration model
│   ├── deployment.py       # Deployment model
│   ├── campaign.py         # OutreachCampaign + OutreachMessage
│   ├── event.py            # OutreachEvent
│   └── audit.py            # AuditLog
├── outreach/               # Outreach module
│   ├── provider.py         # OutreachProvider base class
│   ├── mock_provider.py    # MockOutreachProvider
│   ├── email_provider.py   # EmailOutreachProvider (stub)
│   ├── whatsapp_provider.py # WhatsAppCloudProvider (stub)
│   ├── telegram_provider.py # TelegramOutreachProvider (stub)
│   ├── factory.py          # create_outreach_provider()
│   ├── message_generator.py # RU/KK message templates
│   ├── service.py          # Outreach business logic
│   ├── stage_service.py    # LeadStage transitions
│   └── webhook_handler.py  # Webhook event processing
├── publisher/
│   └── publisher.py        # publish_site()
├── qualification/
│   └── service.py          # LeadQualifier
├── schemas/
│   ├── job.py
│   ├── lead.py
│   ├── landing.py
│   ├── content_generation.py
│   ├── deployment.py
│   └── outreach.py         # Outreach Pydantic schemas
├── security.py             # CSRF, audit log, login rate limiting
├── verification/
│   └── website.py          # WebsiteVerifier (SSRF protection)
├── workers/
│   ├── collector_worker.py
│   ├── enricher_worker.py
│   ├── generator_worker.py
│   ├── content_generator_worker.py
│   ├── publisher_worker.py
│   ├── deployer_worker.py
│   ├── outreach_generator_worker.py
│   ├── outreach_sender_worker.py
│   └── outreach_status_worker.py
├── config.py               # Settings (pydantic-settings)
├── database.py             # SQLAlchemy engine
└── main.py                 # FastAPI app

alembic/versions/
├── 001_initial.py
├── 002_deployments_and_job_id.py
├── 003_provider_and_qualification.py
├── 004_content_generations_and_landing_versions.py
└── 005_crm_outreach_audit.py

docs/
├── AI_GENERATION_POLICY.md
├── CONTENT_REVIEW_RUNBOOK.md
├── COLLECTOR_RUNBOOK.md
├── CRM_PIPELINE.md
├── DATA_SOURCE_POLICY.md
├── OUTREACH_POLICY.md
├── OUTREACH_RUNBOOK.md
└── WHATSAPP_CLOUD_SETUP.md
```

## Диаграмма состояний

### SearchJob
```
pending → collecting → enriching → generating → publishing → completed
                                                        → failed
          → cancelled
```

### LandingPage
```
draft → needs_review → approved → published → deployed
                → rejected
                → failed
```

### ContentGeneration
```
queued → running → succeeded
                 → failed
                 → rejected (validation failed)
```

### Deployment
```
queued → running → succeeded
                 → failed
```

### OutreachCampaign
```
draft → ready → running → completed
                    → paused
              → cancelled
              → failed
```

### OutreachMessage
```
draft → needs_review → approved → queued → sent → delivered → read → replied
                                       → failed
                              → rejected → cancelled
```

### LeadStage
```
new → qualified → landing_generated → needs_review → ready_for_outreach → contacted → replied → interested → proposal_sent → won/lost
                                                                                                                → do_not_contact
```

## Ограничения

- OpenAI отключен по умолчанию (provider = template)
- AI-генерация не публикуется автоматически
- Все факты должны быть проверены перед публикацией
- Не логируются API ключи, полные промпты, сырые данные клиентов
- Тесты никогда не вызывают реальный OpenAI API
- Outreach не отправляется без `OUTREACH_ENABLED=true`
- Все outreach-сообщения требуют ручного утверждения
- WhatsApp/Email/Telegram провайдеры — заглушки (stubs) для MVP
- Тихие часы и лимиты сообщений настраиваются через env vars
