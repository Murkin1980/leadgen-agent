# Collector Runbook

## Overview
This runbook covers operations for the Leadgen Agent collector system, including troubleshooting, monitoring, and maintenance.

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   API       │────▶│  Collector  │────▶│  Enricher   │
│  (FastAPI)  │     │   Worker    │     │   Worker    │
└─────────────┘     └─────────────┘     └─────────────┘
                         │                    │
                         ▼                    ▼
                    ┌─────────────┐     ┌─────────────┐
                    │  PostgreSQL │     │   Redis     │
                    └─────────────┘     └─────────────┘
```

## Provider Selection

### Environment Variables
```bash
# Provider selection
COLLECTOR_PROVIDER=mock|csv|two_gis

# 2GIS Configuration
TWO_GIS_API_KEY=your_api_key
TWO_GIS_API_URL=https://catalog.api.2gis.com/3.0/items
TWO_GIS_CITY_ID=city_id
TWO_GIS_PAGE_SIZE=20
TWO_GIS_MAX_RETRIES=3
TWO_GIS_RETRY_DELAY=1.0

# CSV Configuration
CSV_FILE_PATH=import/companies.csv
CSV_PAGE_SIZE=20

# Qualification
LEAD_MIN_SCORE=50
```

### Provider Selection Logic
1. Check `COLLECTOR_PROVIDER` environment variable
2. If `two_gis`, verify `TWO_GIS_API_KEY` is set
3. If `csv`, verify `CSV_FILE_PATH` exists
4. Default to `mock` if provider not configured

## Monitoring

### Job Status Values
- `pending` - Job created, waiting to start
- `collecting` - Actively collecting data
- `enriching` - Processing collected leads
- `generating` - Generating landing pages
- `publishing` - Publishing to local server
- `completed` - Job finished successfully
- `failed` - Job failed (check `error_message`)
- `cancelled` - Job was cancelled by user

### Key Metrics
```sql
-- Jobs by status
SELECT status, COUNT(*) FROM search_jobs GROUP BY status;

-- Leads by provider
SELECT provider, COUNT(*) FROM leads GROUP BY provider;

-- Leads by qualification score
SELECT 
  CASE 
    WHEN qualification_score >= 70 THEN 'high'
    WHEN qualification_score >= 50 THEN 'medium'
    ELSE 'low'
  END as quality,
  COUNT(*) 
FROM leads 
GROUP BY quality;

-- Average processing time
SELECT 
  AVG(EXTRACT(EPOCH FROM (completed_at - started_at))) as avg_seconds
FROM search_jobs 
WHERE status = 'completed';
```

### Health Check
```bash
# API health
curl http://localhost:8000/health

# Redis connection
redis-cli ping

# PostgreSQL connection
psql -h localhost -U leadgen -d leadgen -c "SELECT 1"
```

## Troubleshooting

### Job Stuck in "collecting" Status
1. Check worker logs: `docker logs leadgen-collector-1`
2. Verify Redis connection: `redis-cli ping`
3. Check for rate limiting errors
4. Restart worker: `docker restart leadgen-collector-1`

### Job Failed with "2GIS API key required"
1. Verify `TWO_GIS_API_KEY` is set in `.env`
2. Check API key is valid at 2gis.com
3. Ensure API key has not expired

### CSV File Not Found
1. Verify file exists at `CSV_FILE_PATH`
2. Check file permissions
3. Ensure CSV has correct headers

### High Memory Usage
1. Check for large result sets
2. Reduce `page_size` configuration
3. Monitor worker memory: `docker stats`

### Slow Collection
1. Check network latency to 2GIS API
2. Reduce `page_size` to batch smaller
3. Check Redis queue depth: `redis-cli LLEN collect`
4. Scale workers: `docker-compose up -d --scale collector=3`

## Maintenance

### Clearing Failed Jobs
```sql
-- Reset failed jobs
UPDATE search_jobs 
SET status = 'pending', error_message = NULL 
WHERE status = 'failed';
```

### Archiving Old Jobs
```sql
-- Archive completed jobs older than 30 days
-- (Implement based on retention policy)
```

### Database Cleanup
```sql
-- Remove leads without jobs
DELETE FROM leads 
WHERE search_job_id IS NULL 
AND created_at < NOW() - INTERVAL '30 days';
```

## Deployment

### Cloudflare Pages
```bash
# Deploy manually
./scripts/deploy_cloudflare.sh

# Or via API
curl -X POST http://localhost:8000/jobs/{job_id}/deploy
```

### Docker
```bash
# Rebuild and restart
docker-compose down
docker-compose build
docker-compose up -d

# View logs
docker-compose logs -f collector
```

## Security

### API Key Rotation
1. Generate new key at 2gis.com
2. Update `TWO_GIS_API_KEY` in `.env`
3. Restart services: `docker-compose restart`
4. Verify new key works: create test job

### SSRF Protection
- Website verification blocks private IPs
- DNS resolution checked before HTTP
- Configurable via `VERIFICATION_ENABLED`

### Rate Limiting
- Exponential backoff on failures
- Configurable via `TWO_GIS_MAX_RETRIES` and `TWO_GIS_RETRY_DELAY`
- No parallel requests to same endpoint
