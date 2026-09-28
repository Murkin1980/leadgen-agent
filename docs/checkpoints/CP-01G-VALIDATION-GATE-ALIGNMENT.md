# CP-01G — Validation Gate Alignment

**Date:** 2026-09-28

**Scope:** Validation-gate alignment and evidence, plus narrowly scoped reachable security/runtime-correctness fixes; no architecture, infrastructure, schema, or dependency changes.

**Result:** **CP-01G PASS** for the locally available scope, coverage, lint-regression, security, SQLite, and automated MVP checks. **CP-01 remains BLOCKED** pending live PostgreSQL and Docker validation. CP-01G does not convert CP-01 to PASS.

## 1. Decision and evidence basis

The earlier whole-repository gates measured optional/production modules as if they were all part of the approved MVP. The adopted scope follows the canonical flow in `SIMPLICITY_REVIEW.md` §§8–10: CSV/mock lead import → template content generation → operator review → local static publish → WhatsApp message generation/approval/send → inbound reply. The flow and deferred components are also recorded in `docs/checkpoints/CP-00-BASELINE.md` and `docs/checkpoints/CP-01-STABILIZATION-VALIDATION.md`; the authoritative checkpoint plan was read from PR #3 without checking it out or modifying it.

The MVP example configuration selects CSV and template generation (`.env.mvp.example`). The scope is based on those product/runtime decisions and the import/queue graph below—not on whether a module currently has tests. Mixed modules and default-worker handlers remain in scope even where their coverage is low.

## 2. Canonical runtime import and queue map

`app/main.py` registers `app.api.routes`, `app.api.outreach_routes`, `app.api.whatsapp_routes`, `app.api.admin_messages_secure`, `app.api.admin`, `app.api.admin_recovery`, and `app.api.production_routes`. Registration/import is not evidence that every registered endpoint is part of the MVP: the production router is explicitly deferred by `SIMPLICITY_REVIEW.md` §3. Its startup import is recorded here rather than misclassified as “not imported.”

The default `worker` in `docker-compose.yml` listens to six queues, all retained in the active coverage scope:

| MVP stage | Actual import/call edge | Default queue / selection evidence |
|---|---|---|
| Lead import | `app.api.routes` → `app.workers.collector_worker.run_collector` → `app.collector.factory.create_collector` → `app.collector.adapters.csv` (CSV) or `app.collector.mock` (mock) | `collect`; `.env.mvp.example` sets `COLLECTOR_PROVIDER=csv`. The factory imports 2GIS only when that optional provider is selected. |
| Enrichment and qualification | `collector_worker` → `app.workers.enricher_worker.run_enricher` → `app.enrichment.enricher`, `app.verification.website`, `app.qualification.service` | `enrich`; enqueued by `collector_worker`. |
| Template landing generation | `app.api.routes` → `app.workers.content_generator_worker.run_content_generator` → `app.generation.context`, `factory`, `template`, `validator` | `generate_content`; `.env.mvp.example` selects `template`. |
| Review and local publish | `app.api.admin` / `app.api.admin_recovery`; `app.api.routes` → `app.publisher.publisher.publish_site` | Publish is local static publishing. Recovery also queues `app.workers.publisher_worker.run_publisher` on `publish`. Cloudflare deployment is not required. |
| WhatsApp outreach | `app.api.outreach_routes` → `app.workers.outreach_generator_worker.run_outreach_generator` → `app.outreach.message_generator`; secure approval/send → `app.workers.outreach_sender_worker.run_outreach_sender` → `app.outreach.service`, provider factory, mock/WhatsApp provider | `outreach_generate`, `outreach_send`; both are in the default worker queue list. |
| Inbound WhatsApp reply | `app.api.whatsapp_routes` → `app.security.webhook_signature` and outreach/lead models and services | Direct API/webhook path; signature validation and duplicate-event behavior are covered by tests. |
| Shared runtime | `app.main`, `app.config`, `app.database`, core models/schemas, `app.security.core`, `app.workers.connection` | Imported by the above API and worker paths. |

The exact 72-file measurement scope is:

