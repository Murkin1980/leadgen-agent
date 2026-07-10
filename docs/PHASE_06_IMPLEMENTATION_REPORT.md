# Phase 06 Implementation Report — WhatsApp Production

## Implemented

- Official WhatsApp Cloud API HTTP provider with template and service-window text modes.
- Safe HTTP error classification: permanent 4xx vs retryable 429/5xx/network failures.
- Kazakhstan phone normalization to E.164 and masked logging.
- Signed webhook verification using `X-Hub-Signature-256` and constant-time comparison.
- Meta webhook subscription verification endpoint.
- Idempotent delivery/read/failed event processing.
- Inbound WhatsApp message storage and CRM reply handling.
- Automatic 24-hour service-window tracking after inbound messages.
- Cancellation of pending follow-ups after a reply.
- WhatsApp template persistence and API.
- Consent/contact-basis fields on leads.
- Safe rollout modes: disabled, sandbox allowlist, production.
- Retry scheduling with exponential backoff, jitter and dead-letter status.
- Message idempotency keys and row-level locking during send.
- Alembic migration `006`.
- Environment configuration and phone normalization tests.

## New API

- `GET /webhooks/whatsapp`
- `POST /webhooks/whatsapp`
- `GET /whatsapp/templates`
- `POST /whatsapp/templates`
- `GET /inbound-messages`
- `POST /inbound-messages/{id}/mark-handled`
- `PUT /leads/{id}/consent`

## Production rollout

1. Keep `OUTREACH_MODE=disabled` while applying migration `006`.
2. Configure Meta credentials and webhook URL.
3. Set `OUTREACH_MODE=sandbox` and add only test phones to `OUTREACH_SANDBOX_ALLOWLIST`.
4. Use an approved WhatsApp template and manually approved outreach message.
5. Verify `sent`, `delivered`, `read` and inbound reply webhooks.
6. Review audit logs, DNC and consent status.
7. Only then set `OUTREACH_MODE=production`.

## Required secrets

- `WHATSAPP_CLOUD_API_TOKEN`
- `WHATSAPP_CLOUD_PHONE_NUMBER_ID`
- `WHATSAPP_WEBHOOK_VERIFY_TOKEN`
- `WHATSAPP_APP_SECRET`

Secrets must remain outside the repository.

## Verification note

The repository changes were applied through the GitHub API. The execution environment did not have network access to clone the repository, so the complete pytest and Docker smoke suites were not executed locally during this implementation. CI should be treated as the final verification gate before production activation.
