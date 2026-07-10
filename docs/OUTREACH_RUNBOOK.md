# Outreach Runbook

## Pre-Launch Checklist

- [ ] `OUTREACH_ENABLED=false` in production until tested
- [ ] WhatsApp/Email/Telegram config keys filled in
- [ ] Webhook endpoints configured and verified
- [ ] Admin login credentials set
- [ ] Redis running and accessible
- [ ] Workers started: `outreach-generator`, `outreach-sender`, `outreach-status`

## Creating a Campaign

1. Navigate to `/campaigns` in admin UI
2. Click "Create Campaign"
3. Fill: name, channel (whatsapp/email/telegram), language (ru/kk)
4. Campaign starts in `draft` status

## Generating Messages

1. Add qualified leads to the campaign via API
2. Trigger message generation worker
3. Messages appear as `needs_review` in campaign detail

## Reviewing Messages

1. Go to campaign detail → message list
2. For each message:
   - **Approve**: marks for sending (requires CSRF token)
   - **Edit**: modify body, then approve
   - **Reject**: removes message from send queue
3. CSRF tokens are included in admin UI pages

## Sending

1. Enable outreach: set `OUTREACH_ENABLED=true`
2. Trigger send worker or approve individually
3. Messages progress: `approved` → `queued` → `sent` → `delivered`

## Monitoring

### Key Metrics
- `/metrics` endpoint shows:
  - Messages by status
  - Reply rate
  - Conversion by stage
  - Rate limit status

### Logs
```bash
# View worker logs
docker compose logs -f outreach-sender
docker compose logs -f outreach-generator
docker compose logs -f outreach-status
```

### Audit Trail
- All approve/reject/send/cancel actions logged
- View via `/audit-log` endpoint

## Rate Limiting

- Default: 50 messages per hour
- Configurable via `OUTREACH_MAX_PER_HOUR`
- Redis-backed counter per provider
- When limit hit: messages queued, sent next hour

## Quiet Hours

- Default: 09:00–20:00 Asia/Almaty
- Configurable via `OUTREACH_QUIET_HOURS_START/END`
- Messages queued outside quiet hours, sent when window opens

## Follow-Up Management

- Automatic follow-up candidates calculated for leads with `next_follow_up_at` set
- Follow-up delays configurable via `FOLLOW_UP_DELAY_HOURS`
- Max follow-ups per lead: `FOLLOW_UP_MAX_COUNT`
- All follow-ups require manual approval

## Do Not Contact

- Leads marked DNC are never contacted
- DNC flags: `do_not_contact=true`, `do_not_contact_reason`
- Unblocked leads can be re-contacted if `OUTREACH_ENABLED` is true
- All DNC actions logged to audit trail

## Troubleshooting

### Messages not sending
1. Check `OUTREACH_ENABLED=true`
2. Check provider config keys are set
3. Check quiet hours not blocking
4. Check rate limit not exceeded
5. Check worker is running: `docker compose ps outreach-sender`

### Webhook not receiving events
1. Verify webhook URL is publicly accessible
2. Verify `WHATSAPP_VERIFY_TOKEN` matches
3. Check Meta Developer Portal webhook status
4. Check API logs for verification errors

### Duplicate messages
- System checks: same lead + same campaign + same channel = rejected
- First-contact prevention for new leads
- Follow-ups require explicit approval
