# Leadgen Agent — project progress review

Date: 2026-07-28
Branch: `work/mvp-pipeline-stabilization`

## Current product goal

Prove one safe, repeatable business flow:

```text
import one company
→ enrich the lead
→ generate a landing page
→ manually review and publish it
→ manually approve one WhatsApp message
→ send through mock/sandbox mode
→ receive and store a reply
```

The project must remain a single repository with the existing FastAPI/PostgreSQL/Redis/RQ stack and one default worker.

## What is already done

### Product workflow

- Lead collection/import exists.
- Lead enrichment exists.
- Content generation exists with template/mock providers.
- Landing review, approval and publication exist.
- Outreach campaign/message generation exists.
- Manual message approval exists.
- Mock and WhatsApp outreach provider paths exist.
- Incoming WhatsApp webhook handling exists.
- Admin interface exists for the main MVP entities.

### Simplification

- Default Docker runtime was reduced to PostgreSQL, Redis, migrations, API, one shared worker and preview.
- Separate workers are disabled by default behind the `advanced` profile.
- Verified unused runtime stubs and legacy workers were removed.
- Simplicity First is mandatory through `AGENTS.md` and `skills/simplicity-first/SKILL.md`.
- The project simplicity review scored 18/20.

### Stability fixes

A live MVP run found and fixed four blocking defects:

1. Missing `python-multipart` prevented form routes from importing.
2. Cyrillic lead names collapsed into the same landing slug.
3. Content generation crashed while mutating a frozen dataclass.
4. The sender rejected messages after the API moved them to `queued` or `retrying`.

Regression tests were added and the reported suite increased from 261 to 269 passing tests.

## Current maturity assessment

### Ready

- Architecture for MVP validation.
- Local default runtime.
- Main domain models and API routes.
- Manual approval model.
- Mock provider path.
- Basic Russian/Kazakhstan data support.

### Partially ready

- Full workflow testing: a happy-path test exists, but previous live testing showed that isolated tests did not catch worker-to-worker integration failures.
- Duplicate protection: several individual safeguards exist, but the complete workflow has not yet been proven idempotent.
- Failure recovery: failures are stored in several components, but operator retry actions are not consistently available in the admin interface.
- Status consistency: transitions exist across Lead, ContentGeneration, LandingPage and OutreachMessage, but they need one documented and tested state flow.
- Docker smoke validation: a smoke script exists, but the final stabilization instruction requires a complete publish/send/webhook verification.

### Not ready for real outreach

- No verified complete automated E2E pipeline after the latest showstopper fixes.
- No verified protection against repeated publish/send/webhook operations across the whole workflow.
- No verified simple retry workflow for an operator.
- GitHub status checks are not currently visible through the connector for the latest commit.
- Real Meta credentials and approved templates have not been validated in this review.

## Progress estimate

- Core MVP implementation: 80%
- Safe sandbox pilot readiness: 65%
- Real-client pilot readiness: 45%
- Production-scale readiness: intentionally not targeted

The project is functionally advanced but still needs workflow-level stabilization before contacting real companies.

## Immediate work order

### Slice 1 — workflow-level tests

1. Inspect `tests/test_mvp_flow.py` and existing worker regression tests.
2. Add one automated test that calls the real enrichment, content generation, publication, outreach sender and webhook processing functions in sequence.
3. Use an isolated database and temporary publication directory.
4. Confirm Russian/Kazakh company data and a Kazakhstan phone number.

### Slice 2 — duplicate and retry safety

1. Add repeated publish protection tests.
2. Add double-send protection tests.
3. Add duplicate webhook protection tests.
4. Add retry tests for failed generation, publication and permitted send failures.

### Slice 3 — operator recovery

1. Add minimal `Повторить` POST actions to the existing admin pages.
2. Reuse authentication and CSRF protection.
3. Reject retries for DNC, invalid recipients and permanent policy blocks.
4. Show clear Russian feedback.

### Slice 4 — status and smoke verification

1. Document allowed MVP status transitions.
2. Correct only demonstrated inconsistencies.
3. Update the Docker smoke script to verify landing output, mock send and webhook reply.
4. Produce `docs/MVP_PIPELINE_STABILIZATION_REPORT.md`.

## Explicit non-goals

Do not add:

- new services or repositories;
- a second database;
- additional queue technology;
- microservices;
- a separate dashboard;
- Prometheus/Grafana;
- generalized workflow or idempotency frameworks;
- new outreach channels;
- mass automatic outreach;
- multi-tenant functionality.

## Evidence required before pilot

The sandbox pilot may start only after:

- the complete automated pipeline test passes;
- repeated send and webhook tests pass;
- an operator can see and retry recoverable failures;
- the Docker smoke pipeline passes from a clean start;
- outreach remains sandbox-restricted to an explicit allowlist;
- the final report records exact test output and known limitations.

## User input that may be needed later

No user input is required to begin code stabilization with mock providers.

Before a real WhatsApp sandbox test, request only:

- the exact phone number to add to the sandbox allowlist;
- confirmation that the Meta WhatsApp test number or production number is available;
- the approved message template name and language, if Meta template sending is used.
