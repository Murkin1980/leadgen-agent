# MVP Pipeline Stabilization Report

Per `docs/CODEX_NEXT_MVP_PIPELINE_STABILIZATION.md`. Branch:
`mvp-pipeline-stabilization` (8 commits on top of `master`, after the
prior session's four-showstopper-bug fix was merged).

## 1. Summary of work

Stabilized the existing MVP flow (import → enrich → generate → approve
→ publish → outreach message → approve → send → webhook) without new
infrastructure, services, or providers. Added one true end-to-end test
that drives real worker functions instead of only checking enqueued
jobs; idempotency tests for every repeatable action in the flow; tests
proving one failed item in a batch doesn't break the rest; four minimal
"Повторить" retry actions in the existing admin UI; a status-transitions
audit document; expanded Kazakhstan/Russian input regression tests; a
genuinely-failing (not `|| true`-everywhere) smoke script for the
default six-service runtime; and a deletion-candidates document. No new
services, queues, dashboards, providers, or roles were introduced. Mass
outreach remains disabled by default (`OUTREACH_ENABLED=false` in
`.env.mvp.example`).

Along the way, writing each required test/harness surfaced real,
previously-undetected defects in the actual pipeline code -- eleven in
total, listed in section 3. This matches the doc's premise: the prior
suite tested components in isolation, and closing the gap at the
workflow level is exactly what found them.

## 2. Changed files

```
 app/api/admin.py                         | 261 ++++++++++++++++++++-
 app/api/routes.py                        |  75 +++++-
 app/config.py                            |   1 +
 app/enrichment/enricher.py               |  33 ++-
 app/outreach/service.py                  |   7 +-
 app/workers/collector_worker.py          | 105 +++++----
 app/workers/enricher_worker.py           |  49 ++--
 app/workers/outreach_generator_worker.py |  80 ++++---
 app/workers/outreach_sender_worker.py    |   9 +-
 app/workers/publisher_worker.py          |   1 -
 docker-compose.yml                       |  18 +-
 docs/MVP_LEGACY_DELETION_CANDIDATES.md   |  74 ++++++ (new)
 docs/MVP_STATUS_TRANSITIONS.md           | 229 ++++++++++++++++++ (new)
 scripts/smoke_mvp_pipeline.sh            | 304 ++++++++++++++++++++++++ (new)
 tests/test_admin_retry_actions.py        | 269 +++++++++++++++++++++ (new)
 tests/test_kz_ru_data_regression.py      | 139 +++++++++++ (new)
 tests/test_mvp_pipeline_e2e.py           | 263 +++++++++++++++++++++ (new)
 tests/test_pipeline_idempotency.py       | 387 +++++++++++++++++++++++++++++++ (new)
 tests/test_worker_resilience.py          | 250 ++++++++++++++++++++ (new)

 18 files changed, 2420 insertions(+), 133 deletions(-)
```

## 3. Defects found and fixed

In the order found, across all sections of required work:

1. **`app/workers/publisher_worker.py` (found writing 4.1's E2E test):**
   referenced `LandingStatus.generated`, which doesn't exist on the
   enum. Every call to `run_publisher` raised `AttributeError`, silently
   caught by the surrounding `except Exception`, marking the landing
   `failed` without ever writing a file. Zero test coverage previously
   existed for `run_publisher` itself. Fixed by removing the dead status
   assignment (nothing else read it).

2. **`app/enrichment/enricher.py` -- slug length (found writing 4.6):**
   `make_slug()` had no length cap; a long company name produced a
   300+ character slug, past the ~255-byte path-component limit on most
   Linux filesystems, which would break `mkdir()` in `save_landing()`.
   Fixed by capping the base slug to 80 characters before the
   uniqueness suffix.

3. **`app/enrichment/enricher.py` -- phone normalization duplication
   (found writing 4.6):** `normalize_phone()`/`make_whatsapp_url()` used
   a separate, looser phone parser than `PhoneNumberService` (used for
   outreach). Invalid input like `"abc"` silently passed through
   unchanged, producing a broken `https://wa.me/` link and displaying
   garbage as the landing page's phone number. Fixed by reusing
   `PhoneNumberService.normalize()`, returning `None` on
   `PhoneNumberError`.

4. **`app/api/routes.py` -- no idempotency guard on content generation
   (found writing 4.2):** `POST /leads/{id}/content-generations` had no
   protection against being called twice for the same lead. Since a
   landing's slug comes from the lead (not the generation), two calls
   created two competing `LandingPage` rows sharing the same slug --
   both could end up `published` in the database while only one
   directory existed on disk. Fixed with a guard: reject a second
   request with 409 while one is queued/running; reuse the lead's
   existing landing on a regenerate request instead of creating a
   competing one. Refactored the pure record-creation logic into
   `_create_content_generation_record()` so both the API route and (in
   section 4.4) the admin retry action can share it without
   double-enqueuing to Redis.

5. **`app/workers/enricher_worker.py` -- batch abort on one failure
   (found writing 4.3):** `run_enricher`'s per-lead loop had no
   try/except around each lead's processing. One lead raising during
   `enrich_lead()` aborted the entire batch -- every lead after it was
   silently never enriched. Fixed: each lead now gets its own
   try/except; failure marks that lead `LeadStatus.failed` and records
   the error via the existing audit log (`log_audit_event`), no new
   column/migration needed. Also made the `SearchJob` lookup optional so
   a single-lead retry (no `search_job_id`) still actually runs, instead
   of silently no-op'ing.

6. **`app/workers/outreach_generator_worker.py` -- same batch-abort
   shape (found writing 4.3):** the per-message loop had the same
   defect. Fixed the same way, reusing the existing `blocked` +
   `error_message` pattern already used a few lines above in the same
   function for the lead-not-found/do-not-contact cases.

7. **`app/workers/outreach_sender_worker.py` -- defensive hardening
   (found writing 4.3):** `run_outreach_sender_batch`'s loop had no
   per-message isolation in case `run_outreach_sender`'s own
   retry-scheduling raises (e.g. Redis unreachable). Isolated each
   message in the batch loop.

8. **`app/workers/collector_worker.py` -- same batch-abort shape (found
   writing 4.3):** the per-company loop had no isolation; one company's
   data causing `qualify_lead()` to raise aborted the rest of the page.
   Fixed: the company is now skipped and logged, safe to retry since
   dedup is keyed on `source_id`.

9. **`app/api/routes.py` -- unhandled publish failure (found writing
   4.4):** `POST /landings/{id}/publish` (the real endpoint the MVP flow
   uses, not the job-based `run_publisher`) had no exception handling
   around rendering/saving/publishing. A failure was a raw HTTP 500; the
   landing stayed `approved` forever with no stored error and no
   `failed` state -- meaning nothing for an admin to even detect as
   failed, let alone retry. Fixed to mirror `run_publisher`'s per-step
   handling: on failure, `status = failed` and `review_note` gets a
   readable error.

10. **`app/outreach/service.py` -- sandbox check never normalized phone
    (found writing/testing 4.4):** `is_sandbox_allowed()` (the only
    caller is `requeue_dead_letter`) compared the raw recipient string
    against the sandbox allowlist without normalizing it first.
    WhatsApp recipients are stored as full `https://wa.me/<digits>`
    URLs, so this could never match a bare `+7XXXXXXXXXX` allowlist
    entry -- every dead-letter retry for a real WhatsApp message in
    sandbox mode was rejected, even when the phone genuinely was
    allowlisted. Fixed to normalize via `PhoneNumberService.normalize()`
    first, matching the live send path's own check.

11. **`docker-compose.yml` -- worker container crashes on startup
    (found writing 4.7, arguably the most severe defect in this pass):**
    the `worker` service and all 8 advanced-profile worker services ran
    `python -m rq worker ...`, but the pinned `rq==1.16.2` package has no
    `__main__.py` -- confirmed directly in this session
    (`ModuleNotFoundError: No module named rq.__main__`). The worker
    container would crash immediately on every startup in a real
    deployment, meaning nothing in the pipeline would ever be processed
    asynchronously. No test previously exercised this because all tests
    call worker functions directly or use FastAPI's `TestClient`, never
    spinning up the actual containers. Fixed all 9 occurrences to use
    the `rq` CLI entry point directly.

12. **`app/config.py` -- `.env.mvp.example` unusable outside Docker
    (found while verifying `docker compose config` in a follow-up
    session):** `Settings.Config` had no `extra` setting, so
    pydantic-settings defaults to rejecting unknown keys found in
    `.env`. `.env.mvp.example` -- the exact file the README's Quick
    Start section says to `cp .env.mvp.example .env` -- includes
    `POSTGRES_DB`/`POSTGRES_USER`/`POSTGRES_PASSWORD` (consumed only by
    the `postgres` container itself, not by this Settings model).
    Copying the template and running the app or test suite directly
    (not via Docker) crashed immediately with a confusing
    `pydantic_core.ValidationError: ... Extra inputs are not permitted`
    instead of starting. Fixed with `extra = "ignore"`; verified 318/318
    still passes with the literal, unedited `.env.mvp.example` present
    as `.env`.



`tests/test_mvp_pipeline_e2e.py` drives, through real application
services and worker functions (not just checking a job was enqueued):
create lead → `run_enricher` → verify unique slug → `run_content_generator`
→ verify landing created (`needs_review`) → approve via the real
`TestClient` → `run_publisher` (writing to a temp directory, never the
real `sites/public`) → verify `index.html`/`profile.json`/`styles.css`
exist and contain the lead's name → create campaign/message →
`run_outreach_generator` → approve via `TestClient` → `run_outreach_sender`
with the mock provider → verify `sent` + `provider_message_id` →
`POST /webhooks/whatsapp` with a mock inbound reply → verify stored once
→ verify `lead.stage == "replied"`.

## 5. Idempotency guarantees added

Covered by `tests/test_pipeline_idempotency.py` and, for worker-level
retry-safety specifically, `tests/test_worker_resilience.py`:

- importing the same source lead twice: existing collector dedup (by
  `source` + `source_id`) confirmed by test, no duplicate leads created.
- enriching the same lead twice: same deterministic slug both times.
- generating content twice for the same lead: second request blocked
  (409) while one is in flight; a fresh request after success reuses the
  existing landing rather than creating a competing one (the bug fixed
  in item 4 above).
- publishing the same approved landing twice: safe, files intact,
  `status` stays `published`.
- pressing send twice: second click rejected (400, status no longer
  `approved`).
- running the sender worker twice on an already-sent message: no
  re-send, `provider_message_id` unchanged.
- receiving the same inbound webhook twice: second call reports
  `changed: 0`, exactly one `InboundMessage` row stored.
- retrying after a failure: a fresh content-generation retry reuses the
  lead's landing rather than creating an unrelated second one.

No generalized idempotency framework was added, per the doc's explicit
instruction -- all of the above use existing unique constraints, current
identifiers (`source_id`, `lead_id`, message status), and small targeted
guards.

## 6. Retry behavior

Four "Повторить" actions added to the existing admin UI (no new
dashboard), all POST-only, behind the existing `admin_auth` cookie and
CSRF protection, with a Russian success/error banner via
`?retry=ok|error&msg=...` on the redirect:

- **Failed enrichment** (`Lead.status == failed`): re-runs `run_enricher`
  synchronously.
- **Failed content generation** (`ContentGeneration.status == failed`):
  reuses the same idempotency-guarded creation logic as the real API
  endpoint, then runs `run_content_generator` synchronously.
- **Failed publication** (`LandingPage.status == failed`, `review_status
  == approved`): calls the real `POST /landings/{id}/publish` endpoint
  function directly.
- **Failed outreach send, only where retry is allowed**
  (`OutreachMessage.status == dead_letter` and `retryable == True`):
  reuses the existing `app.outreach.dead_letter.requeue_dead_letter`,
  which re-validates do-not-contact, consent (production mode), sandbox
  allowlist (sandbox mode), phone validity, and `outreach_enabled`
  before allowing the retry, then runs `run_outreach_sender`
  synchronously. **No retry button is shown** for `blocked` messages
  (permanent policy blocks) or non-retryable dead-letter messages.

Every retry action is state-validated before acting (checked in
`tests/test_admin_retry_actions.py`, 10 tests) and produces an audit log
entry via the existing `log_audit_event` facility.

## 7. Status-transition changes

Full audit in `docs/MVP_STATUS_TRANSITIONS.md`. Summary of what changed
versus what was already correct:

- Confirmed already correct (no false-state bugs found): a lead is
  never marked `published` before files are written; `contacted` is
  only set inside the send-success branch; a message is only `sent`
  after provider success; duplicate webhooks are already deduplicated
  by `provider_message_id`/`provider_event_id`.
- Fixed: a landing could previously get stuck `approved` forever with no
  `failed` state on a publish exception via the single-landing endpoint
  (item 9 above) -- now consistently transitions to `failed` with a
  stored error.
- Fixed: dead-letter retry could incorrectly *over-block* a legitimately
  retryable message due to the unnormalized phone comparison (item 10)
  -- the opposite failure mode from "bypassing" a block, but still a
  real inconsistency between the live-send policy check and the retry
  policy check.
- Documented but **not fixed** (see section 12): `transition_lead_stage()`
  is the one validated, history-tracked way to change `lead.stage`, but
  is used in only 1 of 6 call sites that assign it; the other 5 (mostly
  webhook/send-worker code) assign the field directly, which means the
  admin "Stage History" view under-reports real transitions for those
  paths. This is an observability gap, not a false-state bug -- every
  value being assigned is a legitimate stage for the situation.

## 8. Test counts and results

- Full suite: **318 passed**, 0 failed (was 269 at the start of this
  branch; +49 new tests across 6 new files, all listed in section 2).
- Verified twice in a row from a clean `test.db` for stability (no
  order-dependent flakiness after fixing one test-isolation issue --
  see section 9).
- `python -m compileall app -q`: clean, exit 0.
- Migration chain against real PostgreSQL (installed in this sandbox
  specifically to verify this, since Docker itself wasn't available --
  see section 9): `alembic upgrade head` applied 001→007 cleanly, and
  `python scripts/check_migrations.py` passed its up→down→up→single-head
  verification, with 3 non-fatal warnings about missing indexes on
  `outreach_events.lead_id`/`outreach_events.message_id`/
  `outreach_messages.lead_id` (performance, not correctness; not
  addressed in this pass -- see section 12).
- Manually verified the FastAPI app boots and serves `/health` and
  `POST /jobs` correctly against that same real PostgreSQL + a real
  Redis instance (both installed directly in the sandbox), not just
  SQLite.

## 9. Docker smoke result

**Partially verified; full end-to-end run against real Docker still not
completed.** A Docker daemon was installed and started directly in this
sandbox in a follow-up session (`docker.io` + `docker-compose-v2` from
the Ubuntu archive, both on the network allowlist) specifically to push
this verification further than "no Docker available":

- `docker compose config`: **PASSED.** The compose file parses and
  resolves cleanly -- confirms the YAML fix in item 11 (section 3,
  `python -m rq worker` -> `rq worker`) didn't introduce a syntax or
  schema error, and that all service definitions, `depends_on`
  conditions, and environment variable interpolation are valid.
- `docker compose build`: **blocked by this sandbox's network policy**,
  not by anything in this repository. Building requires pulling
  `python:3.12-slim` from Docker Hub
  (`registry-1.docker.io`), which this sandbox's egress proxy explicitly
  denies (`403 Forbidden`, `x-deny-reason: host_not_allowed` -- confirmed
  directly with `curl -I https://registry-1.docker.io/v2/`). Docker Hub
  is not on the sandbox's allowed-domains list; only
  `archive.ubuntu.com`/`security.ubuntu.com`-style Ubuntu package
  mirrors are. This is an environment restriction, not a defect to fix
  in the codebase.
- `docker compose up` / `scripts/smoke_mvp_pipeline.sh` against real
  containers: **not run**, blocked by the same image-pull restriction.

As a substitute for what actual Docker couldn't verify, this session
additionally installed a real PostgreSQL and confirmed the full
migration chain and a live app run against it directly (see section 8)
-- stronger evidence than the SQLite-only testing this repo's test
suite otherwise relies on, though still not a substitute for the
container-level checks the smoke script performs (image builds,
`depends_on`/healthcheck wiring, the actual `worker` container process
lifecycle).

**Running `bash scripts/smoke_mvp_pipeline.sh` against a real Docker
installation with unrestricted network access remains a required
follow-up before this branch should be considered fully verified** --
see section 12. `docker compose config` passing is a meaningful signal
but does not substitute for it.

## 10. Remaining known limitations

- The smoke script has not been run against real Docker (section 9).
- `transition_lead_stage()` under-adoption (section 7) means the admin
  "Stage History" view is incomplete for leads that reached their
  current stage via a webhook reply or an outreach send, though the
  stage values themselves are always correct.
- `run_publisher` (job-based batch publish worker) still doesn't store
  a readable error message anywhere on a per-landing failure, unlike the
  single-landing endpoint (which now does, after item 9's fix) --
  tracked in `docs/MVP_LEGACY_DELETION_CANDIDATES.md` item 4.
- Three missing indexes reported by `scripts/check_migrations.py`
  (section 8) -- performance, not correctness.
- `docker compose ps <service> --format json` output format assumed to
  be one JSON object per line (Compose v2.20+); the smoke script hasn't
  been verified against older Compose versions that might emit a JSON
  array instead.

## 11. Exact manual pilot steps for one sandbox phone number

Using the default `.env.mvp.example` plus the overrides
`scripts/smoke_mvp_pipeline.sh` applies automatically (or set manually):

```bash
# .env additions for a one-number sandbox pilot
ADMIN_PASSWORD=change-me
OUTREACH_ENABLED=true
OUTREACH_MODE=sandbox
OUTREACH_SANDBOX_ALLOWLIST=+7XXXXXXXXXX   # your one pilot phone number, E.164
OUTREACH_QUIET_HOURS_START=00:00           # optional: widen the window for testing
OUTREACH_QUIET_HOURS_END=00:00
WHATSAPP_ALLOW_MOCK_WEBHOOKS=true
```

```bash
docker compose up --build -d
curl -s http://localhost:8000/health

# 1. Import (CSV or mock provider)
curl -s -X POST http://localhost:8000/jobs -H "Content-Type: application/json" \
  -d '{"city": "Алматы", "category": "Мебель на заказ", "limit": 5, "provider": "csv"}'

# 2. Wait a few seconds, then check leads
curl -s http://localhost:8000/leads

# 3. Generate content for a lead (replace {lead_id})
curl -s -X POST http://localhost:8000/leads/{lead_id}/content-generations

# 4. Check landings, approve and publish (replace {landing_id})
curl -s http://localhost:8000/landings
curl -s -X POST http://localhost:8000/landings/{landing_id}/approve
curl -s -X POST http://localhost:8000/landings/{landing_id}/publish

# 5. Verify the landing is live
curl -s http://localhost:8080/{slug}/

# 6. Create a campaign, add the lead, generate + approve + send
curl -s -X POST http://localhost:8000/campaigns -H "Content-Type: application/json" \
  -d '{"name": "Pilot", "channel": "whatsapp", "language": "ru"}'
curl -s -X POST http://localhost:8000/campaigns/{campaign_id}/add-leads \
  -H "Content-Type: application/json" -d '{"lead_ids": [{lead_id}]}'
curl -s -X POST http://localhost:8000/campaigns/{campaign_id}/generate-messages
curl -s http://localhost:8000/outreach-messages
curl -s -X POST http://localhost:8000/outreach-messages/{message_id}/approve
curl -s -X POST http://localhost:8000/outreach-messages/{message_id}/send

# 7. Confirm it reached 'sent'
curl -s http://localhost:8000/outreach-messages/{message_id}

# 8. Simulate the pilot number replying
curl -s -X POST http://localhost:8000/webhooks/whatsapp -H "Content-Type: application/json" \
  -d '{"entry":[{"changes":[{"value":{"messages":[{"id":"wamid.pilot1","from":"7XXXXXXXXXX","type":"text","text":{"body":"Здравствуйте"}}]}}]}]}'

# 9. Confirm the lead's stage flipped
curl -s http://localhost:8000/leads/{lead_id}
```

Or drive the same flow visually through `/admin/leads`,
`/admin/landings`, and `/admin/messages`.

## 12. Items explicitly postponed

- Rewiring the 5 direct `lead.stage = ...` assignments to go through
  `transition_lead_stage()` (section 7). Explicitly not done because at
  least one call site (the webhook handler) can legitimately fire again
  for a lead already past the target stage (e.g. a second reply from a
  lead already at `replied`), and `transition_lead_stage()` currently
  raises `ValueError` for a transition not in its allowed list. Wiring
  this in safely requires deciding the right behavior for that case
  (no-op vs. extend the adjacency list vs. re-validate) and re-testing
  the webhook/send code paths, which are already working and tested --
  not something to change close to the end of this task without
  dedicated attention.
- Consolidating `run_publisher`'s per-landing failure handling with the
  single-landing endpoint's (now more complete) error-message storage
  (`docs/MVP_LEGACY_DELETION_CANDIDATES.md` item 4).
- The three missing database indexes reported by
  `scripts/check_migrations.py` (section 10) -- performance, not
  correctness, and outside this task's defect-fixing scope.
- Actually deleting anything listed in
  `docs/MVP_LEGACY_DELETION_CANDIDATES.md` -- recorded only, per section
  5's explicit "record deletion candidates separately" instruction.
- Running `scripts/smoke_mvp_pipeline.sh` against a real Docker
  installation (section 9) -- no Docker daemon was available in this
  session's sandbox.
