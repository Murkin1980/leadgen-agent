# SIMPLICITY_REVIEW.md — Leadgen Agent

**Date:** 2025-07-11
**Status:** Draft

---

## 1. Business Result

**Who:** A solo operator (you) who finds furniture companies in Kazakh cities without websites.

**What action:** Import leads → generate a landing page → get operator approval → publish → send a WhatsApp message → get a reply.

**Measurable result:** At least 1 company replies "да, хочу сайт" (or equivalent) within the first manual run of 10–20 leads.

**Explicitly outside v1:**
- Email/Telegram outreach
- Cloudflare deployment (local nginx preview is enough)
- Prometheus metrics, backup/restore, data retention
- API key management, pilot mode, readiness probes
- Multi-city, multi-category scaling
- Automated follow-ups
- CRM stage automation

**Manual during validation:**
- Operator manually reviews each landing before approve
- Operator manually reviews each message before send
- Operator manually checks WhatsApp for replies
- Operator manually runs the pipeline (no background scheduling)

---

## 2. Approaches Researched

### Approach A: Full manual (spreadsheet + WhatsApp Web)
- **Setup:** 0 minutes
- **Moving parts:** 0 (just a browser)
- **Maintenance:** None
- **Cost:** Free
- **Failure modes:** Human error, slow, doesn't scale
- **Dependencies:** None
- **Validates:** Do companies without websites want a free landing page?

### Approach B: Current simplified MVP (6 Docker services)
- **Setup:** `docker compose up --build` (5–10 min first time)
- **Moving parts:** 6 containers (postgres, redis, migrate, api, worker, preview)
- **Maintenance:** Low — all runs locally
- **Cost:** Free (local)
- **Failure modes:** Docker issues, port conflicts
- **Dependencies:** Python, Docker, Node.js (for wrangler)
- **Validates:** Same question + can the pipeline be automated?

### Approach C: Current full architecture (15+ services, production features)
- **Setup:** Docker + Cloudflare + WhatsApp API + OpenAI
- **Moving parts:** 15+ containers, 3+ external APIs
- **Maintenance:** High — monitoring, backups, retention, keys
- **Cost:** WhatsApp API, OpenAI, Cloudflare
- **Failure modes:** API rate limits, webhook issues, deployment failures
- **Dependencies:** Docker, Cloudflare, Meta, OpenAI, Redis, PostgreSQL
- **Validates:** Everything — but overkill for first validation

**Choice: Approach B** — but even simpler. See pass 1.

---

## 3. Simplification Pass 1: Remove Speculative Scope

**Remove from MVP:**

| Component | Why remove |
|-----------|-----------|
| `app/metrics.py` + `/metrics` endpoint | No monitoring needed for 10 manual leads |
| `app/backup.py` + `/api/v1/backup/*` | 10 leads don't need pg_dump |
| `app/retention.py` + `/api/v1/retention/*` | Data purge irrelevant at this scale |
| `app/api_keys.py` + `/api/v1/api-keys/*` | Solo operator, no API key auth needed |
| `app/pilot.py` + `/api/v1/pilot/*` | Kill switch for hypothetical scale |
| `app/outreach/dead_letter.py` + routes | Dead-letter queue for <10 messages |
| `app/outreach/inbox.py` + production routes | Dedicated inbox API — admin panel suffices |
| `app/outreach/template_sync.py` | Meta template sync — templates are hardcoded |
| `app/api/production_routes.py` (entire file) | All 20+ production endpoints unused |
| `app/models/api_key.py` + migration 007 | API key model unused |
| Cloudflare deployment (`app/deployment/`) | Local preview is enough |
| `Dockerfile.deployer` (already deleted) | — |
| Advanced profile services (8 workers) | Unified worker handles everything |
| `wrangler.jsonc`, `package.json`, `node_modules/` | No Cloudflare deployment in MVP |

**Keep:** Everything that touches the actual workflow (collect → generate → approve → publish → send → receive).

---

## 4. Simplification Pass 2: Combine Components

