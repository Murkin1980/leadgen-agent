# MVP Simplification Report

## Goal

Reduce the default `docker compose up --build` from 15 services to 6, without deleting code that works. Verify the simplified MVP works end-to-end, then remove unused components.

## What Changed

### Commit 1: `3bb1f5c` — Safe Disable (profiles, UI, config)

| Area | Before | After |
|------|--------|-------|
| Docker services | 15 services (all started) | 6 default + 9 in `advanced` profile |
| Admin UI tabs | 11 tabs | 5 tabs (Leads, Landings, Messages, Inbox, Settings) |
| Workers | 9 separate RQ workers | 1 unified worker (6 queues) |
| Config | 60+ env vars | `.env.mvp.example` with 20 vars |
| README | Enterprise-oriented | MVP quick start |

**Default services (start with `docker compose up --build`):**
- `postgres` — PostgreSQL 16
- `redis` — Redis 7
- `migrate` — Alembic migrations
- `api` — FastAPI application
- `worker` — Unified RQ worker (collect, enrich, generate_content, publish, outreach_generate, outreach_send)
- `preview` — Static preview server (nginx)

**Advanced services (start with `docker compose --profile advanced up --build`):**
- `collector`, `enricher`, `generator`, `content-generator`, `publisher`, `deployer`, `outreach-generator`, `outreach-sender`

**No code deleted.** All backend routes, models, and logic remain untouched.

### Commit 2: `dd52b95` — Remove Verified Unused Components

After Commit 1 was verified (261 tests pass, no syntax errors), the following were deleted:

| File | Reason |
|------|--------|
| `app/outreach/email_provider.py` | Stub — raises `NotImplementedError`, never used in MVP |
| `app/outreach/telegram_provider.py` | Stub — raises `NotImplementedError`, never used in MVP |
| `app/workers/generator_worker.py` | Legacy pipeline — replaced by `content_generator_worker.py` |
| `app/workers/outreach_status_worker.py` | Polling worker — not used in MVP |
| `Dockerfile.deployer` | Legacy Cloudflare deployment config |

**Cleanup:**
- Removed email/telegram from `outreach/factory.py` provider map
- Removed email/telegram from `outreach/__init__.py` exports
- Removed legacy `generator_worker` enqueue from `enricher_worker.py`
- Removed `outreach-status` service from `docker-compose.yml`
- Added `test_mvp.db` to `.gitignore`

## Architecture

```
┌─────────────────────────────────────────────┐
│              docker compose up               │
│                                              │
│  postgres ─► migrate ─► api ─► worker       │
│                  │              │             │
│  redis ◄─────────┘              │             │
│                                 │             │
│  preview (nginx, sites/public)  │             │
│                                 │             │
│  Worker queues:                │             │
│  collect, enrich,              │             │
│  generate_content, publish,    │             │
│  outreach_generate,            │             │
│  outreach_send                 │             │
└─────────────────────────────────────────────┘

Admin UI: http://localhost:8000/admin
API docs: http://localhost:8000/docs
Preview:  http://localhost:3000
```

## MVP Workflow

```
1. POST /api/v1/leads (or /collect/start)  →  Lead created (status: collected)
2. POST /api/v1/leads/{id}/enrich           →  Lead enriched (status: enriched)
3. POST /api/v1/content/generate            →  Content generated (status: generated)
4. GET  /admin/landings/{id}                →  Review landing
5. POST /admin/landings/{id}/approve        →  Landing approved
6. POST /admin/landings/{id}/publish        →  Landing published
7. POST /api/v1/campaigns/{id}/messages     →  Message created
8. POST /admin/messages/{id}/approve        →  Message approved
9. POST /admin/messages/{id}/send           →  Message sent via WhatsApp
```

## Tests

- **261 tests pass** (SQLite)
- MVP flow test: 10-step happy path (lead → generate → approve → publish → message → approve → send → inbound reply)
- Enterprise modules hidden test: verifies production modules don't load in default import
- All existing tests continue to pass

## Files Created/Modified

| File | Action |
|------|--------|
| `docker-compose.yml` | Rewritten — profiles, unified worker |
| `.env.mvp.example` | Created — minimal MVP config |
| `README.md` | Rewritten — MVP quick start |
| `app/api/admin.py` | Rewritten — 5 MVP tabs |
| `tests/test_mvp_flow.py` | Created — MVP happy-path test |
| `scripts/mvp_smoke_test.sh` | Created — Docker smoke test |
| `docs/MVP_SIMPLIFICATION_REPORT.md` | Created — this document |

## Reversibility

All changes are fully reversible:
- **Commit 1:** Revert profiles in `docker-compose.yml` to start all services
- **Commit 2:** `git revert` restores deleted files
- No migrations were added or modified
- No database schema changes
- No API endpoint changes
