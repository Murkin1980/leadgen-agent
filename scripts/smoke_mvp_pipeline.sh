#!/bin/bash
# Reproducible local smoke script for the default MVP runtime.
#
# Required by docs/CODEX_NEXT_MVP_PIPELINE_STABILIZATION.md section 4.7.
#
# Unlike scripts/mvp_smoke_test.sh (which assumes services are already
# running and swallows most failures with `|| true`, always printing
# "PASSED" regardless of what actually happened), this script:
#   - starts the default six-service runtime itself (never the advanced
#     profile);
#   - genuinely fails (non-zero exit, clear FAIL summary) if any step
#     doesn't reach the state it's supposed to reach;
#   - runs the real pipeline through the real worker processes inside
#     the containers (not by calling worker functions in-process), so it
#     catches infra-level defects unit tests can't -- this run is what
#     caught docker-compose.yml's `python -m rq worker` command crashing
#     immediately (rq 1.16.2 has no __main__.py; fixed to `rq worker`).
#
# Usage:
#   bash scripts/smoke_mvp_pipeline.sh          # interactive: leaves services running
#   CI=1 bash scripts/smoke_mvp_pipeline.sh      # CI mode: tears down at the end regardless of outcome
#
# Requires Docker + Docker Compose v2. Does not require any Meta,
# Cloudflare, or other paid/external credentials -- everything runs
# against the mock/sandbox providers.

set -uo pipefail
cd "$(dirname "$0")/.."

API_URL="http://localhost:8000"
PREVIEW_URL="http://localhost:8080"
WAIT_TIMEOUT=120
SANDBOX_PHONE="+77000000099"
ENV_FILE=".env"
ENV_BACKUP=""
STEP_RESULTS=()
FAILED=0

log() { echo "[SMOKE] $*"; }
pass() { STEP_RESULTS+=("PASS: $1"); log "PASS: $1"; }
fail() { STEP_RESULTS+=("FAIL: $1"); log "FAIL: $1"; FAILED=1; }

cleanup() {
    if [ -n "$ENV_BACKUP" ] && [ -f "$ENV_BACKUP" ]; then
        mv "$ENV_BACKUP" "$ENV_FILE"
        log "Restored original ${ENV_FILE}"
    fi
    if [ "${CI:-0}" = "1" ]; then
        log "CI mode: shutting down docker compose"
        docker compose down -v --remove-orphans > /dev/null 2>&1 || true
    else
        log "Interactive mode: leaving services running for inspection (docker compose down to stop)"
    fi
}
trap cleanup EXIT

print_summary() {
    echo ""
    echo "=================== MVP SMOKE TEST SUMMARY ==================="
    for r in "${STEP_RESULTS[@]}"; do
        echo "  $r"
    done
    echo "================================================================"
    if [ "$FAILED" -eq 0 ]; then
        echo "RESULT: PASSED"
    else
        echo "RESULT: FAILED"
    fi
}

wait_for() {
    local name="$1" check_cmd="$2"
    local elapsed=0
    while [ $elapsed -lt $WAIT_TIMEOUT ]; do
        if eval "$check_cmd" > /dev/null 2>&1; then
            pass "$name is ready"
            return 0
        fi
        sleep 3
        elapsed=$((elapsed + 3))
    done
    fail "$name did not become ready within ${WAIT_TIMEOUT}s"
    return 1
}

json_field() {
    python3 -c "import sys, json; print(json.load(sys.stdin)$1)" 2>/dev/null
}

# ── 0. Prepare a deterministic sandbox .env ─────────────────────────
# Quiet hours are zeroed out (00:00-00:00 = never active) so this script
# gives the same result no matter what time of day it runs.
if [ -f "$ENV_FILE" ]; then
    ENV_BACKUP="$(mktemp)"
    cp "$ENV_FILE" "$ENV_BACKUP"
fi
cp .env.mvp.example "$ENV_FILE"
cat >> "$ENV_FILE" << EOF
ADMIN_PASSWORD=smoke-test-password
OUTREACH_ENABLED=true
OUTREACH_MODE=sandbox
OUTREACH_SANDBOX_ALLOWLIST=${SANDBOX_PHONE}
OUTREACH_QUIET_HOURS_START=00:00
OUTREACH_QUIET_HOURS_END=00:00
WHATSAPP_ALLOW_MOCK_WEBHOOKS=true
EOF

# ── 1. Validate Docker Compose configuration ────────────────────────
if docker compose config > /dev/null; then
    pass "docker compose config is valid"
else
    fail "docker compose config failed"
    print_summary
    exit 1
fi

# ── 2. Start the default services only (never --profile advanced) ──
log "Starting default runtime (postgres, redis, migrate, api, worker, preview)..."
if docker compose up -d --build; then
    pass "docker compose up (default profile) started"
else
    fail "docker compose up failed"
    print_summary
    exit 1
