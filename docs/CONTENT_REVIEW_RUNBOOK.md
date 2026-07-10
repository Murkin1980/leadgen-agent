# Content Review Runbook

## Overview

This runbook covers the workflow for reviewing, approving, and publishing AI-generated landing page content.

## Workflow

```
ContentGeneration (queued → running → succeeded/failed/rejected)
    → LandingPage (needs_review)
        → Manual Review
            → Approved → can be published
            → Rejected → cannot be published
        → Publish → rendered and deployed
```

## Review Steps

### 1. Check Generation Status

```bash
# Via API
curl http://localhost:8000/content-generations?status=succeeded

# Via Admin UI
open http://localhost:8000/admin/landings
```

### 2. Review Landing Content

Navigate to the admin review page:
```
http://localhost:8000/admin/landings/{landing_id}
```

Review the following:
- Lead facts (name, city, phone, score)
- Generated profile (hero, services, advantages, contacts)
- Validation results (errors, warnings)
- Version history

### 3. Approve or Reject

**Approve:**
```bash
curl -X POST http://localhost:8000/landings/{landing_id}/approve \
  -H "Content-Type: application/json" \
  -d '{"approved_by": "admin"}'
```

**Reject:**
```bash
curl -X POST http://localhost:8000/landings/{landing_id}/reject \
  -H "Content-Type: application/json" \
  -d '{"reason": "Слишком общие преимущества"}'
```

### 4. Manual Edit (if needed)

```bash
curl -X PUT http://localhost:8000/landings/{landing_id}/profile \
  -H "Content-Type: application/json" \
  -d '{"meta": {...}, "company": {...}, ...}'
```

Manual edits create a new version and set status to `needs_review`.

### 5. Restore Previous Version

```bash
# List versions
curl http://localhost:8000/landings/{landing_id}/versions

# Restore specific version
curl -X POST http://localhost:8000/landings/{landing_id}/versions/{version_number}/restore
```

### 6. Publish

Only approved landings can be published:
```bash
curl -X POST http://localhost:8000/landings/{landing_id}/publish
```

## Regeneration

To regenerate content for a lead:
```bash
curl -X POST http://localhost:8000/leads/{lead_id}/content-generations \
  -H "Content-Type: application/json" \
  -d '{"language": "ru", "provider": "template", "notes": "Акцентировать кухни"}'
```

## Troubleshooting

### Generation stuck in "queued"
- Check that the `content-generator` worker is running
- Check Redis connection
- Check worker logs: `docker logs leadgen-agent-content-generator-1`

### Generation failed
- Check `error_message` in the ContentGeneration record
- Common errors:
  - OpenAI API key invalid
  - Rate limit exceeded
  - Timeout
  - Invalid model response (non-JSON)

### Validation rejected
- Check `validation_errors_json` in the ContentGeneration record
- Common issues:
  - Phone mismatch between lead and generated content
  - City mismatch
  - HTML tags in text fields
  - Unsupported claims (verified=false)

### Publishing blocked
- Ensure `review_status` is "approved"
- Check that the slug is valid
- Check that the draft directory exists

## Monitoring

### Check usage
```bash
curl http://localhost:8000/usage/openai
```

### Check active generations
```bash
curl "http://localhost:8000/content-generations?status=running"
```

### Check rejected generations
```bash
curl "http://localhost:8000/content-generations?status=rejected"
```
