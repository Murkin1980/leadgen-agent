# Leadgen Agent — MVP Checkpoint Plan

Date: 2026-09-28
Decision: EXTEND_EXISTING
Target: validate the existing MVP before any deep architecture change.

## Operating rule

Work checkpoint by checkpoint. Do not start the next checkpoint until the current checkpoint has a recorded PASS or an explicit BLOCKED decision. Do not merge checkpoint PRs unless Murat explicitly says to merge.

No new repository, dashboard, provider, queue, database, CRM, generalized workflow engine, or infrastructure is in scope.

## CP-00 — Baseline and scope lock

Goal: establish a reproducible baseline from current `master` and PR #2.

Required:
- read `AGENTS.md`, `SIMPLICITY_REVIEW.md`, this checkpoint plan, and PR #2;
- record current `master` SHA and PR #2 head SHA;
- inspect the diff and identify anything outside MVP stabilization;
- confirm the canonical MVP path:
  lead → landing generation → operator review → publish → message approval → WhatsApp send → inbound reply.

PASS:
- baseline SHAs recorded;
- no unexplained scope expansion;
- validation commands identified.

No product code changes unless required to make validation reproducible.

## CP-01 — Stabilization validation

Goal: prove PR #2 works as a complete stabilization slice.

Run from the PR #2 branch:
- full Python test suite;
- migration verification;
- `scripts/local_validate_mvp.sh`;
- strict Docker smoke test;
- verify API, worker and preview startup;
- verify no production-only dependency is required for the MVP path.

PASS:
- all required tests pass;
- Docker smoke passes;
- no unresolved regression in the MVP path.

BLOCKED:
- record exact failing command, error, affected component and minimal next action.
- do not hide failures by weakening tests.

Deliverable:
- `docs/checkpoints/CP-01-STABILIZATION-VALIDATION.md`.

## CP-02 — PR #2 closure readiness

Goal: make PR #2 safe to merge, without merging it.

Required:
- fix only defects discovered by CP-01;
- rerun all CP-01 validation;
- review idempotency for repeated send, publish and webhook;
- verify terminal outreach statuses remain terminal;
- verify admin message approval is POST-only + auth + CSRF;
- verify recovery actions cannot duplicate completed work;
- update PR description with evidence.

PASS:
- PR #2 is non-draft/merge-ready from a technical perspective;
- validation evidence is recorded;
- no known P0/P1 defect remains.

Deliverable:
- `docs/checkpoints/CP-02-PR2-READY.md`.

STOP after PASS. Do not merge PR #2 without Murat's explicit command.

## CP-03 — Post-merge clean baseline

Start only after Murat explicitly merges PR #2.

Goal: verify `master` after merge.

Required:
- sync fresh `master`;
- run the same core test + smoke suite;
- confirm README commands still work;
- confirm migrations are coherent;
- confirm no branch-only assumptions remain.

PASS:
- clean checkout of `master` reproduces the MVP.

Deliverable:
- `docs/checkpoints/CP-03-POST-MERGE-BASELINE.md`.

## CP-04 — Sandbox operator pilot

Goal: prove the workflow as a user/operator, not only as tests.

Use safe sandbox/mock outreach only.

Scenario:
1. import/create a realistic Almaty lead;
2. generate landing;
3. review and approve landing;
4. publish;
5. create/review/approve outreach message;
6. send through mock or explicitly configured WhatsApp sandbox;
7. receive/replay inbound webhook;
8. confirm lead reaches replied state.

Measure each step:
- elapsed time;
- manual actions;
- failure/retry count;
- operator friction;
- worker job duration where applicable.

PASS:
- one complete operator-driven cycle succeeds;
- measurements are captured;
- no manual database edits are needed.

Deliverable:
- `docs/checkpoints/CP-04-SANDBOX-PILOT.md`.

## CP-05 — 10-lead validation batch

Goal: get evidence about reliability and actual complexity.

Run 10 realistic leads through the same MVP path. Do not automate away operator approval.

Capture:
- generation success rate;
- publication success rate;
- send success rate;
- inbound webhook correctness;
- median/p95 durations where meaningful;
- retries/duplicates;
- setup and operator time;
- failure categories.

PASS:
- results for all 10 leads are recorded;
- failures have concrete causes;
- enough timing evidence exists to evaluate Redis/RQ/PostgreSQL complexity.

Deliverable:
- `docs/checkpoints/CP-05-10-LEAD-VALIDATION.md`.

## CP-06 — Architecture evidence review [DEEP-CHANGE GATE]

Goal: decide whether current infrastructure is justified.

Compare measured evidence against:
A. current: FastAPI + PostgreSQL + Redis/RQ + nginx;
B. candidate validation architecture: FastAPI + SQLite + synchronous services + local static serving.

This checkpoint is analysis only.

Required questions:
- Do generation/send operations actually require background jobs?
- Did Redis/RQ prevent real problems or create more failure modes?
- Is PostgreSQL required for the validation workload?
- Can generated pages be served directly for pilot use?
- What code/infrastructure can be deleted without reducing validated business value?

PASS:
- evidence-based recommendation documented;
- exact migration/deletion surface listed;
- risk and rollback described.

Deliverable:
- `docs/checkpoints/CP-06-ARCHITECTURE-GATE.md`.

STOP. Removing Redis/RQ/PostgreSQL, changing persistence, or restructuring the runtime is a deep architecture change and requires Murat's explicit approval.

## CP-07 — Real outreach pilot

Start only after explicit approval for real outreach and required WhatsApp credentials/policy checks.

Goal: validate business outcome, not infrastructure.

Run a small controlled batch with real eligible leads and explicit operator approval before every outbound send.

Capture:
- delivered/sent state;
- replies;
- positive replies;
- operator time;
- failures;
- do-not-contact/consent safeguards.

PASS:
- at least one real end-to-end outreach cycle is proven and results are recorded.

No scale-up is authorized by this checkpoint.

Deliverable:
- `docs/checkpoints/CP-07-REAL-PILOT.md`.

## Definition of MVP evidence complete

MVP evidence is complete when:
- stabilization is merged and reproducible;
- sandbox operator flow works;
- 10-lead batch evidence exists;
- architecture decision is based on measurements;
- a controlled real pilot has been explicitly approved and executed.

Only then consider CRM, follow-up automation, dashboards, extra providers, multi-tenancy or scale infrastructure.
