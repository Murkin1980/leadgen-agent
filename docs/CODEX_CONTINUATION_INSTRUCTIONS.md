# Codex Task — стабилизация Leadgen Agent и подготовка к реальному 2GIS

## Контекст

В репозитории уже реализован MVP Leadgen Agent:

- FastAPI;
- PostgreSQL;
- SQLAlchemy 2.x;
- Alembic;
- Redis + RQ;
- workers `collector`, `enricher`, `generator`, `publisher`;
- mock collector;
- enrichment;
- JSON profile generation;
- Jinja2 landing renderer;
- локальная публикация в `sites/public`;
- Nginx preview;
- Cloudflare Pages deployment через Wrangler;
- pytest-тесты.

Перед подключением реального 2GIS необходимо исправить инфраструктуру и доказать, что сквозной pipeline работает стабильно.

Используй документ:

```text
docs/REPOSITORY_RECOMMENDATIONS.md
```

как источник требований и обоснований.

---

# Главная цель

Реализовать этап стабилизации:

```text
POST /jobs
→ collect
→ enrich
→ generate
→ publish locally
→ complete SearchJob
→ optional Cloudflare deploy
```

После выполнения:

- локально сгенерированные сайты должны физически появляться в `./sites/public`;
- Nginx должен сразу видеть опубликованные сайты;
- миграции должны применяться безопасно;
- Cloudflare deployment должен быть отделён от Git push;
- deployment должен выполняться один раз на задание, а не после каждого лида;
- CI должен автоматически проверять проект.

Не подключай реальный 2GIS в рамках этой задачи.

---

# 1. Исправить Docker volumes

Открой `docker-compose.yml`.

Для сервисов:

- `api`;
- `collector`;
- `enricher`;
- `generator`;
- `publisher`;

замени named volume:

```yaml
volumes:
  - sites:/app/sites
```

на bind mount:

```yaml
volumes:
  - ./sites:/app/sites
```

Для `preview` сохрани:

```yaml
volumes:
  - ./sites/public:/usr/share/nginx/html:ro
```

Из нижней секции удалить:

```yaml
sites:
```

Оставить:

```yaml
volumes:
  pgdata:
```

Добавь каталоги:

```text
sites/drafts/.gitkeep
sites/public/.gitkeep
```

Проверь, что каталоги создаются автоматически при первом запуске, даже если `.gitkeep` отсутствует.

---

# 2. Исправить `.gitignore`

Оставь исключённой временную директорию:

```gitignore
sites/drafts/*
!sites/drafts/.gitkeep
```

Для `sites/public` выбери один прозрачный режим.

## Рекомендуемый режим

Не хранить generated sites в основной ветке репозитория.

Использовать:

```gitignore
sites/public/*
!sites/public/.gitkeep
```

При этом `scripts/publish_to_git.sh` больше не должен пытаться коммитить `sites/public` по умолчанию.

Если скрипт оставляется как резервный, он должен:

- явно требовать переменную `ALLOW_GENERATED_SITE_GIT_PUSH=true`;
- завершаться с понятным сообщением без этой переменной;
- использовать `git add -f sites/public` только после явного разрешения;
- не запускать Cloudflare deploy.

---

# 3. Разделить Git push и Cloudflare deploy

Исправь `scripts/publish_to_git.sh`.

Он не должен вызывать:

```bash
npx wrangler pages deploy
```

Cloudflare deployment должен оставаться только в:

```text
scripts/deploy_cloudflare.sh
```

Обнови оба скрипта так, чтобы их назначение было однозначным.

## `publish_to_git.sh`

Назначение:

- ручной резервный экспорт generated sites в Git;
- по умолчанию отключён;
- не вызывается worker-ами;
- не выполняет Cloudflare deployment.

## `deploy_cloudflare.sh`

Назначение:

- deployment текущей директории `sites/public` в Cloudflare Pages;
- не выполняет `git add`, `git commit` или `git push`.

---

# 4. Усилить `deploy_cloudflare.sh`

Перепиши скрипт с:

```bash
set -Eeuo pipefail
```

Скрипт должен:

