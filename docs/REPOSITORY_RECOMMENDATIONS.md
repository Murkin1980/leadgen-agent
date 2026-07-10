# Leadgen Agent — рекомендации по исправлению и стабилизации

Дата аудита: 10 июля 2026 года.

## 1. Цель документа

Этот документ фиксирует найденные инфраструктурные проблемы репозитория `leadgen-agent` и рекомендуемый порядок их исправления перед подключением реального 2GIS-сборщика, OpenAI и автоматического production-деплоя.

Текущий MVP уже содержит:

- FastAPI API;
- PostgreSQL и SQLAlchemy 2.x;
- Alembic;
- Redis и RQ;
- отдельные workers `collector`, `enricher`, `generator`, `publisher`;
- mock-сборщик компаний;
- обогащение лидов;
- генерацию JSON и статического HTML;
- локальный Nginx preview;
- Cloudflare Pages deployment через Wrangler;
- pytest-тесты.

Главная задача следующего этапа — не расширять функциональность, а обеспечить корректный сквозной путь:

```text
POST /jobs
→ collect
→ enrich
→ generate
→ publish
→ sites/public/{slug}
→ локальный preview
→ Cloudflare Pages
```

---

## 2. Критическая проблема: разные файловые хранилища Docker

### Текущее состояние

Python-сервисы используют именованный Docker volume:

```yaml
volumes:
  - sites:/app/sites
```

При этом Nginx preview читает локальную директорию:

```yaml
volumes:
  - ./sites/public:/usr/share/nginx/html:ro
```

Это два разных хранилища.

В результате:

1. `generator` создаёт файлы внутри Docker volume `sites`;
2. `publisher` копирует файлы внутри того же Docker volume;
3. Nginx смотрит в локальную папку `./sites/public`;
4. API может вернуть статус `published`, но сайт не будет доступен по `http://localhost:8080/{slug}/`.

### Рекомендованное исправление

Для сервисов:

- `api`;
- `collector`;
- `enricher`;
- `generator`;
- `publisher`;

заменить:

```yaml
volumes:
  - sites:/app/sites
```

на:

```yaml
volumes:
  - ./sites:/app/sites
```

Nginx оставить с:

```yaml
volumes:
  - ./sites/public:/usr/share/nginx/html:ro
```

Удалить именованный volume `sites` из нижней секции `volumes`.

Оставить только:

```yaml
volumes:
  pgdata:
```

### Ожидаемый результат

Все сервисы будут работать с одной файловой структурой:

```text
./sites/
├── drafts/
└── public/
```

---

## 3. Критическая проблема: `sites/public/` исключён из Git

### Текущее состояние

В `.gitignore` указано:

```gitignore
sites/public/
```

При этом `scripts/publish_to_git.sh` выполняет:

```bash
git add sites/public
```

Git проигнорирует эту папку, поэтому скрипт не сможет добавить опубликованные лендинги в commit.

### Рекомендованный вариант

Оставить исключённой только временную директорию:

```gitignore
sites/drafts/
```

Удалить из `.gitignore`:

```gitignore
sites/public/
```

Чтобы пустая структура каталогов сохранялась в репозитории, добавить:

```text
sites/drafts/.gitkeep
sites/public/.gitkeep
```

### Альтернативный вариант

Можно использовать:

```bash
git add -f sites/public
```

Но это менее прозрачно. Рекомендуется явно разрешить отслеживание `sites/public/` либо полностью отказаться от Git-публикации в пользу Wrangler.

---

## 4. Несовпадение основной ветки

### Текущее состояние

Основная ветка репозитория:

```text
master
```

В скрипте Cloudflare используется:

```bash
--branch main
```

Это может привести к тому, что Cloudflare создаст preview deployment вместо production deployment или будет использовать не ту ветку.

### Рекомендованное исправление

Выбрать один из вариантов:

#### Вариант A — сохранить `master`

Заменить:

```bash
--branch main
```

на:

```bash
--branch master
```

#### Вариант B — перейти на `main`

Переименовать default branch GitHub в `main` и обновить все deployment-настройки.

### Рекомендация

Для минимального объёма изменений сейчас использовать `master` во всех скриптах и настройках.

---

## 5. Смешаны два механизма публикации

### Текущее состояние

`scripts/publish_to_git.sh` одновременно:

1. добавляет `sites/public` в Git;
2. создаёт commit;
3. выполняет `git push`;
4. запускает Wrangler deploy.

Таким образом используются сразу два пути:

```text
VPS → GitHub → Cloudflare Pages
```

и:

```text
VPS → Wrangler → Cloudflare Pages
```

