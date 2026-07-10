# Outreach Incident Runbook

## Overview

This runbook covers common incidents with the outreach subsystem and how to
resolve them.

## Severity Levels

| Level | Description | Response Time |
|---|---|---|
| P1 | All messages failing, service down | Immediate |
| P2 | High failure rate (>30%), messages stuck | Within 1 hour |
| P3 | Individual message failures, retry queues growing | Within 4 hours |
| P4 | Minor issues, cosmetic errors | Next business day |

## Common Incidents

### 1. All Messages Blocked

**Symptoms**: All new messages immediately move to `blocked` status.

**Check**:
```sql
SELECT status, COUNT(*) FROM outreach_messages
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY status;
```

**Causes**:
- `OUTREACH_MODE=disabled` — Set to `sandbox` or `production`
- `OUTREACH_ENABLED=false` — Set to `true`
- All recipients not in sandbox allowlist — Add recipients
- Quiet hours active — Wait or adjust `OUTREACH_QUIET_HOURS_*`

**Fix**:
```bash
# Check current mode
curl -H "Authorization: Bearer $ADMIN_TOKEN" http://localhost:8080/providers
```

### 2. High Failure Rate from Meta API

**Symptoms**: Messages move to `failed` or `retrying` with API errors.

**Check**:
```sql
SELECT error_message, COUNT(*) FROM outreach_messages
WHERE status IN ('failed', 'retrying')
AND created_at > NOW() - INTERVAL '1 hour'
GROUP BY error_message ORDER BY COUNT(*) DESC;
```

**Common Causes**:

| Error | Meaning | Fix |
|---|---|---|
| `auth_error` (401) | Invalid API token | Rotate `WHATSAPP_CLOUD_API_TOKEN` |
| `invalid_number` (131026) | Phone not on WhatsApp | Verify recipient number |
| `template_not_approved` (131047) | Template not approved | Submit template for review |
| `rate_limit` (429) | Too many requests | Reduce `OUTREACH_MAX_PER_HOUR` |
| `service_unavailable` (5xx) | Meta backend issue | Wait, auto-retry handles this |

### 3. Messages Stuck in Retrying

**Symptoms**: Messages with `status = 'retrying'` past their `next_retry_at`.

**Check**:
```sql
SELECT id, attempt_count, next_retry_at, error_message
FROM outreach_messages
WHERE status = 'retrying'
AND next_retry_at < NOW();
```

**Fix**:
```sql
-- Reset for manual retry
UPDATE outreach_messages
SET status = 'approved', next_retry_at = NULL, error_message = NULL
WHERE status = 'retrying' AND next_retry_at < NOW();
```

### 4. Dead-Letter Queue Growing

**Symptoms**: Messages in `dead_letter` status accumulating.

**Check**:
```sql
SELECT id, lead_id, attempt_count, error_message
FROM outreach_messages WHERE status = 'dead_letter';
```

**Fix**:
1. Investigate root cause from `error_message`
2. Fix the underlying issue (token, template, etc.)
3. Reset message status to `approved` and re-queue

### 5. Webhook Signature Verification Failing

**Symptoms**: Inbound webhooks logged as `{"processed": false, "reason": "invalid_signature"}`.

**Check**:
```bash
# Verify secret matches Meta config
echo $WHATSAPP_APP_SECRET | wc -c  # Should be > 1
```

**Fix**:
1. Verify `WHATSAPP_APP_SECRET` matches the value in Meta Developer Console
2. Check for whitespace or encoding issues
3. Verify webhook URL in Meta console matches your deployment

### 6. Service Window Violations

**Symptoms**: Free-form messages fail with `service_window_closed`.

**Check**:
```sql
SELECT lead_id, last_inbound_at, service_window_expires_at
FROM leads WHERE service_window_expires_at IS NOT NULL
AND service_window_expires_at < NOW();
```

**Fix**: This is expected behavior. After 24h (or configured window),
only template messages can be sent. Use templates for follow-ups.

## Emergency Procedures

### Pause All Outreach

```bash
curl -X POST http://localhost:8080/campaigns/{campaign_id}/pause \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

### Disable Outreach Entirely

```bash
# Set environment variable
OUTREACH_MODE=disabled
```

### Cancel All Pending Messages

```sql
UPDATE outreach_messages
SET status = 'cancelled', error_message = 'Emergency cancellation'
WHERE status IN ('approved', 'queued', 'retrying');
```

## Post-Incident Checklist

1. [ ] Root cause identified
2. [ ] Fix deployed
3. [ ] All dead-letter messages investigated
4. [ ] Rate limits verified
5. [ ] Webhook processing confirmed working
6. [ ] Metrics returning to normal
7. [ ] Incident documented
