# Leadgen Agent — MVP

Simple pipeline: import companies → filter without sites → generate landing → approve → publish → send WhatsApp message → get reply.

## Quick Start

```bash
cp .env.mvp.example .env
docker compose up --build
# API: http://localhost:8000
# Preview: http://localhost:8080
# Admin: http://localhost:8000/admin/leads
```

6 services: postgres, redis, migrate, api, worker, preview.

## Architecture

```
CSV/mock → POST /jobs → Worker [collect]
  → Leads
    → POST /leads/{id}/content-generations → Worker [generate_content]
      → Landing (needs_review)
        → POST /landings/{id}/approve
          → POST /landings/{id}/publish
            → sites/public/{slug}/ → Nginx :8080
  → POST /outreach-messages/{id}/approve
    → POST /outreach-messages/{id}/send → Mock/WhatsApp
      → POST /webhooks/whatsapp → Lead stage = replied
```

## MVP Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check |
| POST | `/jobs` | Create collection job |
| GET | `/jobs/{id}` | Get job status |
| GET | `/leads` | List leads |
| GET | `/leads/{id}` | Lead detail |
| POST | `/leads/{id}/content-generations` | Generate landing content |
| GET | `/landings` | List landings |
| GET | `/landings/{id}` | Landing detail |
| POST | `/landings/{id}/approve` | Approve landing |
| POST | `/landings/{id}/publish` | Publish landing |
| GET | `/outreach-messages` | List outreach messages |
| POST | `/outreach-messages/{id}/approve` | Approve message |
| POST | `/outreach-messages/{id}/send` | Send message |
| GET | `/inbound-messages` | List inbound messages |
| POST | `/webhooks/whatsapp` | WhatsApp webhook |

## Admin UI

- `/admin/leads` — All leads
- `/admin/landings` — Landings on review
- `/admin/messages` — Messages on approval
- `/admin/inbox` — Inbound responses
- `/admin/settings` — MVP settings

## Environment

See `.env.mvp.example` for the minimal set of variables.

| Variable | Default | Description |
|---|---|---|
| `COLLECTOR_PROVIDER` | `csv` | `mock`, `csv`, `two_gis` |
| `TEXT_GENERATOR_PROVIDER` | `template` | `template`, `mock`, `openai` |
| `OUTREACH_PROVIDER` | `mock` | `mock`, `whatsapp` |
| `OUTREACH_MODE` | `disabled` | `disabled`, `sandbox`, `production` |
| `ADMIN_PASSWORD` | — | Required |

## Tests

```bash
TEXT_GENERATOR_PROVIDER=mock DEPLOYMENT_PROVIDER=mock pytest tests/ -v
```

### MVP Smoke Test

```bash
# In Docker:
bash scripts/mvp_smoke_test.sh

# Or standalone:
python -m pytest tests/test_mvp_flow.py -v
```

## Advanced Mode

To run all services (legacy architecture):

```bash
docker compose --profile advanced up --build
```

This enables: collector, enricher, generator, content-generator, publisher, deployer, outreach-generator, outreach-sender, outreach-status workers.

## Project Structure

```
app/
├── api/
│   ├── routes.py              # Core API
│   ├── outreach_routes.py     # Outreach API
│   ├── whatsapp_routes.py     # WhatsApp webhook
│   ├── production_routes.py   # Phase 07 features
│   └── admin.py               # Admin UI (5 tabs)
├── collector/                 # CSV, mock, 2GIS adapters
├── generation/                # Template, mock, OpenAI providers
├── landing/                   # Landing page schema + renderer
├── models/                    # SQLAlchemy models
├── outreach/                  # WhatsApp, mock providers
├── publisher/                 # Local site publisher
├── workers/                   # RQ workers
├── config.py                  # Settings
├── database.py                # SQLAlchemy engine
├── metrics.py                 # Prometheus metrics
├── pilot.py                   # Pilot mode safeguards
├── api_keys.py                # API key management
├── retention.py               # Data retention
├── backup.py                  # Backup/restore
└── main.py                    # FastAPI app

alembic/versions/              # 001-007 migrations
tests/                         # 245+ tests
```

## Migrations

```bash
# Check migration chain
python scripts/check_migrations.py

# Manual migration
alembic upgrade head
alembic downgrade -1
```
