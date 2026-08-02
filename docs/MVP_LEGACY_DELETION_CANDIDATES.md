# MVP Legacy Deletion Candidates

Per `docs/CODEX_NEXT_MVP_PIPELINE_STABILIZATION.md` section 5. These are
candidates found incidentally while stabilizing the MVP pipeline, not
the product of a broad repository-wide cleanup sweep (which is out of
scope for this task). **Nothing in this document has been deleted.**
Each item still needs the full check from section 5 before removal:

- it is not imported;
- it is not referenced by routes, jobs, docs, tests, or Compose;
- no migration depends on it;
- the full test suite and smoke pipeline pass after deletion.

The advanced Docker Compose profile itself is explicitly out of scope
for deletion, per the doc's instruction.

## 1. `Lead.status` values that are never set

`app/models/lead.py`'s `LeadStatus` enum defines `generated` and
`rejected`, but grep across the whole codebase (`app/`) found no place
that ever assigns either one to `Lead.status`:

- `generated`: no assignment anywhere. The transition
  `collected -> enriched -> published` (documented in
  `docs/MVP_STATUS_TRANSITIONS.md`) skips it entirely.
- `rejected`: `LandingPage.review_status` has its own `rejected` value
  (set by `POST /landings/{id}/reject`), but that never propagates to
  `Lead.status`. Nothing else sets it either.

Before deleting: confirm no admin UI filter, external integration, or
downstream analytics query still checks for these two string values
even though nothing produces them.

## 2. `InboundMessageStatus.ignored`

`app/models/whatsapp.py` defines `new`, `handled`, `ignored`. Only
`new` (default) and `handled` (set in `app/api/whatsapp_routes.py` and
`app/outreach/inbox.py`) are ever assigned. `ignored` is unused.

Before deleting: confirm there isn't a planned use (e.g. explicitly
marking a webhook event as intentionally skipped, as opposed to
processed) that just hasn't been wired up yet -- this one reads more
like an intentionally-reserved value than dead code, so it may be worth
keeping as-is rather than removing.

## 3. `scripts/mvp_smoke_test.sh` vs. the new `scripts/smoke_mvp_pipeline.sh`

The pre-existing `scripts/mvp_smoke_test.sh` assumes services are
already running, swallows nearly every failure with `|| true` /
fallback values, and unconditionally prints "MVP SMOKE TEST PASSED" at
the end regardless of what actually happened during the run. The new
`scripts/smoke_mvp_pipeline.sh` (section 4.7) supersedes it
functionally: it starts the stack itself, validates
`docker compose config`, waits for every service, and genuinely fails
when a step doesn't reach its expected state.

**Not deleted in this pass** -- it's referenced by name in `README.md`
("MVP Smoke Test" section) and `AGENTS.md`, so removing it now would
fail the "not referenced by ... docs" criterion. If the team adopts
`smoke_mvp_pipeline.sh` as the standard, a follow-up change should
update those references and then remove the old script.

## 4. `run_publisher`'s per-landing error message (not a deletion candidate, noted for completeness)

Not something to delete, but adjacent to this review: after the
section 4.4 fix, `POST /landings/{id}/publish` stores a readable error
in `LandingPage.review_note` on failure, but `run_publisher`
(`app/workers/publisher_worker.py`, the job-based batch path) still
only sets `status = failed` without storing a message anywhere. Listed
here rather than in the status-transitions doc because the fix would
plausibly involve consolidating the two publish code paths (endpoint
vs. worker) rather than just adding a field -- a larger change than
this pass's scope. See "Items explicitly postponed" in
`docs/MVP_PIPELINE_STABILIZATION_REPORT.md`.
