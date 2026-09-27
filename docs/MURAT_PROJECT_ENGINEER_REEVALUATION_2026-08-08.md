# Leadgen Agent — Murat Project Engineer / Murat AI Stack Re-evaluation

Date: 2026-08-08
Status: Architecture review only — no deep architecture change applied

## 1. Executive conclusion

The product idea remains valid, but the repository is still carrying significantly more engineering surface than the first business validation requires.

The actual MVP result is only:

```text
lead without website
→ landing generated
→ operator reviews
→ operator publishes
→ operator approves message
→ WhatsApp send
→ reply captured
```

Everything that does not improve or protect this exact path should either be removed from the default product, postponed, or deleted after verification.

Current state: the repository is simplified operationally, but not yet simplified internally.

## 2. Murat Project Engineer checks

### Foundation / core rules

Applied project rules:

- Simplicity First before new architecture.
- One repository.
- One main application.
- One database unless there is evidence otherwise.
- Zero or one worker/queue unless required by real load.
- Prefer deletion/consolidation over addition.
- Do not mix Leadgen Agent into another product/core domain without explicit approval.
- Deep architecture changes require explicit user approval before implementation.

### Result

No reason exists today to introduce more services, providers, queues, databases, dashboards, roles, or infrastructure.

## 3. Main contradiction in the current repository

`SIMPLICITY_REVIEW.md` already says the following are outside MVP:

- production routes;
- metrics;
- backup/restore;
- retention;
- API keys;
- pilot mode;
- dead-letter management;
- Cloudflare deployment;
- advanced worker profile;
- Wrangler/Node deployment tooling.

However these components are still present and some are still imported by the main application.

This creates a false-simple system: the operator sees six default containers, while the codebase still contains a Phase 07 production platform.

## 4. Current complexity that should be removed or isolated

### Remove from default application immediately after tests prove safety

1. `app/api/production_routes.py` from `app/main.py`.
2. Phase 07 endpoints from the default runtime.
3. `metrics.py`, `pilot.py`, `api_keys.py`, `retention.py`, `backup.py` from MVP imports.
4. dead-letter/admin production APIs from MVP.
5. template synchronization from MVP.
6. dedicated production inbox API where existing admin inbox is sufficient.

These can remain in Git history; they do not need to stay active in the product.

### Remove from repository after reference check

Candidate legacy components:

- advanced worker services in `docker-compose.yml`;
- `Dockerfile.deployer`;
- Wrangler configuration;
- `package.json` / `package-lock.json` if Cloudflare deploy is not used;
- unused deployment modules;
- email/telegram remnants;
- production-only migrations/models not needed by the validated MVP.

Deletion must only happen after import/reference/migration tests.

## 5. Stronger simplification option

The current runtime is:

```text
PostgreSQL
+ Redis
+ migrate container
+ FastAPI
+ RQ worker
+ nginx preview
```

For the current human-driven validation loop, Redis/RQ is not yet clearly justified.

The operator performs manual approval between expensive steps. A single lead run does not require distributed background processing.

A smaller candidate architecture is:

```text
FastAPI monolith
+ SQLite for local/pilot use
+ local `sites/public`
+ synchronous service calls
+ WhatsApp provider
```

Optional production step later:

```text
PostgreSQL replaces SQLite
```

without changing business services.

This would remove:

- Redis;
- RQ;
- worker container;
- queue debugging;
- queue retry state;
- Redis health checks;
- worker orchestration;
- one entire category of E2E failure.

## 6. Why not change it immediately

Removing Redis/RQ and changing database assumptions is a deep architecture change.

Under the Murat Project Engineer deep-change gate, this review may recommend it, but implementation must wait for explicit user approval.

Before approval, the safe action is to finish the current stabilization branch and measure actual runtime latency for:

- collection;
- enrichment;
- landing generation;
- publish;
- mock/WhatsApp send.

