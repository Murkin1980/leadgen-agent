# Outreach Policy

## Core Principles

1. **No automatic sending** — Every first-contact message requires manual approval by an operator.
2. **Opt-out respect** — Leads marked `do_not_contact` are never contacted. Reply "стоп" handling is mandatory.
3. **Quiet hours** — No messages sent outside configured business hours (default 09:00–20:00 Asia/Almaty).
4. **Rate limits** — Maximum messages per hour enforced via Redis counter.
5. **No fabricated claims** — Generated messages use only verified lead data and approved landing page URLs.
6. **Duplicate prevention** — One first-contact message per lead per campaign per channel.

## Workflow

1. Create a campaign with channel and language
2. Add qualified leads to the campaign
3. Generate messages (worker populates drafts from verified data)
4. Review each message — approve, edit, or reject
5. Send approved messages through the provider
6. Track delivery events via webhooks
7. Follow-up candidates calculated automatically but require manual approval

## Supported Channels

| Channel | Provider | Status |
|---------|----------|--------|
| WhatsApp | Cloud API | Stub (config fields ready) |
| Email | SMTP | Stub (config fields ready) |
| Telegram | Bot API | Stub (config fields ready) |
| Mock | In-memory | Fully functional for testing |

## Compliance

- Messages include opt-out wording in Russian and Kazakh
- All outbound messages are logged in audit trail
- Provider secrets are never exposed in logs or API responses
- Webhook payloads are redacted before storage
