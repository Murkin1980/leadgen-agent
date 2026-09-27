# Codex Router instruction — Leadgen Agent MVP deep simplification

Date: 2026-08-08
Status: approved instruction for implementation through Codex Router / Agent Research
Branch target: `work/mvp-pipeline-stabilization`

## 1. Purpose

Simplify the existing Leadgen Agent into a validation-first tool without changing the core business outcome.

The only required business flow is:

```text
lead without website
→ generate landing
→ operator reviews
→ operator approves/publishes
→ create WhatsApp message
→ operator approves
→ send
→ capture inbound reply
```

This task is not a redesign for scale. It is a reduction of moving parts, dependencies and failure modes.

The project should move from:

> production platform being simplified

to:

> validation tool that may later become a platform

## 2. Mandatory reading order

Before touching code, read in this exact order:

```text
AGENTS.md
skills/simplicity-first/SKILL.md
SIMPLICITY_REVIEW.md
docs/MURAT_PROJECT_ENGINEER_REEVALUATION_2026-08-08.md
docs/PROJECT_PROGRESS_REVIEW_2026-07-28.md
docs/CODEX_NEXT_MVP_PIPELINE_STABILIZATION.md
docs/MVP_STATUS_TRANSITIONS.md
README.md
```

If these documents conflict, precedence is:

```text
AGENTS.md
→ current Murat Project Engineer re-evaluation
→ current status-transition rules
→ older stabilization documents
→ README
```

Do not silently resolve a contradiction by adding infrastructure.

## 3. Murat Project Engineer rules

Apply these rules throughout the task:

- Simplicity First.
- One repository.
- One main application.
- One database for MVP.
- Zero or one worker/queue only if measured evidence proves it is needed.
- Prefer deletion, consolidation and reuse before addition.
- No speculative production architecture.
- No new framework unless current framework blocks the MVP.
- Preserve explicit operator approval before publishing and before sending a message.
- Preserve DNC, duplicate-send protection, webhook idempotency and other safety checks already proven necessary.
- Do not weaken security or status guarantees just to make the simplified version pass.

## 4. Codex Router / Murat AI Stack work split

Use the Router deliberately to reduce expensive-model token usage.

### Stage A — Research / repository inventory

Preferred executor: Agent Research / DeepSeek or another low-cost research-capable model.

Tasks:

1. Build an import/reference graph for all candidate legacy modules.
2. List every route, model, migration, test, Compose service and documentation reference related to:
   - `production_routes.py`;
   - metrics;
   - pilot mode;
   - API keys;
   - retention;
   - backup/restore;
   - dead-letter subsystem;
   - template sync;
   - production inbox;
   - advanced workers;
   - deployment/Cloudflare/Wrangler;
   - Redis/RQ worker paths;
   - PostgreSQL-only assumptions.
3. Produce a concise deletion-impact matrix.
4. Search current primary documentation only when an external technical fact is required.
5. Do not modify code in this stage.

Output:

```text
docs/MVP_SIMPLIFICATION_RESEARCH.md
```

The report must separate:

```text
safe to remove now
safe to disable first
requires refactor
requires migration decision
must keep
unknown / needs review
```

### Stage B — Draft implementation plan

Preferred executor: low-cost coding/reasoning model.

Create:

```text
docs/MVP_SIMPLIFICATION_PLAN.md
```

The plan must use reversible slices and show exact files affected.

Do not create a broad rewrite plan.

### Stage C — Architecture review gate

Preferred executor: strongest available architecture/review model.

Review only:

- deletion-impact matrix;
- migration risks;
- proposed slices;
- evidence for or against Redis/RQ;
- evidence for or against PostgreSQL in the validation build.

The strong model should not reread or summarize the entire repository unless the research report is insufficient.

If research is insufficient, send only the missing targeted questions back to Stage A.

### Stage D — Mechanical implementation

Preferred executor: economical coding model.

Perform file removal, import cleanup, route consolidation, configuration cleanup, test updates and documentation updates.

### Stage E — Final technical review

Preferred executor: strongest code-review model.

Review the final diff for:

- broken business flow;
- unsafe status transitions;
- lost duplicate protection;
- lost DNC/consent safety;
- accidental deletion of required webhook behavior;
- new complexity introduced during simplification.

## 5. Token / model budget policy

Do not spend the strongest model on repository-wide inventory or mechanical deletion.

Use these routing principles:

```text
cheap/research model:
  file inventory
  grep/reference map
  dependency map
  documentation lookup
  obvious legacy candidates
  first-pass test failure classification

mid-cost coding model:
  mechanical refactor
  import cleanup
  route consolidation
  test updates
  README cleanup

strong architecture/review model:
  deep architecture decision
  migration risk
  final diff review
  ambiguous failure root cause
  security/state-machine review
```

If one model has already produced a verified inventory, do not ask the next model to repeat the same full-repository analysis. Pass forward the report and only relevant diffs/files.

Keep context compact:

