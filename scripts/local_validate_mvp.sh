#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "$0")/.."

log() { printf '[LOCAL-VALIDATE] %s\n' "$*"; }
fail() { log "FAILED: $*"; exit 1; }

command -v python >/dev/null 2>&1 || fail "python is not installed"
command -v docker >/dev/null 2>&1 || fail "docker is not installed"
docker compose version >/dev/null 2>&1 || fail "docker compose is not available"

log "1/6 Compile Python sources"
python -m compileall app -q

log "2/6 Run stabilization tests"
python -m pytest \
  tests/test_mvp_pipeline_e2e.py \
  tests/test_mvp_retry_safety.py \
  tests/test_admin_recovery.py \
  tests/test_admin_message_approval_security.py \
  -v

log "3/6 Run full test suite"
python -m pytest tests/ -q

log "4/6 Validate Docker Compose"
docker compose config >/dev/null

log "5/6 Build default runtime"
docker compose build api worker migrate >/dev/null

log "6/6 Run strict Docker smoke flow"
CLEANUP_ON_EXIT=1 bash scripts/smoke_mvp_pipeline_strict.sh

log "ALL LOCAL MVP CHECKS PASSED"
