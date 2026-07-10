# Leadgen Agent

Автоматический пайплайн поиска компаний без сайта, генерации и публикации лендингов.

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

## Тесты

```bash
pip install -r requirements.txt
pip install pytest
TEXT_GENERATOR_PROVIDER=mock DEPLOYMENT_PROVIDER=mock COLLECTOR_PROVIDER=mock pytest tests/ -v
```

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
│   ├── lead.py             # Lead model
│   ├── search_job.py       # SearchJob model
│   ├── landing_page.py     # LandingPage + LandingPageVersion
│   ├── content_generation.py # ContentGeneration model
│   └── deployment.py       # Deployment model
├── publisher/
│   └── publisher.py        # publish_site()
├── qualification/
│   └── service.py          # LeadQualifier
├── schemas/
│   ├── job.py
│   ├── lead.py
│   ├── landing.py
│   ├── content_generation.py
│   └── deployment.py
├── verification/
│   └── website.py          # WebsiteVerifier (SSRF protection)
├── workers/
│   ├── collector_worker.py
│   ├── enricher_worker.py
│   ├── generator_worker.py
│   ├── content_generator_worker.py
│   ├── publisher_worker.py
│   └── deployer_worker.py
├── config.py               # Settings (pydantic-settings)
├── database.py             # SQLAlchemy engine
└── main.py                 # FastAPI app

alembic/versions/
├── 001_initial.py
├── 002_deployments_and_job_id.py
├── 003_provider_and_qualification.py
└── 004_content_generations_and_landing_versions.py

docs/
├── AI_GENERATION_POLICY.md
├── CONTENT_REVIEW_RUNBOOK.md
├── COLLECTOR_RUNBOOK.md
└── DATA_SOURCE_POLICY.md
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

## Ограничения

- OpenAI отключен по умолчанию (provider = template)
- AI-генерация не публикуется автоматически
- Все факты должны быть проверены перед публикацией
- Не логируются API ключи, полные промпты, сырые данные клиентов
- Тесты никогда не вызывают реальный OpenAI API