- send file paths + relevant excerpts rather than whole repository dumps;
- send failing test output only around the actual failure;
- prefer `git diff --stat`, targeted `git diff -- <files>`, and concise reports;
- checkpoint conclusions into markdown so later agents read the checkpoint instead of recreating it.

## 6. Target architecture

The desired validation architecture is:

```text
FastAPI
+ SQLAlchemy
+ SQLite
+ Jinja2
+ FastAPI static file serving
+ Mock/WhatsApp provider
+ existing admin UI
```

Preferred local start:

```bash
python -m uvicorn app.main:app
```

Target default runtime should not require:

```text
Redis
RQ
worker container
PostgreSQL container
migrate container
nginx preview container
Node.js
Wrangler
Docker Desktop
```

Docker may remain as an optional later packaging/deployment path, but must not be required to validate the MVP locally.

## 7. Non-negotiable behaviors to preserve

The simplification is successful only if all of these remain true:

1. Lead can be imported/created.
2. Russian/Kazakh company names produce safe unique slugs.
3. Landing content can be generated.
4. Landing requires operator approval.
5. Landing is only marked published after files/static output exist successfully.
6. Message requires operator approval.
7. Message is only marked sent after provider success.
8. Re-running send does not duplicate provider delivery.
9. DNC/blocked/cancelled/dead-letter items cannot be accidentally resent.
10. Duplicate inbound webhook is processed once.
11. Valid inbound reply moves the lead to `replied`.
12. Recovery actions remain POST + auth + CSRF and only expose genuinely retryable operations.
13. Mock mode remains available so no paid provider is required for tests.

Use `docs/MVP_STATUS_TRANSITIONS.md` as the source of truth.

## 8. Phase 1 — remove inactive production surface from default runtime

This phase should be low risk.

### Required work

1. Remove `production_router` import/registration from default `app/main.py`.
2. Confirm the core MVP starts without importing:
   - `app.metrics`;
   - `app.pilot`;
   - `app.api_keys`;
   - `app.retention`;
   - `app.backup`;
   - `app.outreach.dead_letter`;
   - `app.outreach.template_sync`;
   - production inbox code.
3. Update tests that incorrectly require enterprise/production modules merely to prove importability.
4. Do not delete modules yet if references/migrations remain uncertain.
5. Update README so Phase 07 is not presented as part of normal MVP runtime.

### Acceptance

- core app imports cleanly;
- MVP routes work;
- production routes are absent from default OpenAPI/runtime;
- no core MVP test regresses.

Commit separately.

## 9. Phase 2 — verified legacy deletion

Use Stage A research output.

Candidate removals include, only after proving no required references remain:

```text
app/api/production_routes.py
app/metrics.py
app/pilot.py
app/api_keys.py
app/retention.py
app/backup.py
app/outreach/dead_letter.py
app/outreach/template_sync.py
unused production inbox modules
unused production-only tests
advanced worker definitions
Dockerfile.deployer
Wrangler config
package.json
package-lock.json
unused deployment modules
email/telegram remnants
```

Do not remove a migration/model only because a feature is not exposed. First determine whether existing database schema/tests depend on it.

Prefer leaving historical migration files intact if deleting them creates more risk than value.

Commit separately.

## 10. Phase 3 — measure before deleting Redis/RQ

Do not remove the queue based on opinion alone.

Instrument or run a simple timing harness for 10 realistic mock/template leads.

Measure:

```text
collection duration
enrichment duration
content generation duration
render duration
publish duration
mock send duration
```

Create:

```text
docs/MVP_SYNC_TIMING_REPORT.md
```

No Prometheus or monitoring platform.

Simple elapsed-time logging/test harness is enough.

### Decision rule

If operator-triggered MVP operations comfortably complete in a normal interactive request/process and no step requires durable background execution, remove Redis/RQ for the validation build.

If one specific step genuinely requires background execution, keep one minimal worker only for that step. Do not preserve six queue names just because they already exist.

## 11. Phase 4 — remove Redis/RQ if timing evidence supports it

Expected changes:

1. Extract business logic from worker wrappers into direct service functions where necessary.
2. API/admin actions call service functions directly.
3. Worker functions may temporarily call the same services during transition.
4. Once tests prove direct flow, remove Redis/RQ imports and queue enqueue calls from the MVP path.
5. Remove worker-specific retry state that no longer has meaning, while preserving explicit operator retry and provider retry safety where required.
6. Remove `redis` and `rq` from requirements only after no runtime/test imports remain.
7. Remove Redis/worker services from default Compose or retire Compose from local MVP start.

Do not replace RQ with another queue framework.

Commit in reversible steps.

## 12. Phase 5 — SQLite validation mode

Goal: local MVP should run with one database file.

### Required approach

Keep SQLAlchemy. Do not rewrite persistence manually.

Set validation/local default to something like:

```text
sqlite:///leadgen.db
```

Handle SQLite engine options correctly where needed.

Before changing defaults:

1. inventory PostgreSQL-specific SQL/types/locking behavior;
2. identify `with_for_update()` and other database-specific assumptions;
3. make the MVP service layer portable without weakening duplicate protection;
4. run all core tests on SQLite;
5. retain PostgreSQL compatibility if doing so is cheap.

