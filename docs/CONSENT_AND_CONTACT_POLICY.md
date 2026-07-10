# Consent and Contact Policy

## Overview

The Leadgen Agent enforces strict consent and contact policies before any
outbound message is sent. This document describes the consent model, contact
basis tracking, and do-not-contact (DNC) enforcement.

## Consent Statuses

| Status | Description | Can Send? |
|---|---|---|
| `unknown` | No consent recorded | No (production) |
| `legitimate_interest_reviewed` | B2B legitimate interest documented | Yes |
| `consented` | Explicit opt-in received | Yes |
| `withdrawn` | Lead revoked consent | No |
| `blocked` | Lead blocked communication | No |

## Contact Basis

Every outreach message must have a `contact_basis` value:

- `business_interest` — B2B outreach based on publicly available business info
- `consent_opt_in` — Lead explicitly opted in
- `legitimate_interest` — Documented legitimate interest under applicable law
- `referral` — Referred by a third party with consent

## Do-Not-Contact (DNC)

A lead marked as `do_not_contact = true` will never receive messages, regardless
of consent status. DNC can be set:

- Manually via the admin UI
- Via the API: `POST /leads/{lead_id}/do-not-contact`
- Automatically when `consent_status` is set to `withdrawn` or `blocked`
- When a lead replies with an opt-out request

**DNC is irreversible** in the current model — once set, it can only be cleared
by setting `consent_status` back to an approved state via the consent API.

## Production Policy (`_production_policy_allows`)

Before sending, the system checks (in order):

1. **Mode check**: `OUTREACH_MODE` must not be `disabled`
2. **Phone validation**: Recipient must be a valid Kazakhstan E.164 number
3. **Sandbox allowlist**: In sandbox mode, recipient must be in the allowlist
4. **DNC check**: Lead must not be marked `do_not_contact`
5. **Consent check**: In production mode, `consent_status` must be
   `consented` or `legitimate_interest_reviewed`

If any check fails, the message is set to `blocked` status and logged.

## Sandbox Mode

In sandbox mode, the consent and DNC checks are relaxed. Only the sandbox
allowlist is enforced. This allows testing without full consent infrastructure.

## Service Window

After a lead sends an inbound message, a service window is opened:
- Duration: `WHATSAPP_SERVICE_WINDOW_HOURS` (default: 24 hours)
- During the window: Free-form text messages are allowed
- Outside the window: Only template messages are allowed (Meta policy)

The service window is tracked via `lead.service_window_expires_at`.

## Quiet Hours

Messages are only sent during allowed hours:
- Configurable via `OUTREACH_QUIET_HOURS_START` and `OUTREACH_QUIET_HOURS_END`
- Timezone-aware via `OUTREACH_TIMEZONE`
- Checked at send time (not at approval time)

## API Endpoints

### Update Lead Consent

```http
PUT /leads/{lead_id}/consent
Content-Type: application/json

{
  "consent_status": "consented",
  "contact_basis": "business_interest",
  "consent_source": "manual_review",
  "consent_notes": "Consent recorded during phone call on 2025-01-15"
}
```

### Mark Lead as Do-Not-Contact

```http
POST /leads/{lead_id}/do-not-contact
Content-Type: application/json

{
  "reason": "Lead requested removal from contact list"
}
```

## Data Retention

- Consent records are stored on the `leads` table with timestamps
- All consent changes are logged in the audit trail
- Inbound messages are retained for the conversation history
- `do_not_contact` reason is stored for compliance records

## Compliance Notes

- Never send to a lead marked `do_not_contact`
- Never fabricate consent records
- All outbound messages start in `needs_review` status
- Admin approval is required before sending
- `OUTREACH_ENABLED` must be `true` AND `OUTREACH_MODE` must not be `disabled`
