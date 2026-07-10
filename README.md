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
                                                                                ↓
                                                                           Cloudflare Pages (deploy)
```

### Сервисы

| Сервис | Описание |
|---|---|
| `migrate` | Применяет Alembic миграции при старте |
| `api` | FastAPI — REST API |
| `collector` | RQ worker — сбор компаний |
| `enricher` | RQ worker — обогащение лидов |
| `generator` | RQ worker — генерация JSON и HTML |
| `publisher` | RQ worker — копирование в sites/public |
| `postgres` | PostgreSQL 16 |
| `redis` | Redis 7 |
| `preview` | Nginx — статический сервер лендингов |

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
bash scripts/deploy_cloudflare.sh
```

Или через API — деплой всех опубликованных лендингов:

```bash
curl -X POST http://localhost:8000/jobs/1/deploy
```

## API Endpoints

| Метод | Путь | Описание |
|---|---|---|
| GET | `/health` | Проверка здоровья |
| POST | `/jobs` | Создание задания |
| GET | `/jobs/{id}` | Получение задания |
| POST | `/jobs/{id}/deploy` | Деплой на Cloudflare |
| GET | `/leads` | Список лидов |
| GET | `/leads/{id}` | Карточка лида |
| POST | `/leads/{id}/generate` | Повторная генерация |
| POST | `/landings/{id}/publish` | Публикация |

## Переменные окружения

| Переменная | Описание | По умолчанию |
|---|---|---|
| `APP_ENV` | Режим | `development` |
| `DATABASE_URL` | URL PostgreSQL | — |
| `REDIS_URL` | URL Redis | — |
| `TEXT_GENERATOR_PROVIDER` | `template` или `openai` | `template` |
| `OPENAI_API_KEY` | Ключ OpenAI | — |
| `PUBLIC_BASE_URL` | Базовый URL для превью | `http://localhost:8080` |
| `CLOUDFLARE_PAGES_PROJECT` | Имя проекта Cloudflare Pages | `leadgen-agent` |
| `CLOUDFLARE_PAGES_BRANCH` | Ветка для деплоя | `master` |

## Тесты

```bash
pip install -r requirements.txt
pip install pytest
pytest tests/ -v
```

## CI

GitHub Actions автоматически запускает тесты и проверку Docker Compose при пуше в `master`.

## Структура проекта

```
app/
├── api/routes.py          # FastAPI endpoints
├── collector/             # Сбор данных (mock + 2GIS stub)
├── enrichment/            # Обогащение лидов
├── generation/            # Генерация JSON-профиля (template + OpenAI stub)
├── landing/               # JSON-схема и HTML-рендеринг
├── publisher/             # Публикация в sites/public
├── workers/               # RQ workers (collector, enricher, generator, publisher, deployer)
├── models/                # SQLAlchemy модели
├── schemas/               # Pydantic schemas
├── config.py              # Настройки
└── database.py            # Подключение к БД
```

## Оставшиеся задачи

- [ ] Подключить настоящий 2GIS API (замена MockCollectorAdapter)
- [ ] Подключить OpenAI для генерации профилей (замена TemplateTextGenerationAdapter)
- [ ] Настроить Cloudflare Pages production branch
- [ ] Добавить структурированные логи
- [ ] Добавить retry и dead-letter обработку
- [ ] Интеграционные тесты Docker pipeline