```text
app/__init__.py
app/main.py
app/config.py
app/database.py
app/api/__init__.py
app/api/admin.py
app/api/admin_messages_secure.py
app/api/admin_recovery.py
app/api/outreach_routes.py
app/api/routes.py
app/api/whatsapp_routes.py
app/collector/__init__.py
app/collector/adapters/__init__.py
app/collector/adapters/csv.py
app/collector/base.py
app/collector/exceptions.py
app/collector/factory.py
app/collector/mock.py
app/enrichment/__init__.py
app/enrichment/enricher.py
app/generation/__init__.py
app/generation/base.py
app/generation/context.py
app/generation/factory.py
app/generation/mock.py
app/generation/template.py
app/generation/validator.py
app/landing/__init__.py
app/landing/renderer.py
app/landing/schema.py
app/models/__init__.py
app/models/audit.py
app/models/campaign.py
app/models/content_generation.py
app/models/event.py
app/models/landing_page.py
app/models/lead.py
app/models/search_job.py
app/models/stage.py
app/models/whatsapp.py
app/outreach/__init__.py
app/outreach/factory.py
app/outreach/message_generator.py
app/outreach/mock_provider.py
app/outreach/phone.py
app/outreach/provider.py
app/outreach/service.py
app/outreach/stage_service.py
app/outreach/whatsapp_provider.py
app/publisher/__init__.py
app/publisher/publisher.py
app/qualification/__init__.py
app/qualification/service.py
app/schemas/__init__.py
app/schemas/content_generation.py
app/schemas/job.py
app/schemas/landing.py
app/schemas/lead.py
app/schemas/outreach.py
app/security/__init__.py
app/security/core.py
app/security/webhook_signature.py
app/verification/__init__.py
app/verification/website.py
app/workers/__init__.py
app/workers/collector_worker.py
app/workers/connection.py
app/workers/content_generator_worker.py
app/workers/enricher_worker.py
app/workers/outreach_generator_worker.py
app/workers/outreach_sender_worker.py
app/workers/publisher_worker.py
```

No active module was omitted merely because it had low coverage: for example, `app/workers/enricher_worker.py` (77%), `app/workers/outreach_generator_worker.py` (57%), `app/outreach/service.py` (50%), and `app/api/outreach_routes.py` (47%) remain measured. The entire `app/api/routes.py` and `app/api/outreach_routes.py` files also remain measured even though they contain noncanonical endpoints.

### Explicit coverage exclusions

`.coveragerc` contains 25 exact-file exclusions (the only wildcard is the repository-root prefix before each fixed path); it has no package-wide or extension-wide wildcard. Each exclusion is supported by the approved deferred scope and the runtime edge shown here:

| Exact path(s) | Scope/import evidence |
|---|---|
| `app/api/production_routes.py`, `app/api_keys.py`, `app/backup.py`, `app/metrics.py`, `app/pilot.py`, `app/retention.py` | `SIMPLICITY_REVIEW.md` §3 explicitly defers the production router and these production-only surfaces. `app.main` still imports/registers the router; these routes are outside the canonical request path. |
| `app/models/api_key.py` | The API-key model is explicitly deferred. It is imported by `app.models.__init__` for metadata registration, not used in the canonical flow. |
| `app/outreach/dead_letter.py`, `app/outreach/inbox.py`, `app/outreach/template_sync.py` | Explicitly deferred in `SIMPLICITY_REVIEW.md` §3; inbox/template/dead-letter operations are not part of the canonical admin-panel/WhatsApp path. |
| `app/collector/adapters/two_gis.py` | Optional factory branch only; the approved MVP config uses CSV and the kept collector surface is CSV/mock. `SIMPLICITY_REVIEW.md` §9 lists CSV + mock; §12 identifies CSV as the fallback when the 2GIS API is blocked. |
| `app/generation/openai.py`, `app/generation/usage.py` | OpenAI generation is explicitly postponed in `SIMPLICITY_REVIEW.md` §10; the default MVP selects templates. `usage.py` is imported by the mixed routes module but only supports the optional usage endpoint, not the canonical template flow. |
| `app/outreach/webhook_handler.py` | Imported locally by email/Telegram webhook endpoints only. Those channels are explicitly postponed; WhatsApp uses `app.api.whatsapp_routes` instead. |
| `app/deployment/__init__.py`, `app/deployment/adapter.py`, `app/deployment/base.py`, `app/deployment/cloudflare.py`, `app/deployment/mock.py`, `app/models/deployment.py`, `app/schemas/deployment.py`, `app/workers/deployer_worker.py` | Cloudflare/deployer flow is explicitly postponed; local static publishing remains active. The deployer worker listens to `deploy`, which is absent from the default worker's six queues and present only in the advanced profile. `app.api.routes` imports some deployment types for its separate deploy endpoint, so that mixed route file remains in scope. |
| `app/collector/adapter.py` | Protocol is imported only under `TYPE_CHECKING` in the collector factory; it is not a runtime import. |
| `app/logging/__init__.py`, `app/logging/structured.py` | No runtime import from the canonical API/worker path; the structured logger is unused. |

