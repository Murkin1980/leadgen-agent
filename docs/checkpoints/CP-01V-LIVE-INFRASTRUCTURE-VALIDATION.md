# CP-01V — Live Infrastructure Validation

**Recorded:** 2026-09-28

**Starting commit:** `e773137eb0e9319b3048a9a2a644fb0cd7a3a22a` (`arena/01a0e448-leadgen-agent`)

**Decision:** EXTEND_EXISTING

**RESULT:** **BLOCKED** — this environment cannot provide Docker/Compose, PostgreSQL, or Redis. No local installation or product-code workaround was made.

## ENVIRONMENT

- Repository was clean at the stated starting commit. The CP-01 checkpoint plan was read read-only from PR #3 head `9ec4692a9a79e9a4c9e18fa84b1d1e54bc46cc06`; required repository documents and `docs/checkpoints/CP-01G-VALIDATION-GATE-ALIGNMENT.md` were reviewed.
- Runtime: Python **3.11.2**. A temporary validation-only venv under `/tmp/leadgen-cp01v-venv` was created from the existing `requirements.txt` with pytest/pytest-cov, Ruff 0.16.9, pip-audit, Bandit, and detect-secrets. No project requirements or infrastructure were changed.
- Docker, PostgreSQL, and Redis version commands are unavailable because their CLIs/servers are not installed. The Compose file declares `postgres:16-alpine` and `redis:7-alpine`; those image versions were not started or verified.
- `docker`, `psql`, `postgres`, `pg_isready`, `redis-server`, and `redis-cli` are absent. `/var/run/docker.sock` is absent. Loopback TCP checks returned `connect_ex=111` (connection refused) for ports 5432, 6379, 8000, and 8080. `DOCKER_HOST`, `DOCKER_CONTEXT`, `DATABASE_URL`, `POSTGRES_URL`, and `REDIS_URL` are unset.

## DOCKER

- `docker --version`: **unavailable** — Docker CLI not installed.
- `docker compose version`: **unavailable** — Docker CLI not installed.
- `docker compose config`: exit **127**, `/bin/bash: docker: command not found`.
- Repository default Compose services are `postgres`, `redis`, `migrate`, `api`, `worker`, and `preview`. The documented MVP path is `cp .env.mvp.example .env` followed by `docker compose up --build`; the strict smoke's explicit startup command is `docker compose up -d --build postgres redis migrate api worker preview`.
- Neither startup command could be run. No containers were started, no service was replaced by a mock, and no inter-service health/connectivity claim is made.

## POSTGRES

- PostgreSQL server/client versions: **unavailable**; neither server nor client tools are installed. Port 5432 is closed.
- A real-dialect `alembic upgrade head` attempt targeting `127.0.0.1:5432` exited **1** at connection setup with `psycopg.OperationalError: connection failed ... Connection refused` and “Is the server running on that host and accepting TCP/IP connections?”. No PostgreSQL migration was applied.
- `tests/conftest.py` uses `os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")` and then sets `TEST_DATABASE_URL = os.environ["DATABASE_URL"]`; an explicitly supplied PostgreSQL URL is therefore preserved rather than silently replaced with SQLite. A targeted probe of `test_real_worker_mvp_pipeline` with an explicit PostgreSQL URL failed during the database fixture with connection refused: **0 passed, 1 setup error, 0 skipped, 13 warnings, 2.24s**. This is an environment failure, not a PostgreSQL test pass.
- The full PostgreSQL-backed test suite was **not run** because no server was available. Its test count/failure/skipped totals are therefore not applicable; the single probe above is recorded only to demonstrate the actual connection failure and absence of SQLite fallback.

## MIGRATIONS

- Live PostgreSQL migration chain `base → head`, live schema/table/constraint/index inspection, and PostgreSQL downgrade/re-upgrade: **NOT RUN / EXTERNAL_BLOCKED**. There is no live PostgreSQL database to inspect. `alembic heads` reports the repository's single configured head `007`, but that is not evidence of a PostgreSQL migration result or live database revision.
- SQLite regression checks were rerun separately and are **not substituted** for PostgreSQL:
  - `PATH="/tmp/leadgen-cp01v-venv/bin:$PATH" python scripts/check_migrations.py` — **PASS**; one head `007`, 14 tables, schema/constraint checks, base-to-head, downgrade/re-upgrade, and revision-001 existing-data upgrade. The script reports three SQLite index-presence warnings for manual review.
  - `PATH="/tmp/leadgen-cp01v-venv/bin:$PATH" bash scripts/check_migrations.sh` — **PASS**; full SQLite upgrade/downgrade/re-upgrade checks and 14 tables. It reports SQLite index-presence warnings as nonfatal.

## REDIS

