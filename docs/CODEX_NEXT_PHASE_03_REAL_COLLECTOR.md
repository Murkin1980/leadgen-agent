# Codex Next Phase 03 — Production-ready company collector

## Цель этапа

Подключить реальный источник данных о мебельных компаниях к существующему Leadgen Agent, сохранив mock-режим, тестируемость и безопасную архитектуру.

На этом этапе нужно реализовать реальный collector adapter, проверку наличия рабочего сайта, дедупликацию и устойчивую обработку ошибок. Не использовать обход CAPTCHA, скрытые браузерные профили, ротацию прокси для обхода блокировок или иные способы нарушения ограничений источника.

Предпочтительный порядок источников:

1. официальный API или разрешённый экспорт 2GIS;
2. публичные данные, доступные согласно условиям сервиса;
3. импорт CSV/JSON как резервный production-совместимый источник.

Если официальный доступ к 2GIS не настроен, система должна продолжать работать через `mock` и `csv` providers.

---

## 1. Provider architecture

Расширить конфигурацию:

```env
COLLECTOR_PROVIDER=mock
TWO_GIS_API_KEY=
TWO_GIS_BASE_URL=
COLLECTOR_PAGE_SIZE=20
COLLECTOR_MAX_PAGES=10
COLLECTOR_REQUEST_TIMEOUT=20
COLLECTOR_RATE_LIMIT_PER_SECOND=2
COLLECTOR_MAX_RETRIES=3
COLLECTOR_IMPORT_PATH=/app/import/companies.csv
```

Поддерживаемые providers:

- `mock`
- `two_gis`
- `csv`

Добавить factory:

```python
def get_collector_adapter() -> CollectorAdapter:
    ...
```

Worker не должен напрямую импортировать конкретный adapter.

---

## 2. Collector contract

Сохранить единый интерфейс и добавить явную пагинацию:

```python
class CollectorAdapter(Protocol):
    def search_page(
        self,
        *,
        city: str,
        category: str,
        page: int,
        page_size: int,
    ) -> CollectedPage:
        ...
```

`CollectedPage`:

```python
@dataclass
class CollectedPage:
    items: list[CollectedCompany]
    page: int
    page_size: int
    total: int | None
    has_next: bool
```

`CollectedCompany` должен содержать только нормализованные данные, не сырые ответы поставщика.

Добавить необязательное поле:

```python
raw_payload: dict | None = None
```

По умолчанию сырые данные не сохранять в PostgreSQL. Включать их только при `APP_ENV=development` или отдельной настройке.

---

## 3. TwoGisCollectorAdapter

Реализовать `app/collector/adapters/two_gis.py`.

Требования:

- использовать `httpx.Client` или `httpx.AsyncClient`;
- API key только из окружения;
- base URL только из конфигурации;
- timeout обязателен;
- `User-Agent` должен честно идентифицировать приложение;
- не логировать API key;
- проверять HTTP status;
- корректно обрабатывать malformed JSON;
- преобразовывать ответ через отдельную функцию mapper;
- неизвестные поля источника игнорировать;
- отсутствие необязательного поля не должно ломать импорт.

Создать исключения:

```python
class CollectorError(Exception): ...
class CollectorConfigurationError(CollectorError): ...
class CollectorRateLimitError(CollectorError): ...
class CollectorTemporaryError(CollectorError): ...
class CollectorPermanentError(CollectorError): ...
```

Коды обработки:

- `401/403` → configuration/permanent error;
- `429` → rate-limit error;
- `500–599` → temporary error;
- остальные `400–499` → permanent error.

Не добавлять scraping fallback внутрь `TwoGisCollectorAdapter`.

---

## 4. Retry and rate limiting

Добавить устойчивую политику запросов:

- exponential backoff;
- jitter;
- максимум попыток из конфигурации;
- учитывать `Retry-After`, если он присутствует;
- ограничивать скорость запросов;
- не повторять permanent errors.

Допустимо использовать `tenacity`, либо небольшой собственный модуль.

Все retry должны логироваться структурированно:

```text
collector.request.retry
provider=two_gis
job_id=123
page=2
attempt=2
reason=429
```

Не включать секреты и полный response body в production-логи.

---

## 5. CSV collector

Добавить `CsvCollectorAdapter` как безопасный резервный реальный источник.

Поддержать CSV с колонками:

```text
source_id,name,category,city,address,phone,website,instagram,rating,reviews_count,source_url,latitude,longitude
```

Требования:

- UTF-8 и UTF-8 BOM;
- понятные ошибки при отсутствии обязательных колонок;
- пагинация;
- фильтрация по городу и категории;
- стабильный `source_id`, если он отсутствует — hash нормализованных полей;
- не загружать весь огромный файл в память без необходимости;
- тестовые fixtures.

