# WhatsApp Production Runbook

## Overview

This runbook covers operational procedures for the WhatsApp Cloud API integration
in the Leadgen Agent production environment.

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OUTREACH_MODE` | Yes | `disabled` / `sandbox` / `production` |
| `OUTREACH_ENABLED` | Yes | Legacy toggle (`true`/`false`), kept for backward compat |
| `WHATSAPP_CLOUD_API_TOKEN` | Production | Meta Graph API bearer token |
| `WHATSAPP_CLOUD_PHONE_NUMBER_ID` | Production | Sending phone number ID from Meta |
| `WHATSAPP_GRAPH_API_VERSION` | No | Graph API version (default: `v23.0`) |
| `WHATSAPP_APP_SECRET` | Production | App secret for HMAC webhook signature verification |
| `WHATSAPP_WEBHOOK_VERIFY_TOKEN` | Yes | Token used during webhook subscription |
| `WHATSAPP_REQUEST_TIMEOUT_SECONDS` | No | HTTP timeout for Graph API calls (default: 30) |
| `WHATSAPP_SERVICE_WINDOW_HOURS` | No | Hours after last inbound where free-form text is allowed (default: 24) |
| `WHATSAPP_ALLOW_MOCK_WEBHOOKS` | Dev only | Skip signature check when `APP_ENV != production` |
| `OUTREACH_SANDBOX_ALLOWLIST` | Sandbox | Comma-separated phones allowed in sandbox mode |
| `OUTREACH_QUIET_HOURS_START` | No | Quiet hours start (default: `22:00`) |
| `OUTREACH_QUIET_HOURS_END` | No | Quiet hours end (default: `07:00`) |
| `OUTREACH_MAX_PER_HOUR` | No | Hourly rate limit (default: `30`) |
| `OUTREACH_SEND_MAX_RETRIES` | No | Max retry attempts before dead-letter (default: `3`) |
| `OUTREACH_SEND_RETRY_BASE_SECONDS` | No | Base delay for exponential backoff (default: `60`) |

## Deployment Steps

1. Set all required env vars in Cloudflare Pages or your hosting platform.
2. Run Alembic migration: `alembic upgrade head` (applies `006_whatsapp_production`).
3. Verify webhook subscription in Meta Developer Console.
4. Set `OUTREACH_MODE=sandbox` first, add test numbers to `OUTREACH_SANDBOX_ALLOWLIST`.
5. Send a test message to a sandbox-allowed number.
6. Switch to `OUTREACH_MODE=production` after verifying sandbox flow.

## Monitoring

### Key Metrics

```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" http://localhost:8080/metrics/outreach
```

Returns:
- `draft_count` / `needs_review` — messages awaiting approval
- `approved_count` — messages queued for send
- `sent_count` — successfully sent
- `delivered_count` — confirmed delivered by Meta
- `replied_count` — leads who replied
- `failed_count` — permanent failures
- `reply_rate` — (replied / sent) × 100

### Database Queries

```sql
-- Messages stuck in retrying state
SELECT id, attempt_count, next_retry_at, error_message
FROM outreach_messages
WHERE status = 'retrying' AND next_retry_at < NOW();

-- Dead-lettered messages
SELECT id, lead_id, error_message, attempt_count
FROM outreach_messages
WHERE status = 'dead_letter';

-- Messages in last hour
SELECT status, COUNT(*) FROM outreach_messages
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY status;
```

## Common Operations

### Cancel all pending messages for a lead

```python
from app.outreach.service import cancel_pending_follow_ups
count = cancel_pending_follow_ups(db, lead_id)
db.commit()
```

### Manually approve a message

```bash
curl -X POST http://localhost:8080/outreach-messages/{message_id}/approve \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "X-CSRF-Token: $CSRF_TOKEN"
```

### Set lead consent

```bash
curl -X PUT http://localhost:8080/leads/{lead_id}/consent \
  -H "Content-Type: application/json" \
  -d '{"consent_status": "consented", "contact_basis": "business_interest"}'
```

## Phone Number Format

All phone numbers are normalized to Kazakhstan E.164 format: `+7XXXXXXXXXX`.
The `PhoneNumberService` rejects:
- Numbers shorter than 11 digits
- Non-Kazakhstan country codes
- Service numbers (e.g., `+70000000000`)
- Obviously invalid numbers (e.g., `+77008888888` — repeated digits)

## Retry & Dead-Letter

Messages fail with temporary errors (429, 5xx, network) are retried with
exponential backoff: `base_seconds × 2^attempt + jitter`.

Non-retryable errors: `auth_error`, `invalid_number`, `template_not_approved`.

After `OUTREACH_SEND_MAX_RETRIES` attempts, messages move to `dead_letter` status
and must be investigated manually.

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| All messages blocked | `OUTREACH_MODE=disabled` | Set mode to `sandbox` or `production` |
| Sandbox messages fail | Recipient not in allowlist | Add phone to `OUTREACH_SANDBOX_ALLOWHOOKS` |
| 401 from Graph API | Invalid/expired token | Rotate `WHATSAPP_CLOUD_API_TOKEN` |
| 429 from Graph API | Rate limited | Wait or reduce `OUTREACH_MAX_PER_HOUR` |
| Messages stuck in `retrying` | Temporary API failure | Check `next_retry_at`, wait or manually retry |
| Messages in `dead_letter` | Max retries exceeded | Check error, fix, and re-queue |