1. перейти в корень репозитория;
2. проверить наличие `npx`;
3. проверить наличие `sites/public`;
4. проверить, что в `sites/public` есть хотя бы один `index.html`;
5. прочитать project name и branch из environment;
6. использовать default branch `master`;
7. не хранить API token в коде;
8. возвращать ненулевой exit code при ошибке;
9. выводить понятные сообщения;
10. не печатать секреты.

Использовать переменные:

```env
CLOUDFLARE_PAGES_PROJECT=leadgen-agent
CLOUDFLARE_PAGES_BRANCH=master
CLOUDFLARE_PAGES_URL=https://leadgen-agent.pages.dev
```

Команда deployment:

```bash
npx wrangler pages deploy sites/public \
  --project-name "$CLOUDFLARE_PAGES_PROJECT" \
  --branch "$CLOUDFLARE_PAGES_BRANCH" \
  --commit-dirty=true
```

Не хардкодить production URL в echo. Выводить `CLOUDFLARE_PAGES_URL`, только если переменная задана.

---

# 5. Обновить `.env.example`

Добавь:

```env
CLOUDFLARE_PAGES_PROJECT=leadgen-agent
CLOUDFLARE_PAGES_BRANCH=master
CLOUDFLARE_PAGES_URL=https://leadgen-agent.pages.dev

# Set only on VPS or CI secrets. Never commit a real token.
CLOUDFLARE_API_TOKEN=
CLOUDFLARE_ACCOUNT_ID=
```

Не добавляй реальные secrets.

Проверь, что конфигурация приложения не падает, если Cloudflare-переменные отсутствуют и deployment не запускается.

---

# 6. Автоматизировать миграции

Добавь отдельный Compose service:

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

`api` и workers должны запускаться после успешной миграции.

Используй поддерживаемый текущей версией Docker Compose способ зависимости от успешно завершившегося `migrate`.

Если `condition: service_completed_successfully` доступен, используй его.

Не запускай Alembic отдельно в каждом worker.

Проверь повторный запуск:

```bash
docker compose up -d
```

Он не должен ломаться, если миграции уже применены.

---

# 7. Добавить deployment stage

Добавь новую RQ queue:

```text
deploy
```

Добавь worker service:

```text
deployer
```

Но deployment не должен автоматически выполняться для каждого `LandingPage`.

## Требуемая логика

1. `publisher` публикует каждый лендинг локально.
2. После завершения публикации всех принятых лидов `SearchJob` получает статус `completed`.
3. Cloudflare deployment можно запустить:
   - вручную через API;
   - либо автоматически один раз после завершения SearchJob, если включена настройка.

Добавь env:

```env
AUTO_DEPLOY_CLOUDFLARE=false
```

По умолчанию deployment отключён.

Если `AUTO_DEPLOY_CLOUDFLARE=true`, после полного завершения SearchJob поставить одну задачу в queue `deploy`.

Используй Redis lock:

```text
lock:cloudflare-deploy
```

Одновременно может выполняться только один deployment.

Lock должен иметь TTL, чтобы не остаться навсегда после аварии worker.

---

# 8. Добавить API для ручного deployment

Добавь endpoint:

```http
POST /deploy/cloudflare
```

Тело запроса:

```json
{
  "search_job_id": 1
}
```

Поведение:

- проверить существование SearchJob;
- разрешить deployment только после завершения генерации и локальной публикации;
- поставить одну задачу в queue `deploy`;
- не запускать shell-команду внутри HTTP request;
- вернуть ID RQ job и статус `queued`.

Пример ответа:

```json
{
  "status": "queued",
  "search_job_id": 1,
  "deployment_job_id": "..."
}
```

Добавь endpoint статуса:

```http
GET /deploy/cloudflare/{deployment_job_id}
```

Вернуть:

- `queued`;
- `started`;
- `completed`;
- `failed`;
- error message;
- timestamps.

Не возвращать secrets или environment dump.

---

# 9. Хранение статуса deployment

Создай модель `Deployment`.

Поля:

- `id` — UUID/string;
- `search_job_id` — FK;
- `provider` — `cloudflare_pages`;
- `status`;
- `project_name`;
- `branch`;
- `deployment_url`;
- `error_message`;
- `created_at`;
- `started_at`;
- `completed_at`.

Статусы:

- `queued`;
- `running`;
- `completed`;
- `failed`.