Do not force PostgreSQL removal from future production capability if SQLAlchemy portability is easy to preserve.

## 13. Phase 6 — remove nginx requirement for local preview

Serve generated public sites from FastAPI using its static-file support or an equally small built-in approach.

Desired local URLs:

```text
http://localhost:8000/admin/...
http://localhost:8000/sites/<slug>/
```

or another single-port layout chosen consistently.

Do not introduce a frontend framework.

## 14. Phase 7 — configuration cleanup

Reduce `app/config.py` and `.env.mvp.example` to variables required by the validated MVP.

Candidate values to remove/postpone from default config:

- Cloudflare credentials;
- email SMTP;
- Telegram token;
- production monitoring settings;
- unused follow-up automation;
- Redis URL after queue removal;
- PostgreSQL-only local defaults after SQLite validation mode.

Keep WhatsApp production variables only if the WhatsApp provider still needs them.

Do not commit secrets.

## 15. Phase 8 — admin/UI consolidation

Keep the existing server-rendered admin UI.

Do not build React/Vue/Next.js.

Required user actions should remain obvious:

```text
Leads
Generate
Review landing
Approve
Publish
Create/review message
Approve
Send
Inbox
Recovery
```

Remove navigation or pages that belong only to deleted production subsystems.

## 16. Tests

Use tests as the migration harness.

At minimum preserve/repair:

```text
tests/test_mvp_pipeline_e2e.py
tests/test_mvp_retry_safety.py
tests/test_admin_recovery.py
tests/test_admin_message_approval_security.py
```

Add a direct/synchronous E2E test for the simplified runtime.

Expected final scenario:

```text
create lead
→ generate
→ approve landing
→ publish
→ create/approve message
→ send mock
→ inbound webhook
→ replied
```

Run twice where relevant to prove idempotency.

## 17. Local validation target

The end state should support a Windows-friendly flow approximately like:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.mvp.example .env
python -m uvicorn app.main:app
```

Then open one local port in the browser.

If Alembic remains useful, keep a single documented initialization command. If the validation database can safely create schema automatically only in development/test mode, document that choice explicitly.

## 18. What NOT to do

Do not:

- rewrite the application in another language;
- migrate to Cloudflare/D1/Supabase just to remove Docker;
- add Celery, Dramatiq, Temporal or another queue replacement;
- add React/Next/Vue;
- add a generalized workflow engine;
- add another AI framework;
- add multi-agent runtime into the application itself;
- add multi-tenant support;
- add CRM integrations;
- add analytics dashboards;
- add automated follow-up campaigns;
- add multiple messaging providers;
- add Kubernetes;
- add monitoring infrastructure;
- add a second database;
- redesign the landing generator unless a failing test requires it.

Codex Router is a development orchestration tool, not an application runtime dependency. Do not embed Router/Agent Research into Leadgen Agent.

## 19. Safety / deep-change rule for the coder

The user has authorized this simplification instruction as the next development direction.

However, stop and report before implementing a change if research shows that it would:

- lose existing lead/message data without a migration path;
- weaken DNC/consent protections;
- permit duplicate real WhatsApp sends;
- remove required webhook signature/idempotency safeguards;
- contradict the core Leadgen business flow;
- require a new external paid service;
- require merging Leadgen Agent into another project;
- require abandoning FastAPI/SQLAlchemy rather than simplifying around them.

For ordinary deletion/refactor/test work that follows this instruction, proceed without asking for repeated confirmation.

## 20. Commit strategy

Use small reversible commits. Suggested sequence:

```text
1. research + plan documents
2. detach production routes from MVP runtime
3. delete verified legacy production surface
4. timing harness/report
5. extract direct service functions
6. remove Redis/RQ from MVP path
7. enable SQLite validation default
8. serve static sites from FastAPI
9. simplify config/dependencies/docs
10. final E2E + cleanup report
```

Never bundle all architecture changes into one giant commit.

## 21. Required final report

Create:

```text
docs/MVP_SIMPLIFICATION_FINAL_REPORT.md
```

Include:

1. Before/after architecture.
2. Files/modules deleted.
3. Dependencies removed.
4. Services/containers removed.
5. Final local startup commands.
6. Business behavior preserved.
7. Safety behavior preserved.
8. Test names and exact pass/fail counts.
9. Timing measurements.
10. Known limitations.
11. Items intentionally postponed.
12. Evidence that would justify reintroducing a worker/PostgreSQL/production infrastructure later.

## 22. Completion definition

This task is complete only when:

- the MVP runs locally with materially fewer moving parts;
- the core business flow remains end-to-end functional;
- operator approval gates remain intact;
- duplicate-send/webhook safety remains intact;
- no production-only modules load in the MVP runtime;
- no replacement complexity was introduced;
- tests pass in the exact final state;
- the final startup path is clearly documented;
- the final report is committed.

The desired result is not clever architecture.

The desired result is a small, understandable tool that can prove whether showing a ready-made landing to a company without a website produces a real reply.