fi

# ── 3. Wait for PostgreSQL, Redis, API, worker, preview ─────────────
wait_for "PostgreSQL" 'docker compose exec -T postgres pg_isready -U leadgen -d leadgen'
wait_for "Redis" 'docker compose exec -T redis redis-cli ping | grep -q PONG'
wait_for "API" "curl -sf ${API_URL}/health"
wait_for "Preview (nginx)" "curl -sf -o /dev/null -w '%{http_code}' ${PREVIEW_URL}/ | grep -qE '^(200|403|404)$'"

# Worker has no HTTP healthcheck (it's an RQ worker, not a server) --
# verify the container is actually running rather than crash-looping,
# which is exactly the failure mode this script caught for the
# `python -m rq worker` bug (fixed in docker-compose.yml).
sleep 5
WORKER_STATE=$(docker compose ps worker --format json 2>/dev/null | python3 -c "import sys,json; print(json.loads(sys.stdin.read().splitlines()[0])['State'])" 2>/dev/null || echo "unknown")
if [ "$WORKER_STATE" = "running" ]; then
    pass "worker container is running (not crash-looping)"
else
    fail "worker container state is '${WORKER_STATE}', expected 'running'"
    log "Worker logs:"
    docker compose logs --tail=30 worker || true
fi

# ── 4. Migrations ────────────────────────────────────────────────────
MIGRATE_EXIT=$(docker compose ps migrate --format json 2>/dev/null | python3 -c "import sys,json; print(json.loads(sys.stdin.read().splitlines()[0]).get('ExitCode', 1))" 2>/dev/null || echo "1")
if [ "$MIGRATE_EXIT" = "0" ]; then
    pass "migrate service completed successfully (alembic upgrade head)"
else
    fail "migrate service exit code was '${MIGRATE_EXIT}', expected 0"
fi

# ── 5. Run one mock MVP pipeline through the real API + real workers ─
log "Triggering CSV import job..."
JOB_RESPONSE=$(curl -sf -X POST "${API_URL}/jobs" -H "Content-Type: application/json" \
    -d '{"city": "Алматы", "category": "Мебель на заказ", "limit": 10, "provider": "csv"}')
JOB_ID=$(echo "$JOB_RESPONSE" | json_field "['id']")
if [ -z "$JOB_ID" ]; then
    fail "could not create collection job"
    print_summary
    exit 1
fi
pass "collection job ${JOB_ID} created"

log "Waiting for the real worker to process the job..."
elapsed=0
LEAD_ID=""
while [ $elapsed -lt 60 ]; do
    LEADS=$(curl -sf "${API_URL}/leads?limit=5" 2>/dev/null || echo "[]")
    LEAD_ID=$(echo "$LEADS" | json_field "[0]['id']" 2>/dev/null || echo "")
    if [ -n "$LEAD_ID" ]; then
        break
    fi
    sleep 3
    elapsed=$((elapsed + 3))
done
if [ -z "$LEAD_ID" ]; then
    fail "no lead appeared after collection (worker did not process the job)"
    print_summary
    exit 1
fi
pass "worker collected/enriched lead ${LEAD_ID}"

log "Requesting content generation for lead ${LEAD_ID}..."
GEN_RESPONSE=$(curl -sf -X POST "${API_URL}/leads/${LEAD_ID}/content-generations" -H "Content-Type: application/json" -d '{}')
GEN_ID=$(echo "$GEN_RESPONSE" | json_field "['id']")

elapsed=0
LANDING_ID=""
LANDING_SLUG=""
while [ $elapsed -lt 60 ]; do
    GEN_STATUS=$(curl -sf "${API_URL}/content-generations/${GEN_ID}" 2>/dev/null | json_field "['status']" 2>/dev/null || echo "")
    if [ "$GEN_STATUS" = "succeeded" ]; then
        LANDINGS=$(curl -sf "${API_URL}/landings?lead_id=${LEAD_ID}" 2>/dev/null || echo "[]")
        LANDING_ID=$(echo "$LANDINGS" | json_field "[0]['id']" 2>/dev/null || echo "")
        LANDING_SLUG=$(echo "$LANDINGS" | json_field "[0]['slug']" 2>/dev/null || echo "")
        break
    fi
    if [ "$GEN_STATUS" = "failed" ]; then
        break
    fi
    sleep 3
    elapsed=$((elapsed + 3))
done
if [ -z "$LANDING_ID" ]; then
    fail "content generation did not produce a landing (status: ${GEN_STATUS:-unknown})"
    print_summary
    exit 1
fi
pass "worker generated landing ${LANDING_ID} (slug: ${LANDING_SLUG})"