Это создаёт риск:

- двойного deployment;
- разных версий сайта;
- лишних commit с генерируемыми файлами;
- путаницы между production и preview;
- конфликтов при одновременной публикации.

### Рекомендованная архитектура

Основной путь:

```text
VPS
→ sites/public
→ npx wrangler pages deploy
→ Cloudflare Pages
```

GitHub должен хранить исходный код проекта, шаблоны и конфигурацию, но не обязан хранить каждый сгенерированный лендинг.

### Рекомендуемое разделение скриптов

`scripts/deploy_cloudflare.sh`:

- проверяет наличие `sites/public`;
- запускает Wrangler;
- публикует текущую сборку;
- возвращает ненулевой exit code при ошибке.

`scripts/publish_to_git.sh`:

- используется только вручную;
- не вызывает Wrangler;
- при необходимости коммитит статические сайты в отдельную ветку или отдельный repository.

---

## 6. Не запускать Cloudflare deployment после каждого лида

### Проблема

Если запускать Wrangler после публикации каждого `LandingPage`, то задание на 50 компаний создаст до 50 deployment подряд.

Это:

- замедляет обработку;
- создаёт гонки;
- расходует лимиты Cloudflare;
- усложняет диагностику;
- может опубликовать неполный набор сайтов.

### Рекомендация

Cloudflare deployment должен запускаться один раз:

- после завершения всего `SearchJob`;
- либо вручную через административный endpoint;
- либо отдельной задачей `deploy`, которая получает `search_job_id`.

Рекомендуемая очередь:

```text
collect
→ enrich
→ generate
→ publish
→ deploy
```

При этом `publish` означает локальное копирование в `sites/public`, а `deploy` — отправку всей директории в Cloudflare Pages.

---

## 7. Добавить отдельный статус deployment

Сейчас статус `published` может означать только копирование файлов в локальную папку.

Рекомендуется разделить:

### LandingPage

- `draft`;
- `generated`;
- `published_local`;
- `deployed`;
- `failed`.

Или оставить `published`, но добавить поля:

- `deployed_at`;
- `deployment_status`;
- `deployment_error`;
- `deployment_url`.

### SearchJob

Добавить этап:

- `deploying`.

И итоговые поля:

- `deployment_status`;
- `deployment_url`;
- `deployment_error`.

---

## 8. Автоматические миграции

### Текущее состояние

После запуска Docker Compose требуется вручную выполнять:

```bash
docker compose exec api alembic upgrade head
```

Для локальной разработки это допустимо, но для VPS можно случайно запустить API до применения миграций.

### Рекомендованный вариант

Добавить отдельный сервис:

```yaml
migrate:
  build: .
  env_file: .env
  command: ["alembic", "upgrade", "head"]
  depends_on:
    postgres:
      condition: service_healthy
  restart: "no"
```

Затем `api` и workers должны зависеть от успешного завершения `migrate`.

Если Docker Compose не поддерживает нужное условие завершения в целевой среде, использовать entrypoint-скрипт с идемпотентной командой:

```bash
alembic upgrade head
exec "$@"
```

Не запускать параллельно несколько миграций из каждого worker.

---

## 9. GitHub Actions

Добавить workflow:

```text
.github/workflows/ci.yml
```

Он должен выполнять:

1. checkout;
2. настройку Python 3.12;
3. установку зависимостей;
4. запуск lint;
5. запуск pytest;
6. проверку импорта приложения;
7. проверку Docker Compose config.

Минимальные команды:

```bash
python -m compileall app
pytest -q
docker compose config
```

Опционально:

```bash
ruff check .
ruff format --check .
```

Cloudflare production deploy не следует запускать из CI до появления защищённых secrets и отдельной production-ветки.

---

## 10. Проверка Cloudflare-конфигурации

Проверить:

- существует ли Pages project `leadgen-agent`;
- совпадает ли `project-name`;
- авторизован ли Wrangler;
- настроен ли `CLOUDFLARE_API_TOKEN` на VPS;
- выбран ли правильный Cloudflare account;
- является ли ветка `master` production branch;
- совпадает ли `PUBLIC_BASE_URL` с фактическим Pages URL;
- не используется ли устаревший или тестовый домен.

Не хранить в Git:

- `CLOUDFLARE_API_TOKEN`;
- `CLOUDFLARE_ACCOUNT_ID`;
- OpenAI API key;
- PostgreSQL production password.

Добавить их только в `.env` VPS или secrets CI/CD.

---

## 11. Улучшение deployment-скрипта

`scripts/deploy_cloudflare.sh` должен:

1. использовать `set -Eeuo pipefail`;
2. проверять наличие `npx`;
3. проверять наличие `sites/public`;
4. проверять, что директория не пустая;
5. принимать project name и branch из env;
6. не содержать жёстко заданный URL результата;
7. сохранять лог deployment;
8. возвращать корректный exit code.

Рекомендуемые переменные:

```env
CLOUDFLARE_PAGES_PROJECT=leadgen-agent
CLOUDFLARE_PAGES_BRANCH=master
CLOUDFLARE_PAGES_URL=https://leadgen-agent.pages.dev
```

---

## 12. Проверка сквозного сценария

После исправлений выполнить полный тест.

### 12.1 Запуск

```bash
cp .env.example .env
docker compose down -v
docker compose up --build -d
```

### 12.2 Проверка контейнеров

```bash
docker compose ps
```

Все сервисы должны быть healthy или running.

### 12.3 Проверка API

```bash
curl http://localhost:8000/health
```

Ожидается:

```json
{
  "status": "ok",
  "postgres": true,
  "redis": true
}
```

### 12.4 Создание задания

```bash
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "city": "Алматы",
    "category": "мебель на заказ",
    "limit": 10
  }'
```

### 12.5 Проверка статуса

```bash
curl http://localhost:8000/jobs/1
```

Дождаться статуса `completed`.

### 12.6 Проверка файлов

```bash
find sites/drafts -maxdepth 2 -type f
find sites/public -maxdepth 2 -type f
```

### 12.7 Проверка preview

Открыть:

```text
http://localhost:8080/{slug}/
```

### 12.8 Проверка Cloudflare

```bash
bash scripts/deploy_cloudflare.sh
```

После deployment проверить production URL.

---

## 13. Дополнительные рекомендации

### Идемпотентность

Повторный запуск одной задачи не должен:

- создавать дубли лидов;
- создавать несколько LandingPage для одного и того же лида без причины;
- удалять уже опубликованные сайты;
- ломать статус завершённого SearchJob.

### Безопасность путей

Slug должен проходить строгую проверку. Нельзя позволять значения вида:

```text
../../etc
```

Все операции генератора и publisher должны проверять, что итоговый путь остаётся внутри `sites/drafts` или `sites/public`.

### Атомарная публикация

Копировать сайт сначала во временную папку:

```text
sites/public/.tmp/{slug}
```

После успешного копирования выполнять атомарное переименование в:

```text
sites/public/{slug}
```

Это предотвращает показ частично скопированного сайта.

### Логирование

Добавить структурированные логи с полями:

- `job_id`;
- `lead_id`;
- `landing_id`;
- `queue`;
- `stage`;
- `duration_ms`;
- `error_type`.

### Повторные попытки

Настроить RQ retry для временных ошибок, но не повторять бесконечно ошибки валидации данных.

### Ограничение параллельного deployment

В каждый момент должен выполняться только один Cloudflare deploy. Использовать Redis lock, например:

```text
lock:cloudflare-deploy
```

---

## 14. Приоритет исправлений

### P0 — исправить до дальнейшей разработки

1. Общий bind mount `./sites:/app/sites`.
2. Исправить `.gitignore` или отказаться от Git-публикации сайтов.
3. Согласовать `master`/`main`.
4. Разделить Git push и Wrangler deploy.
5. Проверить полный путь до локального preview.

### P1 — исправить перед VPS production

1. Автоматические миграции.
2. Отдельный deployment stage.
3. Deployment status и ошибки.
4. Защита от одновременного deployment.
5. Улучшенный shell-скрипт.
6. Secrets только через environment.

### P2 — выполнить перед реальным 2GIS

1. GitHub Actions.
2. Структурированные логи.
3. Retry и dead-letter обработка.
4. Атомарная публикация.
5. Интеграционные тесты Docker pipeline.

---

## 15. Критерии готовности этапа стабилизации

Этап считается завершённым, если:

1. Все Python-сервисы и Nginx используют одну локальную директорию `./sites`.
2. После `POST /jobs` сайт физически появляется в `sites/public/{slug}`.
3. Сайт открывается по `http://localhost:8080/{slug}/`.
4. Повторный запуск не создаёт дубли.
5. Миграции применяются до запуска API и workers.
6. Cloudflare deployment запускается отдельно и только один раз на SearchJob.
7. Ветка deployment совпадает с default branch.
8. Скрипты не содержат секретов.
9. CI запускает тесты автоматически.
10. README отражает фактический процесс запуска и deployment.

После выполнения этих пунктов можно переходить к реальному сбору данных 2GIS и генерации контента через OpenAI.