The exclusions affect only the coverage denominator. No modules, routes, providers, queues, dependencies, or infrastructure were removed or disabled. The whole-repository coverage diagnostic below confirms the excluded code is still present and measurable when `.coveragerc` is not applied.

## 3. Coverage jobs and results

The historical CI workflow measured the whole `app` tree in both coverage jobs:

| CI job | Historical command shape | CP-01G scope alignment |
|---|---|---|
| `unit-tests` (SQLite) | `pytest tests/ -v --cov=app --cov-report=xml --cov-fail-under=80` | Now also passes `--cov-config=.coveragerc`; 80% remains unchanged. |
| `postgres-tests` | Same coverage gate with `-m "not slow"` and PostgreSQL/Redis services | Now also passes `--cov-config=.coveragerc`; 80% remains unchanged. This job was not run locally and is not claimed as PASS. |
| `docker-smoke` | Compose-backed runtime and webhook smoke | Not run locally; see external blockers. |

Evidence on the same 291-test suite:

- Whole-repository diagnostic, with the scope config deliberately disabled: **3,333 / 4,889 statements = 68.17%**. All 291 tests passed. This is diagnostic only and shows why the unchanged historical whole-repository 80% gate conflicted with the approved MVP scope.
- Approved explicit MVP scope using `.coveragerc`: **2,842 / 3,463 statements = 82.07%**; **291 passed, 22 warnings**. The unchanged 80% gate passes.
- The earlier CP-01 whole-repository result (59.82%) predates the CP-01G tests and fixes; the current unscoped diagnostic above supersedes it for this code state.

## 4. Ruff/format gates and historical debt

`.github/workflows/ci.yml` now has separate, visible reporting and blocking steps:

- Full `ruff check app tests` and `ruff format --check app tests` remain visible as **non-blocking historical-debt reports** (`continue-on-error: true`); no mass-format was applied.
- `scripts/check_quality_regressions.py` is a standard-library-only changed-line gate. It blocks Ruff diagnostics and formatter diffs overlapping added/modified lines in changed `app/` and `tests/` Python files. CI fetches full history and compares against the PR base SHA (or push-before SHA).
- The checker itself is Ruff/format clean. Local changed-line gate passed for **14 changed app/tests Python files** against both branch-start `08e74c119c3e3a46c2e5dda3fa77b7b38fb34aa1` and `origin/master`.

Current whole-tree diagnostic with Ruff 0.16.9 remains red on untouched debt: **323 findings across 69 files**; format check reports **68 files would be reformatted, 59 already formatted**. These reports remain visible but do not block unrelated historical lines. New/modified lines are blocking; threshold or code behavior was not relaxed.

## 5. Dependency, Bandit, and secret-scan evidence

- `pip check`: **PASS**, no broken requirements.
- `pip-audit -r requirements.txt`: **PASS**, no known vulnerabilities found.
- Bandit full report: **0 HIGH, 0 MEDIUM, 10 LOW**. The full report exits nonzero solely for the remaining LOW findings; the separate blocking `bandit -r app --severity-level high` gate exits 0.
- The former B324 HIGH was in the active CSV collector's stable fallback source ID. The CSV factory branch is reachable from the default `collect` worker when CSV is selected. `app/collector/adapters/csv.py` now calls MD5 with `usedforsecurity=False` and documents its identity-only purpose; `test_csv_fallback_source_id_remains_stable_for_deduplication` verifies the legacy digest output and repeatability. Hash output/deduplication semantics are unchanged.
- All 10 LOW findings were classified: B107 at `app/api/admin.py:52,298` is the intentionally empty CSRF-token default/sentinel (not a credential; missing CSRF is rejected and covered); B311 at `app/workers/outreach_sender_worker.py:79` is non-cryptographic retry jitter; B404×2, B603×3, and B607×2 are subprocess findings in deferred backup/Cloudflare modules. They remain visible in the full report; no finding was hidden.