Добавить volume в Docker Compose:

```yaml
- ./import:/app/import:ro
```

Только сервису collector.

---

## 6. SearchJob progress

Расширить `SearchJob`:

- `provider`
- `current_page`
- `processed_count`
- `skipped_count`
- `duplicate_count`
- `website_check_count`
- `last_heartbeat_at`

Создать Alembic migration `003`.

Обновлять progress после каждой страницы, а не только в конце задания.

`GET /jobs/{id}` должен возвращать эти поля.

При перезапуске worker задание не должно начинаться бесконечно с нуля. Реализовать безопасное продолжение с `current_page`, при этом дедупликация остаётся главным механизмом идемпотентности.

---

## 7. Lead source traceability

Расширить `Lead`:

- `provider`
- `source_updated_at`
- `last_collected_at`
- `website_check_status`
- `website_checked_at`
- `website_final_url`
- `website_http_status`

Не удалять существующие поля `source` и `source_id`, если они используются. Провести аккуратную совместимость или migration данных.

Уникальность должна быть минимум по:

```text
provider + source_id
```

Для CSV fallback без source ID использовать deterministic fingerprint.

---

## 8. Website verification

Наличие строки в поле `website` не означает наличие рабочего сайта.

Создать отдельный модуль:

```text
app/verification/website.py
```

Интерфейс:

```python
class WebsiteVerifier(Protocol):
    def verify(self, url: str) -> WebsiteVerificationResult:
        ...
```

Результат:

```python
@dataclass
class WebsiteVerificationResult:
    original_url: str
    normalized_url: str | None
    final_url: str | None
    status: str
    http_status: int | None
    reachable: bool
    is_placeholder: bool
    error: str | None
```

Статусы:

- `not_provided`
- `reachable`
- `unreachable`
- `invalid_url`
- `placeholder`
- `blocked`
- `unknown`

Правила:

- разрешить только `http` и `https`;
- запретить localhost, private IP, link-local и metadata endpoints;
- ограничить redirects;
- небольшой timeout;
- сначала HEAD, затем при необходимости GET с ограниченным объёмом;
- не скачивать большие файлы;
- не выполнять JavaScript;
- не обходить защиту сайтов;
- добавить SSRF-защиту перед каждым redirect.

Компания считается целевой, если:

- сайт не указан; или
- URL невалиден; или
- сайт недоступен после безопасной проверки; или
- это очевидная страница-заглушка.

Компании с доступным полноценным сайтом не отправлять в генерацию лендинга, но сохранять как rejected/skipped с причиной.

---

## 9. Lead qualification

Создать отдельный сервис:

```text
app/qualification/service.py
```

Он должен возвращать:

```python
@dataclass
class QualificationResult:
    accepted: bool
    reason: str
    score: int
```

Начальные правила scoring:

- название есть: +20;
- телефон есть: +25;
- WhatsApp может быть сформирован: +15;
- мебельная категория подтверждена: +20;
- рейтинг указан: +5;
- отзывы больше нуля: +5;
- рабочего сайта нет: +20;
- рабочий сайт есть: reject;
- нет телефона и других контактов: reject.

Порог должен быть конфигурируемым:

```env
LEAD_MIN_SCORE=50
```

Сохранять в Lead:

- `qualification_score`
- `qualification_reason`

Добавить migration.

---

## 10. Collector worker flow

Обновлённая последовательность:

```text
SearchJob
→ provider factory
→ page collection
→ normalize/map
→ deduplicate/upsert
→ website verification
→ qualification
→ accepted Lead IDs
→ enrich queue
```

Требования:

- commit после каждой страницы;
- отдельная транзакция на страницу;
- одна плохая компания не должна ломать всю страницу;
- ошибки конкретной записи логировать и учитывать в skipped_count;
- provider failure должен корректно завершать SearchJob как failed;
- worker heartbeat;
- лимит задания должен означать число принятых лидов, а не число просмотренных записей;
- прекращать пагинацию при достижении accepted limit или `has_next=False`;
- соблюдать `COLLECTOR_MAX_PAGES`.

---

## 11. API improvements

Расширить `POST /jobs`:

```json
{
  "city": "Алматы",
  "category": "мебель на заказ",
  "limit": 20,
  "provider": "two_gis"
}
```

Если provider не передан, использовать `COLLECTOR_PROVIDER`.

Добавить endpoints:

```http
POST /jobs/{job_id}/retry
POST /jobs/{job_id}/cancel
GET /providers
```

`GET /providers` не должен раскрывать ключи. Пример:

```json
{
  "collectors": [
    {"name": "mock", "configured": true},
    {"name": "csv", "configured": true},
    {"name": "two_gis", "configured": false}
  ]
}
```

