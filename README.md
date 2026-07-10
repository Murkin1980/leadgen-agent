# Leadgen Agent MVP

Автоматический пайплайн поиска компаний без сайта, генерации и публикации лендингов.

## Архитектура

```
POST /jobs → Redis [collect] → CollectorWorker
                                  ↓ Lead IDs
                            Redis [enrich] → EnricherWorker
                                               ↓ Lead IDs
                                          Redis [generate] → GeneratorWorker
                                                               ↓ LandingPage IDs
                                                          Redis [publish] → PublisherWorker
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
| `api` | FastAPI — REST API | `Dockerfile` |
| `collector` | RQ worker — сбор компаний | `Dockerfile` |
| `enricher` | RQ worker — обогащение лидов | `Dockerfile` |
| `generator` | RQ worker — генерация JSON и HTML | `Dockerfile` |
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

### Просмотр задания

```bash
curl http://localhost:8000/jobs/1
```

### Список лидов

```bash
curl "http://localhost:8000/leads?city=Алматы&status=published"
```

### Просмотр лендинга

```
http://localhost:8080/{slug}/
```

### Деплой на Cloudflare

```bash
# Через API (рекомендуется)
curl -X POST http://localhost:8000/jobs/1/deploy

# Или вручную через скрипт
bash scripts/deploy_cloudflare.sh
```

### Проверка статуса деплоя

```bash
curl http://localhost:8000/deployments
curl http://localhost:8000/deployments/{deployment_id}
```

## API Endpoints

| Метод | Путь | Описание |
|---|---|---|
| GET | `/health` | Проверка здоровья |
| POST | `/jobs` | Создание задания |
| GET | `/jobs/{id}` | Получение задания |
| POST | `/jobs/{id}/deploy` | Деплой на Cloudflare Pages |
| GET | `/leads` | Список лидов (фильтры: city, category, status, search_job_id) |
| GET | `/leads/{id}` | Карточка лида |
| POST | `/leads/{id}/generate` | Повторная генерация |
| POST | `/landings/{id}/publish` | Публикация |
| GET | `/deployments` | Список деплоев (фильтры: job_id, status) |
| GET | `/deployments/{id}` | Статус деплоя |

## Переменные окружения

| Переменная | Описание | По умолчанию |
|---|---|---|
| `APP_ENV` | Режим | `development` |
| `DATABASE_URL` | URL PostgreSQL | — |
| `REDIS_URL` | URL Redis | — |
| `TEXT_GENERATOR_PROVIDER` | `template` или `openai` | `template` |
| `OPENAI_API_KEY` | Ключ OpenAI | — |
| `PUBLIC_BASE_URL` | Базовый URL для превью | `http://localhost:8080` |
| `COLLECTOR_PROVIDER` | `mock` или `two_gis` | `mock` |
| `DEPLOYMENT_PROVIDER` | `mock` или `cloudflare` | `mock` |
| `CLOUDFLARE_API_TOKEN` | Токен Cloudflare API | — |
| `CLOUDFLARE_ACCOUNT_ID` | ID аккаунта Cloudflare | — |
| `CLOUDFLARE_PAGES_PROJECT` | Имя проекта Cloudflare Pages | `leadgen-agent` |
| `CLOUDFLARE_PAGES_BRANCH` | Ветка для деплоя | `master` |
| `CLOUDFLARE_PUBLIC_URL` | Публичный URL деплоя | `https://leadgen-agent.pages.dev` |

## Тесты

```bash
pip install -r requirements.txt
pip install pytest
DEPLOYMENT_PROVIDER=mock COLLECTOR_PROVIDER=mock pytest tests/ -v
```

## Mock-деплой (без Cloudflare)

```bash
DEPLOYMENT_PROVIDER=mock curl -X POST http://localhost:8000/jobs/1/deploy
```

## Настоящий Cloudflare деплой

1. Установить `.env`:
```env
DEPLOYMENT_PROVIDER=cloudflare
CLOUDFLARE_API_TOKEN=ваш_токен
CLOUDFLARE_ACCOUNT_ID=ваш_account_id
```

2. Запустить:
```bash
docker compose up --build -d
curl -X POST http://localhost:8000/jobs/1/deploy
```

## CI

GitHub Actions запускает:
1. **Unit-тесты** — pytest + compile check
2. **Docker build** — `docker compose build` всех образов (включая deployer)
3. **Smoke test** — полный пайплайн в Docker (mock-деплой, без реального Cloudflare)

## Структура проекта

```
app/
├── api/routes.py          # FastAPI endpoints
├── collector/             # Сбор данных (mock + 2GIS stub)
│   ├── adapter.py         # CollectorAdapter Protocol
│   ├── base.py            # CollectedCompany + CollectedPage DTOs
│   ├── mock.py            # MockCollectorAdapter (paginated)
│   └── adapters/
│       └── two_gis.py     # TwoGisCollectorAdapter (disabled)
├── deployment/            # Абстракция деплоя
│   ├── adapter.py         # DeploymentAdapter Protocol
│   ├── base.py            # DeploymentResult DTO
│   ├── mock.py            # MockDeploymentAdapter
│   └── cloudflare.py      # CloudflarePagesDeploymentAdapter
├── enrichment/            # Обогащение лидов
├── generation/            # Генерация JSON-профиля (template + OpenAI stub)
├── landing/               # JSON-схема и HTML-рендеринг
├── publisher/             # Публикация в sites/public
├── workers/               # RQ workers
│   ├── collector_worker.py
│   ├── enricher_worker.py
│   ├── generator_worker.py
│   ├── publisher_worker.py
│   └── deployer_worker.py
├── models/                # SQLAlchemy модели
│   ├── lead.py            # Lead (with search_job_id FK)
│   ├── search_job.py      # SearchJob
│   ├── landing_page.py    # LandingPage
│   └── deployment.py      # Deployment
├── schemas/               # Pydantic schemas
│   ├── job.py
│   ├── lead.py
│   ├── landing.py
│   └── deployment.py
├── config.py              # Настройки
└── database.py            # Подключение к БД

scripts/
├── deploy_cloudflare.sh   # Ручной деплой (адаптер)
├── publish_to_git.sh      # Деплой через Git
└── smoke_test.sh          # Интеграционный smoke test

Dockerfile                 # Основной образ (Python + Node.js)
Dockerfile.deployer        # Образ деплойера (Python + Node.js + Wrangler)
```

## Диаграмма состояний деплоя

```
queued → running → succeeded
                  → failed
```

## Оставшиеся задачи

- [ ] Подключить настоящий 2GIS API (замена MockCollectorAdapter)
- [ ] Подключить OpenAI для генерации профилей (замена TemplateTextGenerationAdapter)
- [ ] Добавить структурированные логи
- [ ] Добавить retry и dead-letter обработку
