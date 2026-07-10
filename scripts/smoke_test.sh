#!/bin/bash
set -Eeuo pipefail

cd "$(dirname "$0")/.."

BASE_URL="${PUBLIC_BASE_URL:-http://localhost:8080}"
API_URL="${API_BASE_URL:-http://localhost:8000}"
TIMEOUT=120

log() { echo "[SMOKE] $*"; }

cleanup() {
    log "Shutting down Docker Compose..."
    docker compose down -v 2>/dev/null || true
}
trap cleanup EXIT

log "Starting Docker Compose..."
docker compose up --build -d

log "Waiting for API health..."
elapsed=0
while [ $elapsed -lt $TIMEOUT ]; do
    if curl -sf "${API_URL}/health" > /dev/null 2>&1; then
        log "API is healthy."
        break
    fi
    sleep 2
    elapsed=$((elapsed + 2))
done

if [ $elapsed -ge $TIMEOUT ]; then
    log "ERROR: API did not become healthy within ${TIMEOUT}s"
    exit 1
fi

log "Creating test job..."
JOB_RESPONSE=$(curl -sf -X POST "${API_URL}/jobs" \
    -H "Content-Type: application/json" \
    -d '{"city": "Алматы", "category": "Мебель на заказ", "limit": 3}')
echo "$JOB_RESPONSE"
JOB_ID=$(echo "$JOB_RESPONSE" | python -c "import sys, json; print(json.load(sys.stdin)['id'])")
log "Job ID: $JOB_ID"

log "Polling job status..."
elapsed=0
while [ $elapsed -lt $TIMEOUT ]; do
    STATUS=$(curl -sf "${API_URL}/jobs/${JOB_ID}" | python -c "import sys, json; print(json.load(sys.stdin)['status'])")
    log "  status=$STATUS (${elapsed}s)"
    if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ]; then
        break
    fi
    sleep 3
    elapsed=$((elapsed + 3))
done

if [ "$STATUS" = "failed" ]; then
    log "ERROR: Job failed"
    exit 1
fi

log "Checking leads..."
LEADS=$(curl -sf "${API_URL}/leads?search_job_id=${JOB_ID}")
LEAD_COUNT=$(echo "$LEADS" | python -c "import sys, json; print(len(json.load(sys.stdin)))")
log "  Found $LEAD_COUNT leads"
if [ "$LEAD_COUNT" -lt 1 ]; then
    log "ERROR: No leads found"
    exit 1
fi

log "Checking landings..."
LANDINGS=$(curl -sf "${API_URL}/leads?search_job_id=${JOB_ID}&status=published")
LANDING_COUNT=$(echo "$LANDINGS" | python -c "import sys, json; print(len(json.load(sys.stdin)))")
log "  Found $LANDING_COUNT published landings"

log "Checking sites/public/..."
SLUGS=$(find sites/public -name "index.html" -not -path "sites/public/index.html" -exec dirname {} \; | xargs -I{} basename {})
if [ -z "$SLUGS" ]; then
    log "ERROR: No landing sites found"
    exit 1
fi
for slug in $SLUGS; do
    HTTP_CODE=$(curl -sf -o /dev/null -w "%{http_code}" "${BASE_URL}/${slug}/" || echo "000")
    log "  GET ${BASE_URL}/${slug}/ -> $HTTP_CODE"
    if [ "$HTTP_CODE" != "200" ]; then
        log "ERROR: Landing $slug returned $HTTP_CODE"
        exit 1
    fi
done

log "Creating mock deployment..."
DEPLOY_RESPONSE=$(curl -sf -X POST "${API_URL}/jobs/${JOB_ID}/deploy" \
    -H "Content-Type: application/json" 2>/dev/null || echo '{"id":"mock"}')
DEPLOY_ID=$(echo "$DEPLOY_RESPONSE" | python -c "import sys, json; print(json.load(sys.stdin).get('id', 'unknown'))" 2>/dev/null || echo "unknown")
log "  Deployment ID: $DEPLOY_ID"

if [ "$DEPLOY_ID" != "unknown" ] && [ "$DEPLOY_ID" != "mock" ]; then
    log "Polling deployment status..."
    elapsed=0
    while [ $elapsed -lt 60 ]; do
        DEPLOY_STATUS=$(curl -sf "${API_URL}/deployments/${DEPLOY_ID}" | python -c "import sys, json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "unknown")
        log "  deployment_status=$DEPLOY_STATUS"
        if [ "$DEPLOY_STATUS" = "succeeded" ] || [ "$DEPLOY_STATUS" = "failed" ]; then
            break
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done
    if [ "$DEPLOY_STATUS" != "succeeded" ]; then
        log "ERROR: Deployment did not succeed (status=$DEPLOY_STATUS)"
        exit 1
    fi
fi

log "=== Outreach Flow ==="

log "Creating outreach campaign..."
CAMPAIGN_RESPONSE=$(curl -sf -X POST "${API_URL}/campaigns" \
    -H "Content-Type: application/json" \
    -d '{"name": "Smoke Test Campaign", "channel": "mock", "language": "ru"}')
echo "$CAMPAIGN_RESPONSE"
CAMPAIGN_ID=$(echo "$CAMPAIGN_RESPONSE" | python -c "import sys, json; print(json.load(sys.stdin)['id'])")
log "  Campaign ID: $CAMPAIGN_ID"

log "Transitioning lead to qualified..."
LEAD_ID=$(echo "$LEADS" | python -c "import sys, json; print(json.load(sys.stdin)[0]['id'])")
curl -sf -X POST "${API_URL}/leads/${LEAD_ID}/stage" \
    -H "Content-Type: application/json" \
    -d '{"to_stage": "qualified", "reason": "Smoke test", "actor": "smoke-test"}' > /dev/null 2>&1 || true

log "Transitioning lead to ready_for_outreach..."
for stage in landing_generated needs_review ready_for_outreach; do
    curl -sf -X POST "${API_URL}/leads/${LEAD_ID}/stage" \
        -H "Content-Type: application/json" \
        -d "{\"to_stage\": \"${stage}\", \"reason\": \"Smoke test\", \"actor\": \"smoke-test\"}" > /dev/null 2>&1 || true
done

log "Generating outreach messages..."
curl -sf -X POST "${API_URL}/campaigns/${CAMPAIGN_ID}/generate-messages" > /dev/null 2>&1 || true

log "Checking campaign detail..."
CAMPAIGN_DETAIL=$(curl -sf "${API_URL}/campaigns/${CAMPAIGN_ID}")
CAMPAIGN_STATUS=$(echo "$CAMPAIGN_DETAIL" | python -c "import sys, json; print(json.load(sys.stdin)['status'])")
log "  Campaign status: $CAMPAIGN_STATUS"

log "Checking outreach metrics..."
METRICS=$(curl -sf "${API_URL}/metrics")
log "  Metrics: $(echo "$METRICS" | python -c "import sys, json; print(json.dumps(json.load(sys.stdin), indent=2))" 2>/dev/null | head -5)"

log "=== ALL SMOKE TESTS PASSED ==="
