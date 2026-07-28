#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "$0")/.."

API_URL="${API_BASE_URL:-http://localhost:8000}"
PREVIEW_URL="${PREVIEW_BASE_URL:-http://localhost:8080}"
CLEANUP_ON_EXIT="${CLEANUP_ON_EXIT:-0}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-150}"

log() { printf '[MVP-DOCKER-SMOKE] %s\n' "$*"; }
fail() { log "FAILED: $*"; docker compose ps || true; docker compose logs --tail=100 api worker migrate || true; exit 1; }

cleanup() {
  if [[ "$CLEANUP_ON_EXIT" == "1" ]]; then
    log "Stopping smoke environment"
    docker compose down -v --remove-orphans >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

wait_http() {
  local url="$1"
  local label="$2"
  local elapsed=0
  until curl --fail --silent --show-error "$url" >/dev/null 2>&1; do
    sleep 2
    elapsed=$((elapsed + 2))
    if (( elapsed >= TIMEOUT_SECONDS )); then
      fail "$label did not become ready: $url"
    fi
  done
  log "$label is ready"
}

log "Validate Compose configuration"
docker compose config >/dev/null

log "Start default services only"
docker compose up -d --build postgres redis migrate api worker preview

log "Wait for migration completion"
elapsed=0
until [[ "$(docker inspect -f '{{.State.ExitCode}}' "$(docker compose ps -q migrate)" 2>/dev/null || echo 1)" == "0" ]]; do
  sleep 2
  elapsed=$((elapsed + 2))
  if (( elapsed >= TIMEOUT_SECONDS )); then
    fail "migrations did not complete successfully"
  fi
done

wait_http "$API_URL/health" "API"
# Nginx may return 403 for an empty document root, which still proves the service
# is reachable. Curl without --fail and require a non-000 response code.
preview_code="$(curl --silent --output /dev/null --write-out '%{http_code}' "$PREVIEW_URL/" || true)"
[[ "$preview_code" != "000" ]] || fail "preview service is unreachable"
log "Preview is reachable (HTTP $preview_code)"

log "Verify worker process is running"
worker_id="$(docker compose ps -q worker)"
[[ -n "$worker_id" ]] || fail "worker container was not created"
[[ "$(docker inspect -f '{{.State.Running}}' "$worker_id")" == "true" ]] || fail "worker container is not running"

log "Run worker-level MVP pipeline test inside API image"
docker compose exec -T \
  -e DATABASE_URL=sqlite:////tmp/mvp-smoke.db \
  -e TEXT_GENERATOR_PROVIDER=mock \
  -e OUTREACH_PROVIDER=mock \
  -e OUTREACH_ENABLED=false \
  api python -m pytest tests/test_mvp_pipeline_e2e.py -q

log "Run retry and admin safety tests inside API image"
docker compose exec -T \
  -e DATABASE_URL=sqlite:////tmp/mvp-smoke.db \
  api python -m pytest \
    tests/test_mvp_retry_safety.py \
    tests/test_admin_recovery.py \
    tests/test_admin_message_approval_security.py \
    -q

log "Check final container state"
for service in postgres redis api worker preview; do
  container_id="$(docker compose ps -q "$service")"
  [[ -n "$container_id" ]] || fail "$service container is missing"
  [[ "$(docker inspect -f '{{.State.Running}}' "$container_id")" == "true" ]] || fail "$service is not running"
done

log "STRICT MVP DOCKER SMOKE PASSED"