- `redis-server --version` and `redis-cli --version`: **unavailable**; binaries are not installed. Port 6379 is closed.
- No Redis service was started and no `PING`/RQ connectivity was verified. The Redis service declared in Compose could not be exercised because Docker is unavailable. Test-time queue mocks/in-process execution from CP-01G are not live Redis evidence.

## LOCAL_VALIDATION

Command:

```bash
PATH="/tmp/leadgen-cp01v-venv/bin:$PATH" bash scripts/local_validate_mvp.sh
```

Result: exit **1** at the script's preflight: `[LOCAL-VALIDATE] FAILED: docker is not installed`. It stopped before its internal test, Compose, build, and smoke steps. The full suite and other available validations were run separately below; this failure is not represented as a pass.

## DOCKER_SMOKE

Command:

```bash
CLEANUP_ON_EXIT=1 PATH="/tmp/leadgen-cp01v-venv/bin:$PATH" bash scripts/smoke_mvp_pipeline_strict.sh
```

Result: exit **127** at `docker compose config`: `scripts/smoke_mvp_pipeline_strict.sh: line 37: docker: command not found`. The cleanup trap ran; no containers, migration service, API, worker, preview, or smoke assertion ran. Expected health checks and inter-service connections remain unverified.

## CONTAINERIZED_MVP_E2E

**NOT RUN / EXTERNAL_BLOCKED.** Without Docker, PostgreSQL, and Redis there is no real containerized stack on which to execute lead → generation → landing approval → publish → message approval → send → inbound webhook → replied. No real WhatsApp message was sent. The CP-01G SQLite/in-process E2E and the focused tests rerun here are ordinary regression evidence only; they do not satisfy this containerized requirement.

## REGRESSION

Available local validations on the unchanged CP-01G code state:

| Check | Result |
|---|---|
| Full suite with `.coveragerc` and unchanged `--cov-fail-under=80` | **PASS** — 291 passed, 22 warnings; 2,842/3,463 statements, **82.07%** (11.55s). |
| Focused CSV/default-worker, canonical E2E, and send-handoff tests | **PASS** — 8 passed, 16 warnings (5.94s). |
| Focused admin approval/recovery/webhook security tests | **PASS** — 70 passed, 19 warnings (5.62s). |
| Ruff/format changed-line gate | **PASS** — 14 changed app/tests Python files against branch-start `08e74c119c3e3a46c2e5dda3fa77b7b38fb34aa1` and `origin/master`. |
| Historical whole-tree Ruff/format report | Visible, non-blocking debt: **323 Ruff findings across 69 files**; **68 files would be reformatted, 59 already formatted**. |
| `pip check` / `pip-audit -r requirements.txt` | **PASS** — no broken requirements; no known vulnerabilities. |
| Bandit | **0 HIGH, 0 MEDIUM, 10 LOW**; blocking HIGH-only gate exits 0. Full report exits 1 for the documented LOW findings. |
| Repository secret scan | **PASS** — 21 previously reviewed example/test candidates across 15 files; blocking baseline hook scanned 205 files with 0 unbaselined candidates. No values are reproduced. |
| SQLite migration scripts / `alembic heads` | **PASS** as separately labeled SQLite checks; one configured head `007`. |
| `python -m compileall app -q` | **PASS**. |
| Live PostgreSQL migration / PostgreSQL suite | **EXTERNAL_BLOCKED** — loopback refused connection; one targeted setup probe errored as recorded above; full PG suite not run. |
| Docker Compose startup / local validator / strict smoke | **EXTERNAL_BLOCKED** — CLI absent; exact exits recorded above. |
| Containerized MVP E2E | **NOT RUN** — required real stack unavailable. |

There were no application, schema, dependency, workflow, or validation-gate changes in CP-01V. CP-01G's coverage scope and gates remain unchanged and green where runnable.

## FIXES

**None.** The failures are caused by unavailable external infrastructure, not an observed repository defect. No product code or test was changed to work around the environment. The only planned repository change for CP-01V is this evidence file. The CP-01 stabilization result document was not changed because the CP-01V PASS rule was not met.

## BLOCKERS

1. **Docker/Compose unavailable:** no CLI or Docker socket; Compose cannot start the default stack. This blocks container health/connectivity, `local_validate_mvp.sh`, strict Docker smoke, and containerized MVP E2E.
2. **PostgreSQL unavailable:** no server/client binaries and loopback 5432 refused connections. This blocks live migration/schema verification and the PostgreSQL-backed suite.
3. **Redis unavailable:** no server/client binaries and loopback 6379 refused connections; live Redis/RQ connectivity is unverified.

**CP-01V RESULT: BLOCKED. CP-01 FINAL STATUS: BLOCKED.** CP-01 remains open only for the live infrastructure validations above. No PR was merged, and CP-02 was not started.