Добавь Alembic migration.

Не сохраняй API token.

---

# 10. Безопасный запуск shell deployment

Создай Python service, например:

```text
app/deployment/cloudflare.py
```

Он должен:

- запускать `scripts/deploy_cloudflare.sh` через `subprocess.run`;
- не использовать `shell=True`;
- устанавливать timeout;
- захватывать stdout/stderr;
- ограничивать размер сохраняемого error output;
- обновлять Deployment status;
- обрабатывать timeout;
- освобождать Redis lock в `finally`.

Пример безопасного вызова:

```python
subprocess.run(
    ["bash", "scripts/deploy_cloudflare.sh"],
    cwd=project_root,
    env=allowed_env,
    capture_output=True,
    text=True,
    timeout=settings.cloudflare_deploy_timeout,
    check=False,
)
```

Не передавать весь `os.environ` без необходимости. Сформировать разрешённый набор переменных.

---

# 11. Атомарная локальная публикация

Исправь publisher.

Вместо прямого копирования в:

```text
sites/public/{slug}
```

используй:

```text
sites/public/.tmp/{slug}-{unique-id}
```

Алгоритм:

1. создать временную директорию;
2. скопировать все файлы;
3. проверить наличие `index.html`;
4. удалить старую целевую директорию безопасным способом;
5. атомарно переименовать временную директорию в `{slug}`;
6. очистить временные данные при ошибке.

Проверь защиту от path traversal.

Slug должен быть только безопасным именем директории.

После `resolve()` итоговый путь должен оставаться внутри `sites/public`.

---

# 12. Идемпотентность pipeline

Проверь и исправь:

- повторный SearchJob не создаёт дубль по `source + source_id`;
- повторный enrichment обновляет существующий Lead;
- повторный generate не создаёт бесконтрольно новые LandingPage;
- повторный publish заменяет существующий сайт атомарно;
- повторный deploy создаёт новую Deployment запись, но не повреждает предыдущую;
- одновременно одинаковый SearchJob не ставится в deploy несколько раз.

Добавь уникальные ограничения или application-level guards там, где это необходимо.

---

# 13. Корректное завершение SearchJob

Проверь текущую цепочку статусов.

SearchJob должен становиться `completed` только когда:

- collector завершён;
- все принятые Lead прошли enrichment;
- все принятые Lead получили LandingPage;
- все LandingPage локально опубликованы;
- ошибки отдельных лидов корректно учтены.

Не завершать SearchJob после публикации первого лида.

Добавь понятную агрегацию:

- `found_count`;
- `accepted_count`;
- `enriched_count`;
- `generated_count`;
- `published_count`;
- `failed_count`.

Если изменение модели слишком крупное, минимум вычислять эти значения через запросы и возвращать в Job response.

---

# 14. GitHub Actions CI

Добавь:

```text
.github/workflows/ci.yml
```

Запускать на:

- push в `master`;
- pull request в `master`.

Workflow должен:

1. checkout;
2. установить Python 3.12;
3. кешировать pip;
4. установить зависимости;
5. запустить `python -m compileall app`;
6. запустить `pytest -q`;
7. запустить `docker compose config`.

Добавь Ruff, если он не ломает текущий проект:

```bash
ruff check .
ruff format --check .
```

Если добавляешь Ruff:

- зафиксируй версию;
- добавь конфигурацию в `pyproject.toml`;
- исправь найденные ошибки;
- не отключай проверки глобально без причины.

CI не должен выполнять production Cloudflare deployment.

---

# 15. Тесты

Добавь тесты минимум для:

## Docker/path behavior

- drafts и public используют ожидаемые локальные пути;
- publisher создаёт сайт в `sites/public/{slug}`;
- повторный publish корректно заменяет сайт;
- временная папка очищается после ошибки;
- path traversal блокируется.

## Deployment

- endpoint ставит задачу в queue;
- deployment запрещён для незавершённого SearchJob;
- одновременно не запускаются два deployment;
- успешный subprocess меняет статус на `completed`;
- ошибка subprocess меняет статус на `failed`;
- timeout корректно обрабатывается;
- secrets не попадают в error message.

## Pipeline

