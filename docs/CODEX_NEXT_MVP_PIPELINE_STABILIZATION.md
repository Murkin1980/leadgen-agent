# Codex instruction: MVP pipeline stabilization

## 1. Goal

Stabilize the existing Leadgen Agent MVP end-to-end flow without adding new infrastructure, services, repositories, dashboards, providers, roles, or speculative features.

The required working flow is:

```text
create/import lead
→ enrich lead
→ generate content
→ create landing page
→ preview
→ approve
→ publish
→ create outreach message
→ approve
→ send through mock/sandbox provider
→ receive webhook
→ update message and lead status
```

The result of this task is not a new phase or architecture redesign. The result is one reliable, repeatable MVP user flow.

## 2. Mandatory first step

Read and apply:

```text
AGENTS.md
skills/simplicity-first/SKILL.md
SIMPLICITY_REVIEW.md
```

Do not expand the current architecture budget.

Keep the default runtime:

```text
postgres
redis
migrate
api
worker
preview
```

Do not create:

- a second repository;
- additional databases;
- microservices;
- new queues;
- a separate frontend;
- Prometheus/Grafana;
- API key or role systems;
- a complex dead-letter subsystem;
- new outreach providers;
- automatic mass outreach;
- multi-tenant functionality.

## 3. Current context

A live MVP pipeline run previously revealed four showstopper defects:

1. Missing `python-multipart` prevented FastAPI form routes from importing.
2. Cyrillic company names collapsed to the same slug and landing pages overwrote each other.
3. The content generator attempted to mutate a frozen dataclass.
4. The outreach worker rejected legitimate `queued` and `retrying` messages.

These defects were fixed and regression tests were added. However, the existing suite historically tested components mainly in isolation. The next work must close the remaining gaps at the workflow level.

## 4. Required work

### 4.1 Add one complete automated MVP pipeline test

Create a true end-to-end integration test that exercises the real application services and worker functions.

The test must:

1. Create or import one lead.
2. Enrich the lead.
3. Verify a unique slug is generated.
4. Run content generation through the actual worker function.
5. Verify the landing record is created.
6. Approve the landing.
7. Run the publish worker.
8. Verify the expected files exist in a temporary publication directory.
9. Create an outreach campaign and message.
10. Approve the message.
11. Run the outreach sender worker with the mock provider.
12. Verify the message becomes `sent` and receives a provider message ID.
13. Process a mock inbound webhook.
14. Verify the webhook is stored once.
15. Verify the related message/lead state changes correctly.

The test must call real worker functions rather than only checking that a job was enqueued.

Use temporary directories and isolated database fixtures. Never write test output into the real `sites/public` directory.

Suggested location:

```text
tests/test_mvp_pipeline_e2e.py
```

### 4.2 Add idempotency and duplicate-protection tests

Add regression tests for repeated actions.

Verify that:

- importing the same source lead twice does not create uncontrolled duplicates;
- enriching the same lead twice does not produce conflicting slugs;
- generating content twice does not create multiple active landing pages for the same generation request;
- publishing the same approved landing twice is safe;
- pressing send twice does not send the same message twice;
- running the sender job twice does not duplicate provider delivery;
- receiving the same webhook event twice stores/processes it only once;
- retrying a failed task does not create a second unrelated entity.

Do not add a generalized distributed idempotency framework. Use existing database constraints, current identifiers, state checks, and small targeted guards.

### 4.3 Verify the single shared worker behavior

The default worker currently consumes several queues. Confirm that one failed job does not break later jobs.

Add tests or a simple integration harness that proves:

- a job exception is captured;
- the related database record receives a failed/error state;
- a readable error message is stored;
- the worker process can continue with the next job;
- the failed operation can be safely retried;
- retrying does not bypass approval, sandbox, DNC, consent, or duplicate-send checks.

Do not build a separate dead-letter service.

### 4.4 Add minimal retry actions to the existing admin interface

Use the current admin UI. Do not create a new dashboard.

For failed MVP steps, provide a small visible action such as `Повторить`:

- failed enrichment;
- failed content generation;
- failed publication;
- failed outreach send where retry is allowed.

Requirements:

- POST actions only;
- existing authentication and CSRF protection;
- state validation before retry;
- no retry for permanent policy blocks, DNC, rejected consent, or invalid recipient;
- audit/log entry where existing audit facilities are available;
- clear Russian success/error feedback.