| Current | Simplify to |
|---------|------------|
| 14 database tables | **6 tables**: leads, landing_pages, content_generations, outreach_campaigns, outreach_messages, inbound_messages |
| 100+ API endpoints | **~25 endpoints** (health, leads CRUD, landings CRUD, messages CRUD, webhooks) |
| 7 Alembic migrations | **4 migrations** (initial, outreach, whatsapp, drop unused) |
| Separate admin HTML + API routes | **One admin panel** with embedded actions (approve/reject/send) |
| `outreach_routes.py` + `whatsapp_routes.py` + `production_routes.py` + `routes.py` | **One `routes.py`** with all needed endpoints |
| 6 worker queues + unified worker | **1 worker** processing 3 queues: `collect`, `generate`, `outreach` |
| Template + OpenAI + Mock generators | **Template only** (OpenAI is optional, mock is for tests) |
| Mock + WhatsApp + Email + Telegram providers | **Mock + WhatsApp** (email/telegram already deleted) |
| CSRF + audit logging + webhook signatures | **CSRF only** (audit and signatures for production) |

---

## 5. Simplification Pass 3: Remove Dependencies

| Dependency | Keep? | Reason |
|------------|-------|--------|
| `fastapi` | Yes | Core framework |
| `uvicorn` | Yes | ASGI server |
| `sqlalchemy` | Yes | ORM |
| `psycopg` | Yes | PostgreSQL driver |
| `alembic` | Yes | Migrations |
| `redis` + `rq` | Yes | Job queue |
| `pydantic` + `pydantic-settings` | Yes | Config/validation |
| `jinja2` | Yes | Landing page templates |
| `httpx` | Yes | HTTP client for verification + WhatsApp |
| `tenacity` | Yes | Retry for WhatsApp API |
| `wrangler` (Node.js) | **Remove** | No Cloudflare in MVP |
| `prometheus_client` (implicit in metrics) | **Remove** | Not needed |

---

## 6. Simplification Pass 4: Operational Reality

**How is it started?**
```bash
docker compose up --build
```

**How is it stopped?**
```bash
docker compose down
```

**How is it configured?**
Copy `.env.mvp.example` to `.env`, edit 3 values (admin password, CSV file path).

**How is a failure diagnosed?**
`docker compose logs api` and `docker compose logs worker`.

**How is data backed up?**
Not needed for validation. `test.db` is disposable.

**How is the system restored?**
`docker compose down -v && docker compose up --build` (recreate from scratch).

**How many commands for a new operator?**
2: `cp .env.mvp.example .env` then `docker compose up --build`.

**How many services must be healthy?**
4: postgres, redis, api, worker. (preview is optional, migrate is one-shot.)

---

## 7. Simplicity Score

| Criterion | Score | Notes |
|-----------|-------|-------|
| One clear business outcome | 2 | "Get a reply from a lead" |
| Minimal number of services | 1 | 4 containers (postgres, redis, api, worker) |
| Minimal number of dependencies | 2 | 10 Python packages, all essential |
| One obvious deployment path | 2 | `docker compose up --build` |
| Easy local start | 2 | 2 commands |
| Easy rollback | 2 | `docker compose down -v` |
| Manual fallback exists | 2 | Spreadsheet + WhatsApp Web |
| No speculative features | 1 | Some production code still present |
| Understandable by one developer | 2 | Single repo, single stack |
| Testable end to end | 2 | 261 tests, MVP flow test |
| **Total** | **18/20** | Proceed |

---

## 8. Final MVP Workflow

```
1. cp .env.mvp.example .env
2. docker compose up --build
3. Import CSV leads: POST /jobs (or CSV auto-import)
4. Review leads: GET /admin/leads
5. Generate landing: POST /leads/{id}/content-generations
6. Review landing: GET /admin/landings/{id}
7. Approve: POST /admin/landings/{id}/approve
8. Publish: POST /landings/{id}/publish
9. Create campaign: POST /campaigns
10. Add leads: POST /campaigns/{id}/add-leads
11. Generate messages: POST /campaigns/{id}/generate-messages
12. Review message: GET /admin/messages/{id}
13. Approve: POST /admin/messages/{id}/approve
14. Send: POST /admin/messages/{id}/send
15. Check WhatsApp for reply
16. Mark handled: POST /inbound-messages/{id}/mark-handled
```

