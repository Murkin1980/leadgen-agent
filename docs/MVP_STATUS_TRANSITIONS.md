# MVP Status Transitions

Audit of the state machines behind the MVP pipeline, per
`docs/CODEX_NEXT_MVP_PIPELINE_STABILIZATION.md` section 4.5. Covers
`Lead`, `ContentGeneration`, `LandingPage`, the publication/deployment
record, `OutreachMessage`, and inbound message/event handling.

## 1. `Lead.status` (`app/models/lead.py`)

```
collected -> enriched -> generated -> published
          -> failed
          -> rejected
```

| From | To | Set by |
|---|---|---|
| `collected` | `enriched` | `run_enricher` on success |
| `collected` / `enriched` | `failed` | `run_enricher` on a per-lead exception (section 4.3 fix) |
| `enriched` | `published` | `POST /landings/{id}/publish` or `run_publisher`, only after files are successfully written and `publish_site()` returns a URL |

**`generated` is defined but never set anywhere in the code.** Nothing
transitions a lead into it. Candidate for
`docs/MVP_LEGACY_DELETION_CANDIDATES.md`.

**`rejected` is defined but nothing sets `Lead.status` to it either**
(landing rejection sets `LandingPage.review_status = rejected`, not
`Lead.status`). Same candidate list.

Confirmed correct: a lead is **never** marked `published` unless
`publish_site()` actually succeeded -- both `run_publisher` and (after
the section 4.4 fix) `POST /landings/{id}/publish` only set
`Lead.status = published` inside the success path, after file writes
complete. On any exception, only the landing is marked `failed`; the
lead's status is left untouched.

## 2. `Lead.stage` (`app/models/stage.py`, funnel state distinct from `Lead.status`)

```
new -> qualified -> landing_generated -> needs_review -> ready_for_outreach
    -> contacted -> replied -> interested -> proposal_sent -> won
                            -> lost -> new
    -> do_not_contact -> new (anywhere)
```

Full adjacency list lives in `app/outreach/stage_service.py`'s
`VALID_TRANSITIONS` and is enforced by `transition_lead_stage()`, which
also validates the transition, writes a `LeadStageHistory` row, and
flips `do_not_contact` consistently.

**Known gap, not fixed in this pass:** `transition_lead_stage()` is the
only validated, history-tracked way to change `lead.stage`, but it is
actually used in exactly one place
(`app/api/outreach_routes.py:370`). Five other call sites assign
`lead.stage` directly, bypassing both validation and history:

- `app/api/whatsapp_routes.py:94` -- webhook sets `"replied"` directly
- `app/outreach/webhook_handler.py:190` -- same, in the legacy/advanced
  webhook handler
- `app/workers/outreach_sender_worker.py:125` -- sets `"contacted"` on
  successful send
- `app/api/outreach_routes.py:423` -- sets `do_not_contact` directly
- `app/retention.py:197` -- restores a previously-saved stage during
  anonymization rollback (this one is arguably correct to bypass
  validation, since it's restoring a known-good prior value, not
  making a new business transition)

Practical effect: these four direct-assignment sites do not produce a
`LeadStageHistory` entry, so the "Stage History" section of the admin
lead-detail page under-reports real transitions (e.g. it won't show
when/why a lead moved to `replied` from a webhook, or to `contacted`
after a send). This is an observability gap, not a false-state bug --
in every case the *value* being assigned is a legitimate next stage for
the lead's situation.

**Explicitly postponed** (see the stabilization report): routing these
four call sites through `transition_lead_stage()` was not done in this
pass. `transition_lead_stage()` raises `ValueError` when the target
stage isn't in the source stage's allowed list, and at least one of
these call sites (the webhook handler) can legitimately fire more than
once for a lead already past the target stage (e.g. a second reply from
a lead already at `replied`). Wiring this in safely requires deciding
the right behavior for that case (no-op vs. re-validate vs. extend the
adjacency list) and re-testing the webhook path, which touches
already-tested, working production code close to the end of this task.
Flagging it here rather than making a rushed change to a proven path.

## 3. `ContentGeneration.status` (`app/models/content_generation.py`)

```
queued -> running -> succeeded
                   -> failed
       -> rejected (not currently set anywhere -- see deletion candidates)
```

Set by `run_content_generator` (`app/workers/content_generator_worker.py`).
Confirmed: a generation is only `succeeded` after the landing's
`profile_json` has been validated and the `LandingPage` row committed.
On any exception, it's `failed` with `error_message` populated.

Idempotency (section 4.2): `POST /leads/{id}/content-generations`
rejects a second request with 409 while one is `queued`/`running` for
the same lead, and reuses the lead's existing `LandingPage` on a
regeneration instead of creating a second one with the same slug.

## 4. `LandingPage.status` / `LandingPage.review_status`

Two parallel fields track different things:

- `status`: `draft -> needs_review -> approved -> published -> deployed`, or `failed`
- `review_status`: `needs_review -> approved -> published`, or `rejected`

```
needs_review --(admin approve)--> approved --(publish)--> published
      |                               |
      +--(admin reject)--> rejected   +--(publish error)--> status=failed
                                           (review_status stays "approved" --
                                            the landing is still eligible
                                            for a publish retry)
```