The working secret scan is `detect-secrets==1.5.0`, run over all files and as a blocking baseline hook in CI (replacing the ineffective `|| true` scan). The repository-wide scan found **21 detector candidates across 15 files**: 8 `Basic Auth Credentials` patterns and 13 `Secret Keyword` patterns. Review confirmed these are sample/local configuration defaults, documentation examples, or test-only values—not live credentials. `.secrets.baseline` records only false-positive fingerprints (`is_secret: false`); no candidate value is reproduced here. The exact detector locations are in the generated baseline. The CI-style hook scanned **204 files**, found **0 unbaselined candidates**, and exited 0. No real secret was found; this is not a secret-scan blocker.

## 6. SQLite migrations and MVP E2E/security

SQLite validation:

- `python scripts/check_migrations.py`: **PASS** — single head `007`, base-to-head upgrade, 14 expected tables, constraint checks, downgrade one revision, and re-upgrade. The helper prints SQLite-specific “may be missing” warnings for several indexes, then reports all table checks passed.
- `bash scripts/check_migrations.sh`: **PASS** — 14 tables; revision 002/004 schema checks; unique constraints; downgrade/re-upgrade/full-chain checks; legacy revision-001 SQLite data preservation and nullable-FK verification. It prints three SQLite index-presence warnings for manual review, then reports `MIGRATION CHAIN VERIFICATION PASSED`.
- `alembic heads`: **PASS**, one head `007`.

Automated MVP/E2E/security:

- Focused CSV/default-worker, canonical pipeline, and send-handoff command: **8 passed, 16 warnings**. The four CP-01G tests cover stable CSV identity, CSV through the default worker runtime to a WhatsApp reply, template/safety policies, and admin reject/template-consent behavior.
- Focused admin approval/recovery/webhook security command: **70 passed, 19 warnings**. This includes auth, POST/CSRF-only message approval, terminal-status guards, recovery/retry policy, and webhook security cases.
- Full scoped suite: **291 passed, 22 warnings**, with the 82.07% result above. `test_real_worker_mvp_pipeline` runs generation/publication and sender worker functions through the secured approval routes, inbound WhatsApp handling, replied-stage transition, and duplicate-event idempotency.
- `python -m compileall app -q`: **PASS**.

These are automated application tests using the repository's SQLite/test and in-process queue/mocking facilities. They do not represent a live PostgreSQL, Redis, or Docker run.

## 7. External blockers and checkpoint boundary

The following local environment evidence prevents the remaining CP-01 runtime validations:

- `scripts/local_validate_mvp.sh`: exit 1 at its preflight — `[LOCAL-VALIDATE] FAILED: docker is not installed`.
- `CLEANUP_ON_EXIT=0 bash scripts/smoke_mvp_pipeline_strict.sh`: exit 127 at Compose validation — `docker: command not found`.
- `docker`, `docker compose`, `psql`, and `pg_isready` are unavailable.
- A direct `alembic upgrade head` attempt using `postgresql+psycopg` at `127.0.0.1:5432` exits 1 with `Connection refused` / “Is the server running on that host and accepting TCP/IP connections?”. No PostgreSQL migration or integration test is claimed as PASS.

**CP-01G is PASS; CP-01 remains BLOCKED** until live PostgreSQL integration and Docker-backed default-profile validation are completed. CI defines PostgreSQL-service and Docker smoke jobs, but no result from those remote jobs is asserted here. PR #2 and PR #3 remain unmerged. CP-02 was not started.

## 8. Change evidence

- `.coveragerc` — explicit 72-file active scope and 25 evidence-backed exact-file exclusions; 80% CI threshold unchanged.
- `.github/workflows/ci.yml` — changed-line Ruff/format blocker, non-blocking historical reports, blocking Bandit HIGH gate, working blocking secret-baseline scan, and report artifact kept outside the scanned worktree.
- `scripts/check_quality_regressions.py` — standard-library changed-line Ruff/format gate.
- `.secrets.baseline` — audited false-positive fingerprints; no raw values.
- `app/collector/adapters/csv.py` and `tests/test_cp01g_mvp_runtime_gate.py` — B324 non-security hash annotation plus stable-ID and canonical-runtime behavioral tests.
- `app/workers/outreach_generator_worker.py` — preserve actual recipient phone rather than a `wa.me` URL and keep worker error handling/logging behavior safe; covered by the canonical path tests.
- No dependency, schema, queue, service, or infrastructure change was made in CP-01G.