**Total: 16 steps, all manual, all visible in admin panel.**

---

## 9. Components Kept

| Component | Why |
|-----------|-----|
| `app/api/routes.py` | Core API (leads, landings, content, publish) |
| `app/api/outreach_routes.py` | Campaign/message CRUD |
| `app/api/whatsapp_routes.py` | WhatsApp webhooks + inbound |
| `app/api/admin.py` | Admin HTML panel (5 tabs) |
| `app/collector/` | CSV + mock data import |
| `app/enrichment/` | Lead enrichment (slug, phone, WhatsApp URL) |
| `app/generation/` | Template content generation |
| `app/landing/` | Jinja2 landing page rendering |
| `app/publisher/` | File-copy publish to sites/public |
| `app/outreach/` | WhatsApp provider, templates, stages |
| `app/qualification/` | Lead scoring |
| `app/verification/` | Website SSRF-protected check |
| `app/workers/` | Unified worker (collect, generate, outreach) |
| `app/security/` | CSRF protection |
| `app/models/` | 6 core tables |
| `app/config.py` | Environment configuration |
| `app/database.py` | SQLAlchemy setup |
| `app/main.py` | FastAPI app |
| `templates/landing.html` | Landing page template |
| `import/companies.csv` | Test data |
| `docker-compose.yml` | 4-service default profile |
| `Dockerfile` | Python app container |
| `.env.mvp.example` | Minimal config |

---

## 10. Components Postponed (not deleted, just not in MVP default)

| Component | When to add |
|-----------|------------|
| Cloudflare deployment | After first successful manual run |
| OpenAI generation | After template proves the concept |
| API key auth | When exposing API to others |
| Prometheus metrics | When running in production |
| Backup/retention | When data has real value |
| Pilot mode / kill switch | When sending to real leads at scale |
| Dead-letter handling | When message volume >50/day |
| Email/Telegram providers | When WhatsApp proves insufficient |
| Multi-city support | After Almaty validation |
| Automated follow-ups | After first reply received |

---

## 11. Components Rejected

| Component | Why |
|-----------|-----|
| Microservices architecture | One monolith is enough |
| Event bus / message broker | RQ + Redis is sufficient |
| Separate frontend (React/Vue) | Admin HTML panel works |
| Kubernetes deployment | Docker Compose is enough |
| Multi-tenant support | Solo operator |
| Real-time dashboards | Admin panel + logs suffice |
| Automated A/B testing | Manual comparison is enough |
| CRM integration (HubSpot etc.) | Custom admin panel is the CRM |

---

## 12. Risks and Manual Fallback

| Risk | Mitigation | Fallback |
|------|-----------|----------|
| Docker won't start | Check ports, Docker Desktop running | Run locally with `uvicorn` |
| PostgreSQL connection fails | Check `.env` DATABASE_URL | Use SQLite for testing |
| WhatsApp API rate limit | Mock provider for testing | Send manually via WhatsApp Web |
| Landing page looks wrong | Review in admin panel before publish | Edit `profile_json` manually |
| No replies from leads | Try different message templates | Call companies by phone |
| 2GIS API blocked | Use CSV import | Manually enter leads |

---

## 13. Criteria for Adding Complexity Later

Complexity may be added ONLY when:

1. **Measured load:** >100 leads/day requires separate workers
2. **Real failure:** WhatsApp delivery fails repeatedly → add retry/dead-letter
3. **Legal/compliance:** GDPR opt-out → add consent management
4. **Confirmed demand:** Operator says "I need email outreach too" → add email provider
5. **Proven maintenance pain:** Manual deploy is tedious → add Cloudflare automation

Each addition requires updating this review with evidence.
