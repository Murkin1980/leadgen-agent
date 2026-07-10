# WhatsApp Cloud API Setup

## Prerequisites

1. Meta Business account
2. WhatsApp Business account
3. Phone number registered with WhatsApp

## Configuration

Set environment variables in `.env`:

```bash
OUTREACH_PROVIDER=whatsapp
OUTREACH_ENABLED=false  # Set to true only after testing

WHATSAPP_API_VERSION=v18.0
WHATSAPP_PHONE_NUMBER_ID=<your-phone-number-id>
WHATSAPP_ACCESS_TOKEN=<your-permanent-access-token>
WHATSAPP_BUSINESS_ACCOUNT_ID=<your-waba-id>
WHATSAPP_VERIFY_TOKEN=<choose-a-secret-token>
```

## Webhook Setup

1. Go to Meta Developer Portal → App → WhatsApp → Configuration
2. Set webhook URL: `https://your-domain/webhooks/whatsapp`
3. Set verify token: same as `WHATSAPP_VERIFY_TOKEN`
4. Subscribe to: `messages`, `message_status`

## Webhook Verification

Meta sends a GET request with `hub.mode`, `hub.verify_token`, `hub.challenge`. The API verifies the token and echoes the challenge.

## Delivery Events

The webhook receives JSON with:
- `messages[].id` — Provider message ID (e.g., `wamid.xxx`)
- `messages[].from` — Sender phone number
- `statuses[].id` — Provider message ID matching the sent message
- `statuses[].status` — One of: `sent`, `delivered`, `read`, `played`
- `statuses[].errors` — Error details if failed

## Error Handling

- Failed deliveries update the message status to `failed`
- Failed events are logged to `outreach_events`
- Retry logic is handled by the `outreach_status_worker`

## Security

- `WHATSAPP_VERIFY_TOKEN` must match in app config and `.env`
- Webhook signature verification (X-Hub-Signature-256) is checked
- All webhook payloads are logged with secrets redacted
