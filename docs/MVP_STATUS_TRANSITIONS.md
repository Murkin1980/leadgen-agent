# MVP status transitions

This document is the source of truth for the current Leadgen Agent MVP workflow.
It describes only the validated MVP path and deliberately excludes speculative workflow-engine behavior.

## Core rule

A parent entity must not move to a success state before the operation that proves that state has completed successfully.

Examples:

- a lead is not `published` until landing files are written and publication succeeds;
- a lead is not `contacted` until the provider returns a successful send result;
- a message is not `sent` before provider success;
- an inbound webhook is processed once per provider event/message ID;
- terminal policy blocks are not automatically retried.

## ContentGeneration

Allowed transitions:

```text
queued -> running
running -> succeeded
running -> rejected
running -> failed
failed -> queued      # explicit admin retry only
rejected -> queued    # explicit admin retry only
```

Terminal for the current attempt:

- `succeeded`
- `failed`
- `rejected`

Rules:

- `succeeded` requires valid generated content and a linked LandingPage.
- `failed` must contain a readable `error_message`.
- retry clears `error_message`, `started_at`, and `completed_at` before enqueueing.
- retry must not create an unrelated duplicate landing page.

## LandingPage

Allowed MVP transitions:

```text
draft/needs_review -> approved/approved
approved/approved -> generated/approved
                    -> published/published
approved/approved -> failed/approved      # publication/rendering failure
needs_review -> failed/rejected            # manual rejection
failed/approved -> approved/approved       # explicit publication retry only
```

Rules:

- manual rejection is not a publication retry candidate;
- only `failed` + `review_status=approved` may be retried as publication;
- publication writes files before setting `published`;
- repeated publication must be safe and replace the same slug atomically;
- the linked lead becomes `published` only after publication succeeds.

## OutreachMessage

Allowed MVP transitions:

```text
needs_review -> approved
approved -> queued
queued -> sent
queued -> failed
queued -> blocked
queued -> retrying
retrying -> sent
retrying -> failed
retrying -> dead_letter
failed(retryable=true) -> queued   # explicit admin retry only
sent -> delivered
sent/delivered -> read
sent/delivered/read -> replied
approved/queued/retrying -> cancelled  # inbound reply or operator action
```

Terminal/no-op statuses for repeated worker execution:

- `sent`
- `delivered`
- `read`
- `replied`
- `failed`
- `dead_letter`
- `cancelled`
- `blocked`

Rules:

- `blocked`, `dead_letter`, `cancelled`, DNC, invalid recipient, and permanent policy failures are not shown as retryable admin operations;
- `failed` may be manually retried only when `retryable=true`;
- provider success must exist before `sent`;
- repeated worker execution after a terminal status must not change status, error reason, provider ID, timestamps, or attempt count;
- the lead becomes `contacted` only after provider success.

## Lead

Relevant MVP stages:

```text
new
landing_generated
ready_for_outreach
contacted
replied
interested
won
lost
do_not_contact
```

Rules:

- content-generation failure does not advance the lead;
- publication failure does not mark the lead `published`;
- blocked or failed outreach does not mark the lead `contacted`;
- successful provider send may move `ready_for_outreach -> contacted`;
- a valid inbound message moves the lead to `replied`;
- inbound reply cancels pending approved/queued/retrying messages for the same lead;
- DNC and withdrawn/blocked consent prevent retry and sending.

## WhatsApp webhook idempotency

Delivery status events use a stable provider event key derived from provider message ID, state, and provider timestamp.

Inbound messages are unique by provider message ID.

Expected behavior:

```text
first delivery/inbound event -> changed = 1
same event repeated          -> changed = 0
```

A duplicate event must not:

- create another InboundMessage;
- create another OutreachEvent;
- advance the lead twice;
- cancel messages twice;
- alter timestamps a second time.

## Manual recovery page

Location:

```text
/admin/recovery
```

Displayed operations:

- failed/rejected content generations;
- failed publication where landing remains approved;
- failed outreach messages where `retryable=true`.

Never displayed:

- blocked;
- cancelled;
- dead-letter;
- sent/delivered/read/replied;
- DNC leads;
- permanent provider/policy failures.

All recovery actions require:

- authenticated admin cookie;
- POST request;
- valid CSRF token;
- current-state validation immediately before enqueueing;
- an audit-log entry.

## Deferred

The MVP does not need a generalized workflow engine, distributed state machine, new queue technology, or separate dead-letter dashboard.
Add complexity only after a measured failure demonstrates that these explicit transitions are insufficient.