- SearchJob не становится completed после первого published lead;
- SearchJob становится completed после всех лидов;
- deployment ставится один раз при `AUTO_DEPLOY_CLOUDFLARE=true`;
- deployment не ставится при false.

Все тесты должны использовать mocks и не обращаться к реальному Cloudflare.

---

# 16. Обновить README

README должен содержать фактический процесс запуска.

## Локальный запуск

```bash
cp .env.example .env
docker compose up --build -d
docker compose ps
curl http://localhost:8000/health
```

Миграции должны применяться автоматически через `migrate`.

## Создание задания

Оставить рабочий пример `POST /jobs`.

## Просмотр сайта

```text
http://localhost:8080/{slug}/
```

## Ручной Cloudflare deployment

Через API:

```bash
curl -X POST http://localhost:8000/deploy/cloudflare \
  -H "Content-Type: application/json" \
  -d '{"search_job_id": 1}'
```

И резервная команда:

```bash
bash scripts/deploy_cloudflare.sh
```

Объяснить, что:

- локальная публикация и Cloudflare deployment — разные этапы;
- generated sites по умолчанию не коммитятся в основную ветку;
- токены задаются только на VPS или в secrets.

---

# 17. Обновить архитектурную документацию

Добавь файл:

```text
docs/DEPLOYMENT_ARCHITECTURE.md
```

Опиши:

```text
Generator
→ sites/drafts/{slug}
→ Publisher
→ sites/public/{slug}
→ Nginx local preview
→ optional Deploy Queue
→ Wrangler
→ Cloudflare Pages
```

Отдельно опиши:

- отличие `published locally` от `deployed`;
- Redis lock;
- ручной и автоматический режим;
- хранение статусов;
- обработку ошибок.

---

# 18. Не выполнять в этом этапе

Не делай следующее:

- не подключай реальный парсинг 2GIS;
- не используй неофициальные обходы CAPTCHA;
- не добавляй proxy rotation;
- не подключай OpenAI production calls;
- не создавай frontend admin panel;
- не меняй дизайн landing template без необходимости;
- не выполняй реальный Cloudflare deployment во время тестов;
- не коммить API tokens;
- не переписывай рабочие модули полностью без причины.

---

# 19. Команды проверки

После реализации выполни:

```bash
python -m compileall app
pytest -q
docker compose config
docker compose down -v
docker compose up --build -d
docker compose ps
curl http://localhost:8000/health
```

Создай тестовое задание:

```bash
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "city": "Алматы",
    "category": "мебель на заказ",
    "limit": 10
  }'
```

Проверь:

```bash
find sites/drafts -maxdepth 2 -type f
find sites/public -maxdepth 2 -type f
```

Проверь локальный URL:

```text
http://localhost:8080/{slug}/
```

Не запускай реальный Cloudflare deploy без доступных secrets.

---

# 20. Критерии готовности

Задача считается выполненной, если:

1. `docker compose up --build -d` запускает стек без ручного Alembic.
2. Все сервисы используют общий каталог `./sites`.
3. После задания HTML появляется в `sites/public/{slug}`.
4. Nginx показывает этот HTML.
5. `publish_to_git.sh` не запускает Wrangler.
6. `deploy_cloudflare.sh` не выполняет Git операции.
7. Используется ветка `master` либо централизованная env-настройка.
8. Cloudflare deployment имеет отдельную queue и модель статуса.
9. Deployment выполняется максимум один одновременно.
10. Автоматический deploy по умолчанию выключен.
11. Publisher работает атомарно и защищён от path traversal.
12. SearchJob завершается только после всех локальных публикаций.
13. Тесты проходят.
14. CI проходит.
15. README и архитектурная документация обновлены.

---

# 21. Формат отчёта Codex

После выполнения предоставь:

1. краткое резюме изменений;
2. список изменённых файлов;
3. список новых миграций;
4. описание нового deployment flow;
5. команды запуска;
6. результаты тестов;
7. результат `docker compose config`;
8. результат сквозного mock pipeline;
9. известные ограничения;
10. следующий рекомендуемый этап.

Следующим этапом после успешной стабилизации будет отдельная задача по подключению официального или разрешённого источника данных 2GIS с rate limiting, кэшированием, аудитом источника и проверкой наличия действующего сайта.