### 4.5 Normalize status transitions

Audit the state transitions among:

- `Lead`;
- `ContentGeneration`;
- `LandingPage`;
- publication/deployment record;
- `OutreachMessage`;
- inbound message/event.

Document the actual allowed transitions and correct inconsistencies.

At minimum, prevent these false states:

- lead marked published when publishing failed;
- lead marked contacted when send was blocked or failed permanently;
- landing marked published before files are successfully written;
- message marked sent before provider success;
- duplicate webhook moving a record twice;
- retry returning a permanently blocked item to a sendable state.

Prefer a small transition helper or explicit service functions over a new workflow engine.

Add a compact document:

```text
docs/MVP_STATUS_TRANSITIONS.md
```

### 4.6 Expand Kazakhstan/Russian data regression tests

Add tests for realistic input:

- `ТОО «Құрылыс Жиһаз»`;
- `ИП Дерево-Мастер`;
- identical company names in the same city;
- empty city;
- long company name;
- quotation marks and punctuation;
- Kazakh Cyrillic characters;
- phone formats `8 707 123 45 67`, `+7 707 123 45 67`, `77071234567`;
- empty or invalid phone;
- duplicate phone with a slightly different company name.

Expected results:

- valid unique ASCII slug;
- deterministic phone normalization;
- safe WhatsApp URL only for valid numbers;
- no landing-page path collision;
- no accidental duplicate outreach.

### 4.7 Add a reproducible local smoke script

Create or update one simple smoke script for the default runtime.

It must:

1. Validate Docker Compose configuration.
2. Start the default services only.
3. Wait for PostgreSQL, Redis, API, worker, and preview.
4. Apply migrations.
5. Run or trigger one mock MVP pipeline.
6. Check that the landing page is reachable in preview.
7. Check that the mock message reaches `sent`.
8. Process one mock webhook.
9. Print a concise success/failure summary.
10. Shut down cleanly when run in CI mode.

Prefer one command, for example:

```bash
bash scripts/smoke_mvp_pipeline.sh
```

Do not require Meta credentials, Cloudflare credentials, or paid services.

## 5. Code deletion and cleanup

Do not delete the advanced Docker Compose profile as part of this task.

Only remove code when all of the following are true:

- it is not imported;
- it is not referenced by routes, jobs, docs, tests, or Compose;
- no migration depends on it;
- the full test suite and smoke pipeline pass after deletion.

Record deletion candidates separately in:

```text
docs/MVP_LEGACY_DELETION_CANDIDATES.md
```

Do not perform broad cleanup unrelated to the MVP pipeline.

## 6. Tests and checks

Run at minimum:

```bash
python -m compileall app -q
pytest tests/ -v
docker compose config
docker compose build
bash scripts/smoke_mvp_pipeline.sh
```

Also run the migration chain against PostgreSQL if the repository already contains the required script or CI service.

All newly found defects in the required MVP flow must be fixed before completion.

Do not claim success based only on unit tests. The end-to-end pipeline and smoke script must pass.

## 7. Completion criteria

The task is complete only when:

- one automated E2E pipeline test passes;
- repeated actions are proven safe by tests;
- a failed job can be seen and retried from the existing admin interface;
- state transitions are documented and consistent;
- Kazakhstan/Russian input cases pass;
- the default six-service runtime completes the smoke pipeline;
- no new infrastructure was introduced;
- mass outreach remains disabled;
- all existing tests still pass.

## 8. Required report

Create:

```text
docs/MVP_PIPELINE_STABILIZATION_REPORT.md
```

Include:

1. Summary of work.
2. Changed files.
3. Defects found and fixed.
4. E2E scenario covered.
5. Idempotency guarantees added.
6. Retry behavior.
7. Status-transition changes.
8. Test counts and results.
9. Docker smoke result.
10. Remaining known limitations.
11. Exact manual pilot steps for one sandbox phone number.
12. Items explicitly postponed.

## 9. Commit strategy

Prefer two reversible commits:

1. Tests and reproduced failures.
2. Minimal fixes, admin retry actions, documentation, and smoke script.

Do not mix unrelated refactoring or new features into these commits.

## 10. Final instruction

Do not design the next phase. Do not add production-scale infrastructure. Make the current MVP flow boring, repeatable, visible, and safe.