Cancel реализовать кооперативно: worker проверяет статус между страницами.

Retry должен создавать новую попытку или безопасно продолжать существующее задание. Не допускать двух активных collector jobs для одного SearchJob.

---

## 12. Structured logging

Добавить единый JSON logger либо структурированный key-value формат.

Обязательные поля:

- `event`
- `job_id`
- `provider`
- `lead_id`, если есть
- `page`, если есть
- `duration_ms`
- `status`

События:

- `collector.job.started`
- `collector.page.started`
- `collector.page.completed`
- `collector.record.skipped`
- `collector.request.retry`
- `collector.job.completed`
- `collector.job.failed`

Не логировать:

- API tokens;
- полный номер телефона в production;
- полный raw payload;
- персональные данные сверх необходимого.

---

## 13. Tests

Добавить unit tests:

- provider factory;
- TwoGIS response mapper;
- HTTP 401/403/429/500 handling;
- retry logic;
- Retry-After handling;
- pagination;
- CSV BOM parsing;
- CSV missing columns;
- deterministic source ID;
- website URL normalization;
- SSRF blocking;
- redirect SSRF blocking;
- reachable/unreachable/placeholder classification;
- qualification score;
- duplicate upsert;
- limit counts accepted leads;
- job cancellation;
- job resume from current page.

Все HTTP tests выполнять через mock transport (`httpx.MockTransport`, `respx` или эквивалент), без реальной сети.

Добавить integration test для CSV provider через Docker pipeline.

CI не должен обращаться к 2GIS или любому внешнему сайту.

---

## 14. Security requirements

Обязательно:

- API keys только через environment/secrets;
- `.env` остаётся в `.gitignore`;
- URL validation и SSRF protection;
- ограничение размера ответов;
- timeout на все сетевые операции;
- rate limiting;
- отсутствие обхода CAPTCHA и anti-bot;
- отсутствие proxy rotation для обхода блокировок;
- отсутствие автоматического сбора запрещённых персональных данных;
- документировать источник данных и правила использования.

Добавить файл:

```text
docs/DATA_SOURCE_POLICY.md
```

В нём описать:

- какие providers поддерживаются;
- какие данные собираются;
- что запрещено;
- как отключить provider;
- как удалить импортированные данные;
- как настроить retention.

---

## 15. README and runbook

Обновить README:

- запуск mock provider;
- запуск CSV provider;
- настройка официального TwoGIS provider;
- пример создания SearchJob;
- просмотр progress;
- retry/cancel;
- диагностика 401, 403, 429, timeout;
- объяснение website verification.

Добавить:

```text
docs/COLLECTOR_RUNBOOK.md
```

Runbook должен содержать:

- health checklist;
- логи и команды Docker;
- повтор задания;
- отключение provider;
- восстановление после rate limit;
- проверку миграций;
- проверку Redis queues.

---

## 16. Acceptance criteria

Этап завершён, если:

1. `COLLECTOR_PROVIDER=mock` продолжает работать без регрессий.
2. `COLLECTOR_PROVIDER=csv` проходит полный pipeline в Docker.
3. `COLLECTOR_PROVIDER=two_gis` требует явной конфигурации и выдаёт понятную ошибку без ключа.
4. Реальные HTTP-вызовы изолированы в adapter.
5. Пагинация и rate limit реализованы.
6. Retry не применяется к permanent errors.
7. SearchJob показывает page/progress counters.
8. Повторный сбор не создаёт дубли.
9. Рабочие сайты корректно исключаются.
10. Website verifier защищён от SSRF.
11. Accepted limit считается по квалифицированным лидам.
12. Cancel и retry работают.
13. Все unit tests проходят без интернета.
14. Docker CSV smoke test проходит.
15. README, DATA_SOURCE_POLICY и COLLECTOR_RUNBOOK обновлены.

---

## 17. Что не делать на этом этапе

- не подключать браузерную автоматизацию;
- не внедрять Playwright/Selenium;
- не обходить CAPTCHA;
- не добавлять proxy rotation;
- не подключать OpenAI;
- не создавать frontend admin panel;
- не делать массовую WhatsApp-рассылку;
- не менять существующий deployment pipeline без необходимости.

---

## Отчёт Codex после выполнения

Предоставить:

1. список изменённых файлов;
2. новые миграции;
3. описание provider architecture;
4. пример CSV;
5. пример запуска каждого provider;
6. результаты unit tests;
7. результат Docker CSV smoke test;
8. перечень ограничений официального TwoGIS provider;
9. подтверждение отсутствия реальных сетевых запросов в CI;
10. оставшиеся задачи для OpenAI enrichment и admin UI.
