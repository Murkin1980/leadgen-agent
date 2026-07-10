# Production Deployment

## Prerequisites

- Python 3.12+ (Docker) or 3.13 (local)
- PostgreSQL 14+
- Redis 7+
- Cloudflare account with Pages project
- Meta Developer App with WhatsApp Cloud API access
- Alembic migrations up to date (001–006)

## Environment Variables

Copy `.env.production.example` to `.env.production` and fill in all values.

### Required for Production

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `ADMIN_PASSWORD` | Admin panel password |
| `WHATSAPP_CLOUD_API_TOKEN` | Meta Graph API token |
| `WHATSAPP_CLOUD_PHONE_NUMBER_ID` | Sending number ID |
| `WHATSAPP_APP_SECRET` | For webhook signature verification |
| `WHATSAPP_WEBHOOK_VERIFY_TOKEN` | Webhook subscription token |
| `OUTREACH_MODE` | Must be `production` for live sending |

### Optional but Recommended

| Variable | Default | Description |
|---|---|---|
| `OUTREACH_MAX_PER_HOUR` | 30 | Hourly rate limit |
| `OUTREACH_QUIET_HOURS_START` | 22:00 | Quiet hours begin |
| `OUTREACH_QUIET_HOURS_END` | 07:00 | Quiet hours end |
| `OUTREACH_SEND_MAX_RETRIES` | 3 | Max retry attempts |
| `WHATSAPP_SERVICE_WINDOW_HOURS` | 24 | Free-form window |

## Deployment Steps

### 1. Database

```bash
# Run all migrations including Phase 06
alembic upgrade head

# Verify migration 006 applied
alembic heads
```

### 2. Cloudflare Pages

```bash
# Install dependencies
pip install -r requirements.txt

# Build static assets (if any)
# Deploy via Wrangler
wrangler pages deploy . --project-name=leadgen-agent
```

### 3. API Server

```bash
# Using Docker
docker compose -f docker-compose.prod.yml up -d

# Or directly
uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers 4
```

### 4. Workers

```bash
# Start RQ workers for each queue
rq worker collect enrichment generate_content publish deploy outreach_send outreach_status --with-scheduler
```

### 5. Webhook Configuration

1. In Meta Developer Console, set webhook URL to:
   `https://your-domain.com/webhooks/whatsapp`
2. Subscribe to `messages` and `message_deliveries` fields
3. Verify the GET challenge succeeds

### 6. Verify Deployment

```bash
# Health check
curl https://your-domain.com/health

# Webhook verification
curl "https://your-domain.com/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=YOUR_TOKEN&hub.challenge=test123"

# Check outreach metrics
curl -H "Authorization: Bearer $ADMIN_TOKEN" https://your-domain.com/metrics/outreach
```

## Security Checklist

- [ ] `OUTREACH_MODE=production` (not `sandbox`)
- [ ] `WHATSAPP_ALLOW_MOCK_WEBHOOKS=false`
- [ ] `APP_ENV=production`
- [ ] All secrets in env vars, not in code
- [ ] `.env.production` in `.gitignore`
- [ ] HTTPS enforced on all endpoints
- [ ] Admin panel behind authentication
- [ ] CSRF protection enabled on all POST endpoints
- [ ] Audit logging active

## Rollback Procedure

1. Set `OUTREACH_MODE=disabled` to stop all sending
2. Cancel pending messages: `UPDATE outreach_messages SET status='cancelled' WHERE status IN ('approved','queued')`
3. Revert to previous deployment
4. No database rollback needed (migrations are additive)

## Monitoring

- Check `/metrics/outreach` endpoint periodically
- Set up alerts for `dead_letter` count > 0
- Monitor `reply_rate` for drops
- Watch for rate limit warnings in logs
