# Leadgen Agent MVP

Автоматический пайплайн поиска компаний без сайта, генерации и публикации лендингов.

## Архитектура

```
POST /jobs → Redis Queue (collect) → Collector Worker
                                         ↓ Lead IDs
                                    Redis Queue (enrich) → Enricher Worker
                                                             ↓ Lead IDs
                                                        Redis Queue (generate) → Generator Worker
                                                                                    ↓ LandingPage IDs
                                                                               Redis Queue (publish) → Publisher Worker
                                                                                                         ↓
                                                                                                    sites/public/
```

### Сервисы

| Сервис | Описание |
|---|---|
| `api` | FastAPI — REST API |
| `collector` | RQ worker — сбор компаний |
| `enricher` | RQ worker — обогащение лидов |
| `generator` | RQ worker — генерация JSON и HTML |
| `publisher` | RQ worker — публикация в sites/public |
| `postgres` | PostgreSQL 16 |
| `redis` | Redis 7 |
| `preview` | Nginx — статический сервер лендингов |

## Быстрый старт

```bash
cp .env.example .env
docker compose up --build -d
docker compose exec api alembic upgrade head
curl http://localhost:8000/health
```

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

Откройте в браузере:

```
http://localhost:8080/{slug}/
```

## Структура проекта

```
app/
├── api/routes.py          # FastAPI endpoints
├── collector/             # Сбор данных (mock + 2GIS stub)
├── enrichment/            # Обогащение лидов
├── generation/            # Генерация JSON-профиля (template + OpenAI stub)
├── landing/               # JSON-схема и HTML-рендеринг
├── publisher/             # Публикация в sites/public
├── workers/               # RQ workers
├── models/                # SQLAlchemy модели
├── schemas/               # Pydantic schemas
├── config.py              # Настройки
└── database.py            # Подключение к БД
```

## API Endpoints

| Метод | Путь | Описание |
|---|---|---|
| GET | `/health` | Проверка здоровья |
| POST | `/jobs` | Создание задания |
| GET | `/jobs/{id}` | Получение задания |
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

## Тесты

```bash
pip install -r requirements.txt
pytest tests/ -v
```

## Оставшиеся задачи

- [ ] Подключить настоящий 2GIS API (замена MockCollectorAdapter)
- [ ] Подключить OpenAI для генерации профилей (замена TemplateTextGenerationAdapter)
- [ ] Деплой лендингов через Cloudflare Pages
- [ ] Автоматический push в GitHub через publish_to_git.sh
- [ ] Мониторинг и логирование
- [ ] Фронтенд для управления заданиями