log "Approving and publishing landing ${LANDING_ID}..."
curl -sf -X POST "${API_URL}/landings/${LANDING_ID}/approve" > /dev/null
PUBLISH_RESPONSE=$(curl -sf -X POST "${API_URL}/landings/${LANDING_ID}/publish")
PUBLISH_STATUS=$(echo "$PUBLISH_RESPONSE" | json_field "['status']")
if [ "$PUBLISH_STATUS" = "published" ]; then
    pass "landing ${LANDING_ID} published"
else
    fail "landing ${LANDING_ID} did not reach published (status: ${PUBLISH_STATUS})"
    print_summary
    exit 1
fi

# ── 6. Check the landing page is reachable in preview ───────────────
if curl -sf -o /dev/null "${PREVIEW_URL}/${LANDING_SLUG}/"; then
    pass "landing is reachable at ${PREVIEW_URL}/${LANDING_SLUG}/"
else
    fail "landing NOT reachable at ${PREVIEW_URL}/${LANDING_SLUG}/"
fi

# ── 7. Check the mock message reaches sent ──────────────────────────
log "Creating outreach campaign and message..."
CAMPAIGN_RESPONSE=$(curl -sf -X POST "${API_URL}/campaigns" -H "Content-Type: application/json" \
    -d '{"name": "Smoke Test", "channel": "whatsapp", "language": "ru"}')
CAMPAIGN_ID=$(echo "$CAMPAIGN_RESPONSE" | json_field "['id']")
curl -sf -X POST "${API_URL}/campaigns/${CAMPAIGN_ID}/add-leads" -H "Content-Type: application/json" \
    -d "{\"lead_ids\": [${LEAD_ID}]}" > /dev/null
curl -sf -X POST "${API_URL}/campaigns/${CAMPAIGN_ID}/generate-messages" -H "Content-Type: application/json" -d '{}' > /dev/null

elapsed=0
MSG_ID=""
while [ $elapsed -lt 30 ]; do
    MESSAGES=$(curl -sf "${API_URL}/outreach-messages?lead_id=${LEAD_ID}" 2>/dev/null || echo "[]")
    MSG_ID=$(echo "$MESSAGES" | json_field "[0]['id']" 2>/dev/null || echo "")
    MSG_STATUS=$(echo "$MESSAGES" | json_field "[0]['status']" 2>/dev/null || echo "")
    if [ "$MSG_STATUS" = "needs_review" ]; then
        break
    fi
    sleep 3
    elapsed=$((elapsed + 3))
done
if [ -z "$MSG_ID" ]; then
    fail "no outreach message was generated"
    print_summary
    exit 1
fi

curl -sf -X POST "${API_URL}/outreach-messages/${MSG_ID}/approve" > /dev/null
curl -sf -X POST "${API_URL}/outreach-messages/${MSG_ID}/send" > /dev/null

elapsed=0
MSG_FINAL_STATUS=""
while [ $elapsed -lt 30 ]; do
    MSG_FINAL_STATUS=$(curl -sf "${API_URL}/outreach-messages/${MSG_ID}" 2>/dev/null | json_field "['status']" 2>/dev/null || echo "")
    if [ "$MSG_FINAL_STATUS" = "sent" ]; then
        break
    fi
    sleep 3
    elapsed=$((elapsed + 3))
done
if [ "$MSG_FINAL_STATUS" = "sent" ]; then
    pass "message ${MSG_ID} reached 'sent' via the real worker + mock provider"
else
    fail "message ${MSG_ID} did not reach 'sent' (status: ${MSG_FINAL_STATUS})"
fi

# ── 8. Process one mock inbound webhook ─────────────────────────────
log "Sending a mock inbound WhatsApp webhook..."
WEBHOOK_PAYLOAD=$(cat << EOF
{"entry": [{"changes": [{"value": {"messages": [{"id": "wamid.smoke_$(date +%s)", "from": "${SANDBOX_PHONE#+}", "type": "text", "text": {"body": "Да, интересно"}}]}}]}]}
EOF
)
WEBHOOK_RESPONSE=$(curl -sf -X POST "${API_URL}/webhooks/whatsapp" -H "Content-Type: application/json" -d "$WEBHOOK_PAYLOAD")
CHANGED=$(echo "$WEBHOOK_RESPONSE" | json_field "['changed']")
if [ "$CHANGED" = "1" ]; then
    pass "webhook processed, lead stage updated"
else
    fail "webhook did not report changed=1 (response: ${WEBHOOK_RESPONSE})"
fi

LEAD_STAGE=$(curl -sf "${API_URL}/leads/${LEAD_ID}" 2>/dev/null | json_field "['stage']" 2>/dev/null || echo "")
if [ "$LEAD_STAGE" = "replied" ]; then
    pass "lead ${LEAD_ID} stage is 'replied'"
else
    fail "lead ${LEAD_ID} stage is '${LEAD_STAGE}', expected 'replied'"
fi

# ── 9. Summary ───────────────────────────────────────────────────────
print_summary

# ── 10. Clean shutdown handled by the trap above ────────────────────
exit $FAILED
