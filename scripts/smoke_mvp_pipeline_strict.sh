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
migrate_id="$(docker compose ps -aq migrate)"
[[ -n "$migrate_id" ]] || fail "migrate container was not created"
until [[ "$(docker inspect -f '{{.State.Status}}' "$migrate_id" 2>/dev/null || echo missing)" == "exited" ]]; do
  sleep 2
  elapsed=$((elapsed + 2))
  if (( elapsed >= TIMEOUT_SECONDS )); then
    fail "migrations did not finish"
  fi
done
[[ "$(docker inspect -f '{{.State.ExitCode}}' "$migrate_id")" == "0" ]] || fail "migrations exited with an error"
log "Migrations completed"

wait_http "$API_URL/health" "API"

preview_code="$(curl --silent --output /dev/null --write-out '%{http_code}' "$PREVIEW_URL/" || true)"
[[ "$preview_code" != "000" ]] || fail "preview service is unreachable"
log "Preview is reachable (HTTP $preview_code)"

log "Check default service state"
for service in postgres redis api worker preview; do
  container_id="$(docker compose ps -q "$service")"
  [[ -n "$container_id" ]] || fail "$service container is missing"
  [[ "$(docker inspect -f '{{.State.Running}}' "$container_id")" == "true" ]] || fail "$service is not running"
done

log "Confirm API can import the secured admin and recovery routes"
docker compose exec -T api python -c \
  'from app.main import app; paths={r.path for r in app.routes}; required={"/health","/admin/messages","/admin/recovery"}; missing=required-paths; assert not missing, missing; print("routes-ok")'

log "Confirm worker imports all default queue handlers"
docker compose exec -T worker python -c \
  'from app.workers.content_generator_worker import run_content_generator; from app.workers.publisher_worker import run_publisher; from app.workers.outreach_sender_worker import run_outreach_sender; print("workers-ok")'

log "STRICT MVP DOCKER SMOKE PASSED"