Confirmed correct after the section 4.4 fix to
`POST /landings/{id}/publish`: `status` is only set to `published`
after `render_landing`, `save_landing`, and `publish_site()` all
succeed. Before that fix, a failure in any of those three calls was an
*unhandled exception* -- the landing silently stayed `approved`/whatever
it was, with no `failed` state and no stored error, which also meant
there was nothing for the section 4.4 retry action to detect. Both
`run_publisher` (job-based) and the single-landing endpoint now handle
failures the same way: `status = failed`, and a readable error is
stored (`review_note` for the endpoint path; the job's per-landing loop
in `run_publisher` also sets `status = failed` and continues to the
next landing without a stored message today -- see deletion/cleanup
candidates for unifying this).

`deployed` (Cloudflare Pages / the advanced deployment flow) is a
separate status tracked on the `Deployment` model, not folded into
`LandingPage.status` transitions here.

## 5. `Deployment.status` (`app/models/deployment.py`, advanced/Cloudflare flow)

```
queued -> running -> succeeded
                   -> failed
```

Out of scope for the default MVP six-service runtime (Cloudflare
deployment is part of the advanced profile), included here only for
completeness.

## 6. `OutreachMessage.status` (`app/models/campaign.py`)

```
draft -> needs_review -> approved -> queued -> sent -> delivered -> read -> replied
                              |          |
                              |          +-> retrying -> (loops back to queued via RQ)
                              |          |         |
                              |          |         +-> dead_letter (retries exhausted)
                              |          +-> failed (permanent provider failure)
                              |          +-> blocked (policy check failed: DNC,
                              |               sandbox mismatch, disabled, consent)
                              +-> cancelled
```

Set by `run_outreach_generator` (draft -> needs_review or blocked),
`POST /outreach-messages/{id}/approve` (-> approved),
`POST /outreach-messages/{id}/send` (-> queued),
`run_outreach_sender` (-> sent / blocked / failed / retrying / dead_letter).

Confirmed correct: `status` is only set to `sent` inside
`if result.success:`, after the provider call returns success --
never before. `blocked` and `dead_letter` are distinct on purpose:

- `blocked` = a **policy** said no (DNC, sandbox mismatch, outreach
  disabled, consent not approved). `retryable = False`. No admin retry
  action is offered for these (section 4.4) -- retrying a policy block
  without the underlying condition changing would defeat the policy.
- `dead_letter` = **transient** provider failures were retried until
  `outreach_send_max_retries` was exhausted. `retryable = True`. This is
  what the section 4.4 retry action targets, via the existing
  `app.outreach.dead_letter.requeue_dead_letter`, which re-validates
  DNC, consent (in production mode), sandbox allowlist (in sandbox
  mode), phone validity, and `outreach_enabled` before allowing the
  retry -- so a retry can never bypass those checks and return a
  permanently-blocked message to a sendable state.

**Bug found and fixed in this pass:** `is_sandbox_allowed()`
(`app/outreach/service.py`, the only caller is
`requeue_dead_letter`) compared the raw `recipient` string against the
sandbox allowlist without normalizing it first. WhatsApp recipients are
stored as full `https://wa.me/<digits>` URLs, so this check could never
match a bare `+7XXXXXXXXXX` allowlist entry -- every dead-letter retry
for a real WhatsApp message in sandbox mode was rejected with "not in
sandbox allowlist", even when the phone genuinely was allowlisted. Fixed
to normalize via `PhoneNumberService.normalize()` first, matching how
the live send path's own check (`_production_policy_allows` in
`outreach_sender_worker.py`) already did it.

Idempotency (section 4.2): sending is guarded twice -- the API endpoint
only accepts `status == approved` (rejects a second click with 400 once
the message is `queued`), and `can_send_message()` accepts the
legitimate in-flight states (`approved`, `queued`, `retrying`) so the
worker doesn't reject its own queued job, but nothing outside those
three states is ever accepted for send.

## 7. Inbound message handling (`app/models/whatsapp.py`, webhook)

`InboundMessage.status`: `new -> handled`. `ignored` is defined but
never set anywhere -- deletion candidate.

Deduplication (section 4.2, confirmed by test): the webhook handler
(`app/api/whatsapp_routes.py`) looks up `InboundMessage` by
`provider_message_id` before creating a new row, so replaying the same
WhatsApp webhook event is a no-op the second time --
`POST /webhooks/whatsapp` with an identical payload returns
`{"changed": 0}` and does not create a second row or re-fire the lead
stage change. The same pattern (checking `OutreachEvent.provider_event_id`)
protects delivery-status webhook events from double-processing.

## Summary against the "at minimum, prevent these false states" checklist

| Required guarantee | Status |
|---|---|
| Lead marked published when publishing failed | Confirmed never happens; fixed a path where it *could* have gone undetected (section 4.4) |
| Lead marked contacted when send was blocked/failed | Confirmed never happens -- `lead.stage = contacted` only inside the success branch |
| Landing marked published before files are written | Confirmed never happens, after the section 4.4 fix to the single-landing publish endpoint |
| Message marked sent before provider success | Confirmed never happens |
| Duplicate webhook moving a record twice | Confirmed prevented, by `provider_message_id`/`provider_event_id` dedup |
| Retry returning a permanently blocked item to sendable | Confirmed prevented, via `requeue_dead_letter`'s re-validation (and the sandbox-check bug fix above, which had been *silently over-blocking* legitimate retries -- the opposite failure mode, but still worth fixing) |
