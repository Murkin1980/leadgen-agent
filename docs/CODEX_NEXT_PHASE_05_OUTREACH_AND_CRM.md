# Phase 05 — Outreach, CRM Pipeline, Notifications, and Delivery Tracking

## Goal

Turn approved and published landing pages into a controlled sales workflow without automatic spam.

The system must let an operator select qualified leads, prepare personalized outreach drafts, approve each message, send through pluggable providers, track delivery and replies, and manage the lead through a lightweight CRM pipeline.

## Critical rules

1. No message may be sent automatically immediately after collection.
2. Every first-contact message requires manual approval.
3. Respect provider terms, local laws, opt-out requests, quiet hours, and rate limits.
4. Do not scrape private contact data or infer personal data.
5. Never send to a lead marked `do_not_contact`.
6. Do not expose provider secrets in logs, API responses, or admin HTML.
7. Tests must use mock providers only.

---

## 1. CRM pipeline

Add a `LeadStage` enum:

- `new`
- `qualified`
- `landing_generated`
- `needs_review`
- `ready_for_outreach`
- `contacted`
- `replied`
- `interested`
- `proposal_sent`
- `won`
- `lost`
- `do_not_contact`

Add fields to `Lead`:

- `stage`
- `assigned_to`
- `last_contacted_at`
- `next_follow_up_at`
- `do_not_contact`
- `do_not_contact_reason`
- `preferred_channel`
- `notes`

Create Alembic migration `005`.

Add stage history model:

### LeadStageHistory

- `id`
- `lead_id`
- `from_stage`
- `to_stage`
- `changed_by`
- `reason`
- `created_at`

Every stage change must create a history row.

---

## 2. Outreach campaign model

Create models:

### OutreachCampaign

- `id`
- `name`
- `channel`
- `status`
- `language`
- `created_by`
- `scheduled_at`
- `started_at`
- `completed_at`
- `created_at`
- `updated_at`

Statuses:

- `draft`
- `ready`
- `running`
- `paused`
- `completed`
- `cancelled`
- `failed`

### OutreachMessage

- `id`
- `campaign_id`
- `lead_id`
- `channel`
- `recipient`
- `subject`
- `body`
- `status`
- `provider_message_id`
- `approved_by`
- `approved_at`
- `sent_at`
- `delivered_at`
- `read_at`
- `replied_at`
- `failed_at`
- `error_message`
- `created_at`
- `updated_at`

Statuses:

- `draft`
- `needs_review`
- `approved`
- `queued`
- `sent`
- `delivered`
- `read`
- `replied`
- `failed`
- `cancelled`
- `blocked`

Add unique protection against duplicate first-contact messages for the same lead, channel, and campaign.

---

## 3. Outreach provider abstraction

Create:

```python
class OutreachProvider(Protocol):
    def send(self, message: OutreachMessage) -> SendResult:
        ...

    def get_status(self, provider_message_id: str) -> DeliveryStatus:
        ...
```

Implement:

- `MockOutreachProvider`
- `EmailOutreachProvider` interface/stub
- `WhatsAppCloudProvider` interface/stub
- `TelegramOutreachProvider` interface/stub

Do not enable real sending by default.

Environment variables:

```env
OUTREACH_PROVIDER=mock
OUTREACH_ENABLED=false
OUTREACH_MAX_PER_HOUR=20
OUTREACH_QUIET_HOURS_START=20:00
OUTREACH_QUIET_HOURS_END=09:00
OUTREACH_TIMEZONE=Asia/Almaty
```

For WhatsApp Cloud API prepare configuration fields, but keep provider disabled unless all required values are present.

---

## 4. Message generation

Create a message-generation service that uses only verified lead data and the approved landing page.

Supported languages:

- Russian
- Kazakh

Generate:

- first-contact message;
- follow-up message;
- short WhatsApp version;
- email version;
- Telegram version.

Rules:

- no invented claims;
- no fake urgency;
- no promises of guaranteed sales;
- include company name when available;
- include preview URL;
- keep WhatsApp first contact concise;
- include opt-out wording where appropriate;
- never include raw technical metadata.

All generated messages must start in `needs_review`.

---

## 5. Approval workflow

API endpoints:

```http
POST /campaigns
GET /campaigns
GET /campaigns/{id}
POST /campaigns/{id}/add-leads
POST /campaigns/{id}/generate-messages
GET /campaigns/{id}/messages
POST /outreach-messages/{id}/approve
POST /outreach-messages/{id}/reject
PUT /outreach-messages/{id}
POST /outreach-messages/{id}/send
POST /campaigns/{id}/send-approved
POST /campaigns/{id}/pause
POST /campaigns/{id}/resume
POST /campaigns/{id}/cancel
```

Sending rules:

- only `approved` messages can be queued;
- `OUTREACH_ENABLED` must be true for non-mock providers;
- lead must not be `do_not_contact`;
- campaign must not be paused or cancelled;
- quiet hours must be enforced;
- hourly rate limit must be enforced in Redis;
- duplicate first contact must be blocked.

---

## 6. Worker and queues

Add Redis queues:

- `outreach_generate`
- `outreach_send`
- `outreach_status`

Add workers:

- `outreach_generator_worker.py`
- `outreach_sender_worker.py`
- `outreach_status_worker.py`

Add corresponding Docker Compose services.

Use retry with bounded exponential backoff for transient provider errors.

Permanent failures must not be retried endlessly.

---

## 7. Delivery events and webhooks

Create model:

### OutreachEvent

- `id`
- `message_id`
- `event_type`
- `provider_event_id`
- `payload_json`
- `created_at`

Add webhook endpoints:

```http
POST /webhooks/whatsapp
POST /webhooks/email
POST /webhooks/telegram
```

Requirements:

- verify webhook signatures when provider supports them;
- idempotently process duplicate events;
- store raw payload safely;
- redact secrets and tokens;
- update message status monotonically;
- mark lead stage `replied` when a verified inbound reply is received.

Real webhook integrations may remain provider stubs, but mock webhook flow must be fully testable.

---

## 8. Follow-up scheduling

Add a simple follow-up scheduler.

Rules:

- follow-up only after an approved first message;
- never follow up after reply, opt-out, won, lost, or do-not-contact;
- configurable delay;
- maximum number of follow-ups;
- manual approval required for every follow-up in this phase.

Environment variables:

```env
FOLLOW_UP_ENABLED=true
FOLLOW_UP_DELAY_HOURS=48
FOLLOW_UP_MAX_COUNT=2
```

Add endpoint:

```http
GET /follow-ups/due
POST /follow-ups/{message_id}/generate
```

---

## 9. Admin UI

Extend the existing Jinja2 admin panel.

Add pages:

- CRM pipeline board;
- lead details and stage history;
- campaigns list;
- campaign details;
- message review screen;
- delivery status screen;
- opt-out and do-not-contact management;
- follow-ups due.

No frontend framework is required.

Use CSRF protection for state-changing HTML forms.

Require authentication for all admin pages.

---

## 10. Security

Implement:

- CSRF protection;
- secure session cookies in production;
- constant-time password verification;
- login rate limiting;
- webhook signature validation interfaces;
- secrets redaction in logs;
- recipient validation;
- message length limits;
- HTML escaping in admin UI;
- audit log for approve, edit, send, cancel, opt-out, and stage changes.

Create `AuditLog` model if one does not already exist.

---

## 11. Metrics

Add endpoint:

```http
GET /metrics/outreach
```

Return:

- draft count;
- approved count;
- sent count;
- delivered count;
- replied count;
- failed count;
- opt-out count;
- reply rate;
- conversion by stage;
- campaign breakdown.

Do not expose phone numbers, email addresses, tokens, or message bodies in metrics.

---

## 12. Tests

Add tests for:

- stage transitions and history;
- campaign creation;
- message generation;
- approval requirement;
- do-not-contact blocking;
- duplicate prevention;
- quiet hours;
- hourly rate limit;
- mock sending;
- retry behavior;
- webhook idempotency;
- status progression;
- opt-out handling;
- follow-up eligibility;
- admin authentication;
- CSRF protection;
- audit logging;
- metrics calculations.

No test may call a real messaging provider.

Target: at least 220 total passing tests.

---

## 13. Docker smoke test

Extend `scripts/smoke_test.sh`:

1. create a mock collection job;
2. generate content;
3. approve and publish a landing;
4. create a campaign;
5. add one lead;
6. generate a mock outreach message;
7. approve it;
8. send through mock provider;
9. simulate delivered and replied webhook events;
10. verify lead stage becomes `replied`;
11. verify outreach metrics.

No external network calls.

---

## 14. Documentation

Add:

- `docs/OUTREACH_POLICY.md`
- `docs/CRM_PIPELINE.md`
- `docs/WHATSAPP_CLOUD_SETUP.md`
- `docs/OUTREACH_RUNBOOK.md`

Update README with full operator flow.

---

## Acceptance criteria

The phase is complete when:

1. A lead can be moved through CRM stages with history.
2. An approved landing can be added to a campaign.
3. Personalized messages can be generated in RU and KK.
4. Messages require manual approval.
5. Mock messages can be sent and tracked.
6. Duplicate contact, quiet hours, rate limits, and do-not-contact are enforced.
7. Delivery and reply events are idempotent.
8. Follow-up candidates are calculated safely.
9. Admin UI supports campaign and message review.
10. All tests and Docker smoke tests pass.

## Deliverables from Codex

After implementation, provide:

- changed file list;
- migration summary;
- API endpoint list;
- Docker service list;
- security decisions;
- test results;
- smoke-test output;
- remaining steps for real WhatsApp Cloud API and email provider activation.
