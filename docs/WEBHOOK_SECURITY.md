# Webhook Security

## Overview

All incoming webhooks from Meta (WhatsApp Cloud API) are verified using
HMAC-SHA256 signatures. This document describes the verification mechanism
and security controls.

## How It Works

1. Meta sends webhooks with an `X-Hub-Signature-256` header containing
   `sha256={hex_digest}`.
2. The server computes `HMAC-SHA256(raw_body, APP_SECRET)` and compares
   using constant-time comparison.
3. If the signature is invalid:
   - Returns HTTP 200 with `{"processed": false, "reason": "invalid_signature"}`
     (to avoid Meta retry storms)
   - **Does not create** `InboundMessage` records
   - **Does not create** `OutreachEvent` records
   - **Does not modify** any `Lead` records
   - Increments `webhook_invalid_signature_total` metric
   - Writes audit/security log (without payload or phone number)

## Signature Verification Flow

```
Request arrives
  → Extract X-Hub-Signature-256 header
  → Compute expected = HMAC-SHA256(raw_body, APP_SECRET)
  → Compare with constant-time hmac.compare_digest
  → If APP_SECRET is empty and not production: allow (mock mode)
  → Otherwise reject with {"processed": false, "reason": "invalid_signature"}
```

## Key Implementation Details

- **Constant-time comparison**: Uses `hmac.compare_digest()` to prevent
  timing attacks.
- **Prefix handling**: Accepts signatures with or without the `sha256=` prefix
  via `str.removeprefix("sha256=")`.
- **Missing secret**: Returns 403 in production; allows in development when
  `WHATSAPP_ALLOW_MOCK_WEBHOOKS=true`.
- **Centralized verification**: Single source of truth in `app/security/webhook_signature.py`

## Meta Webhook Verification (GET)

When first subscribing, Meta sends a GET request with:
- `hub.mode=subscribe`
- `hub.verify_token={your_token}`
- `hub.challenge={random_string}`

The server responds with the challenge string if the token matches.
The verify token is set via `WHATSAPP_WEBHOOK_VERIFY_TOKEN`.

## Best Practices

1. **Always set `WHATSAPP_APP_SECRET` in production.** Without it, any
   attacker can inject fake webhook events.
2. **Never log raw webhook payloads** with secrets. The `_redact_secrets()`
   function strips sensitive headers.
3. **Keep `WHATSAPP_ALLOW_MOCK_WEBHOOKS=false` in production.** This flag
   bypasses signature verification when `APP_SECRET` is empty.
4. **Use HTTPS** for webhook endpoints (Cloudflare Pages handles this).
5. **Validate Content-Type** — Meta sends `application/json`.

## Audit Trail

All webhook events are logged as `OutreachEvent` records with:
- `provider_event_id`: Unique key (e.g., `wamid.xxx:delivered:timestamp`)
- `payload_json`: Redacted payload (secrets removed, truncated to 5000 chars)
- `event_type`: `delivered`, `read`, `failed`, `replied`, etc.

## Testing Webhooks Locally

```bash
# Generate a valid signature
SECRET="your_app_secret"
PAYLOAD='{"entry":[]}'
SIG=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print $2}')

curl -X POST http://localhost:8080/webhooks/whatsapp \
  -H "Content-Type: application/json" \
  -H "X-Hub-Signature-256: sha256=$SIG" \
  -d "$PAYLOAD"
```