If these operations complete comfortably within a normal HTTP request or a simple operator-triggered process, the worker is unnecessary for MVP.

## 7. Three architecture options

### Option A — Keep current simplified Docker stack

```text
FastAPI + PostgreSQL + Redis/RQ + nginx
```

Pros:
- already implemented;
- minimal code change;
- worker isolates slow calls.

Cons:
- Docker Desktop required;
- six services to explain;
- queue/Redis failure modes;
- more local setup and debugging.

Use only if measured generation/send work needs a background worker.

### Option B — Recommended MVP simplification

```text
FastAPI + SQLite + local generated pages
```

All operator-triggered operations run synchronously.

Pros:
- one Python process;
- no Docker required for first validation;
- no Redis;
- no worker;
- no PostgreSQL installation;
- easiest debugging;
- easiest laptop start.

Cons:
- not intended for high concurrency;
- long external API calls block a request;
- later production database migration may be needed.

This is the preferred validation architecture if timing tests support it.

### Option C — Cloud-only rewrite

Move runtime/database/queues into a serverless platform.

Rejected for the current stage.

Reason: it changes runtime assumptions, persistence, filesystem publishing, and deployment model at the same time. It reduces local containers but increases migration and platform-specific work. This is not simplicity for an unvalidated product.

## 8. Murat AI Stack role separation

This repository should stay model-independent.

Recommended work split:

- GPT / Murat Project Engineer: architecture decisions, deep-change gate, final review.
- coding model: mechanical deletion/refactor/test updates.
- documentation model: README/runbook cleanup after architecture stabilizes.
- GitHub connector: repository inspection and PR review.

Do not encode the business process into one specific AI model or plugin.

## 9. What the MVP should NOT contain

Until the first real reply/conversion is measured, do not add:

- CRM integration;
- analytics dashboard;
- follow-up automation;
- multiple messaging providers;
- complex consent subsystem beyond necessary policy safeguards;
- automated scheduling;
- multi-tenant support;
- Kubernetes;
- monitoring stack;
- generalized workflow engine;
- event bus;
- more queues;
- another database;
- separate frontend framework.

## 10. Recommended next work without deep architecture change

1. Finish current stabilization PR.
2. Remove `production_router` from default `app.main` after regression tests.
3. Remove advanced mode from README as a normal user path.
4. Produce a verified legacy deletion list.
5. Measure worker job durations on 10 realistic leads.
6. Run one operator pilot using mock/sandbox.
7. Record actual friction: setup time, failed steps, manual actions, average lead time.

Then decide whether Redis/RQ survives.

## 11. Recommended deep simplification if approved

Target structure:

```text
app/
  main.py
  config.py
  database.py
  models.py or models/
  services/
    leads.py
    generation.py
    publishing.py
    outreach.py
  api/
    admin.py
    webhook.py
  landing/
  templates/

sites/
tests/
```

Runtime:

```text
python -m uvicorn app.main:app
```

Database for validation:

```text
SQLite file
```

No Redis. No RQ. No migrate container. No nginx requirement for local validation; FastAPI can serve generated static pages directly.

## 12. Success criteria before adding complexity

Do not optimize for scale until all are true:

1. A real lead receives a generated landing.
2. Operator approves it successfully.
3. A real WhatsApp message is sent safely.
4. At least one inbound reply is captured.
5. The process is repeated across 10–20 leads.
6. We know the actual slow/failing step.

## 13. Recommendation

The project should move from "production platform being simplified" to "validation tool that may later become a platform".

Recommended immediate architecture direction:

- keep one repository;
- keep FastAPI;
- keep Jinja2;
- keep the current admin UI;
- keep one messaging provider;
- keep explicit operator approvals;
- remove inactive production architecture;
- strongly consider removing Redis/RQ and PostgreSQL from the validation version after timing evidence and explicit approval.

Do not add anything new until the first real end-to-end pilot produces a measurable reply outcome.
