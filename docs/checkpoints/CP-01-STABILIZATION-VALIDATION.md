# CP-01 — Stabilization validation

Recorded: 2026-09-28

**RESULT: BLOCKED**

## Baseline SHAs

- **Current `master`:** `08e74c119c3e3a46c2e5dda3fa77b7b38fb34aa1` (confirmed from `origin/master`; also the merge base of the tested branch).
- **PR #2 head:** `b30448eac4e5dd6844fa245a75f1db12abd88b0f` (still open and draft; not modified or merged on GitHub).
- **Tested CP-01 working SHA:** `022b5212a5e7bcf655880cfb5e0ed9271a03fd98` on `arena/01a0e448-leadgen-agent`.
- Immediately before the CP-01 push, the remote arena branch was `4fa5f8771bed0be5503af897c2bc89f9c6727e74`; it is an ancestor of the tested commit. The tested branch includes current master and was not force-pushed.
- The evidence-file commit follows the tested code SHA; no source or test changes were made after `022b521` was tested.

## Outcome summary

| Validation category | Result | Summary |
|---|---|---|
| Complete Python suite on SQLite | **PASS** | 287 passed, 21 warnings, 2.33s on tested SHA. |
| CI coverage gate | **FAIL** | Same 287 tests pass, but measured coverage is 59.82%, below the required 80%; exit 1. |
| Repository-wide Ruff / format gates | **FAIL** | 328 Ruff findings and 69 unformatted files remain. Comparison with current master shows 0 new findings; the touched files pass. |
| SQLite migration chain | **FAIL** | Both migration-check scripts stop at revision 002 because SQLite cannot apply the added constraint with the current migration operation. |
| PostgreSQL migration/integration tests | **BLOCKED** | No PostgreSQL service is available locally; connection to `127.0.0.1:5432` is refused. SQLite was not used as a substitute. |
| Security | **FAIL** | `pip-audit` reports 14 rows (7 distinct CVEs) for transitive Starlette 0.41.3. No dependency upgrades were made. |
| `scripts/local_validate_mvp.sh` | **BLOCKED** | Stops at its Docker preflight: Docker is not installed. |
| Strict Docker smoke | **BLOCKED** | Docker CLI is not installed; smoke exits before Compose can start. |
| Canonical automated MVP path | **PASS** | Worker-level E2E completes through actual landing and message approval routes, publish, send, inbound webhook, and replied stage; duplicate webhook is idempotent. |

**Overall remains BLOCKED:** required coverage, repository-wide lint/format, SQLite migration-chain, security, PostgreSQL, and Docker criteria are not all passing/proven. No criterion is represented as PASS solely by inference.

## Validation evidence

The local validation environment was Python 3.11.2, pytest 9.1.1, Ruff 0.16.9. The repository CI workflow uses Python 3.12. Commands below include the temporary validation virtual environments used in this run.

### 1. Complete Python suite and coverage gate

**Suite command:**

```bash
DATABASE_URL='sqlite:////tmp/leadgen-cp01-tested-sha.db' \
  /tmp/leadgen-cp01-venv/bin/python -m pytest tests/ -q -ra
```

**PASS** — `287 passed, 21 warnings in 2.33s`, exit 0, tested SHA `022b5212a5e7bcf655880cfb5e0ed9271a03fd98`.

**CI coverage command:**

```bash
DATABASE_URL='sqlite:////tmp/leadgen-cp01-tested-sha-coverage.db' \
  /tmp/leadgen-cp01-venv/bin/python -m pytest tests/ -v \
  --cov=app --cov-report=xml --cov-fail-under=80 --cov-config=.coveragerc
```

**FAIL** — all 287 tests passed, but coverage was **59.82%** against the required **80%**; pytest-cov exited 1 after 4.21s. The missing coverage threshold was not weakened. The 21 warnings were primarily Pydantic/Starlette deprecations and SQLite foreign-key-cycle warnings during teardown.

### 2. Required lint and static checks

**Repository-wide Ruff:**

```bash
/tmp/leadgen-cp01-venv/bin/ruff check app tests
```

**FAIL** — exit 1, **328 findings** (194 marked fixable and 11 additional unsafe fixes hidden by Ruff). The same Ruff 0.16.9 run against the extracted `origin/master` baseline found 330 findings; comparison by relative path, rule, and message found **0 new findings** on CP-01 and 2 baseline findings removed. The largest current groups are F401: 117, B008: 81, I001: 62, and BLE001: 23; the remaining 45 findings span 16 rules. No repository-wide mass-fix was applied.

**Repository-wide formatter:**

```bash
/tmp/leadgen-cp01-venv/bin/ruff format --check app tests
```

**FAIL** — 69 files would be reformatted, 57 are already formatted. The same check on `origin/master` found 71 files to reformat; path comparison found **0 newly unformatted files** on CP-01.

The following changed Python paths were checked separately with `ruff check` and `ruff format --check`; both passed (10 files already formatted): `app/api/admin_messages_secure.py`, `app/api/admin_recovery.py`, `app/models/landing_page.py`, `app/publisher/publisher.py`, `app/workers/outreach_sender_worker.py`, `tests/conftest.py`, `tests/test_admin_message_approval_security.py`, `tests/test_admin_recovery.py`, `tests/test_mvp_idempotency.py`, and `tests/test_mvp_pipeline_e2e.py`.

Exact changed-file commands:

```bash
/tmp/leadgen-cp01-venv/bin/ruff check \
  app/api/admin_messages_secure.py app/api/admin_recovery.py \
  app/models/landing_page.py app/publisher/publisher.py \
  app/workers/outreach_sender_worker.py tests/conftest.py \
  tests/test_admin_message_approval_security.py tests/test_admin_recovery.py \
  tests/test_mvp_idempotency.py tests/test_mvp_pipeline_e2e.py

/tmp/leadgen-cp01-venv/bin/ruff format --check \
  app/api/admin_messages_secure.py app/api/admin_recovery.py \
  app/models/landing_page.py app/publisher/publisher.py \
  app/workers/outreach_sender_worker.py tests/conftest.py \
  tests/test_admin_message_approval_security.py tests/test_admin_recovery.py \
  tests/test_mvp_idempotency.py tests/test_mvp_pipeline_e2e.py
```

**PASS — compile check:**

```bash
/tmp/leadgen-cp01-venv/bin/python -m compileall app -q
```

Exit 0.

**PASS — Alembic head check:**

```bash
PATH="/tmp/leadgen-cp01-venv/bin:$PATH" alembic heads
```

Output: `007 (head)` (one head).

**PASS — whitespace check:** `git diff --check` exited 0 before the code commit.

### 3. SQLite validation and migration checks

The complete Python suite above ran against an isolated SQLite file and passed. The migration chain is a separate result and **fails** on SQLite.

**Command:**

```bash
PATH="/tmp/leadgen-cp01-venv/bin:$PATH" \
  /tmp/leadgen-cp01-venv/bin/python scripts/check_migrations.py
```

**FAIL** — SQLite Alembic upgrade stops at `001 -> 002` (`002_deployments_and_job_id.py`). The helper truncates its subprocess error, so the shell migration check was also run for the full exception:

```bash
PATH="/tmp/leadgen-cp01-venv/bin:$PATH" bash scripts/check_migrations.sh
```

**FAIL** — `NotImplementedError: No support for ALTER of constraints in SQLite dialect` while applying revision 002's `op.add_column`. The shell script detected the single head (`007`) before attempting the upgrade. This is a SQLite dialect/migration incompatibility; it does not establish PostgreSQL migration behavior.

### 4. PostgreSQL validation

No `DATABASE_URL`/`POSTGRES_URL` service configuration, Docker, `psql`, or `pg_isready` is available in this sandbox. A real PostgreSQL migration attempt was made with the repository's test credentials against loopback:

```bash
DATABASE_URL='postgresql+psycopg://leadgen:leadgen@127.0.0.1:5432/leadgen' \
PATH="/tmp/leadgen-cp01-venv/bin:$PATH" \
  /tmp/leadgen-cp01-venv/bin/python scripts/check_migrations.py
```

**BLOCKED** — Alembic could not connect; a separate TCP probe returned `ConnectionRefusedError: [Errno 111] Connection refused`. The PostgreSQL integration suite was not run. SQLite results are not substituted for PostgreSQL evidence.

### 5. Security validation

**Dependency audit:**

```bash
/tmp/leadgen-cp01-security-venv/bin/pip-audit -r requirements.txt
```

**FAIL** — exit 1; 14 vulnerability rows for transitive `starlette==0.41.3`, representing seven distinct CVEs. Reported fix versions were:

- CVE-2025-54121 — Starlette 0.47.2
- CVE-2025-62727 — Starlette 0.49.1
- CVE-2026-48710 — Starlette 1.0.1
- CVE-2026-48817 and CVE-2026-48818 — Starlette 1.1.0
- CVE-2026-54282 — Starlette 1.3.0
- CVE-2026-54283 — Starlette 1.3.1

The audit failure was investigated; no project dependency was upgraded, per scope instruction.

**Bandit:**

```bash
/tmp/leadgen-cp01-security-venv/bin/bandit -r app -f json \
  -o /tmp/leadgen-cp01-bandit-report.json
```

Bandit exited 1 with 11 findings (1 HIGH, 10 LOW). The same 11 findings and severities occur on current master. The HIGH B324 finding is the existing MD5-based deterministic CSV source ID (`app/collector/adapters/csv.py`), not a password/signature use; the sender's B311 is the existing retry-jitter PRNG. CI marks the Bandit command non-blocking with `|| true`; neither finding was changed as unrelated to CP-01.

**Secret scanner command compatibility:**

```bash
/tmp/leadgen-cp01-security-venv/bin/trufflehog filesystem . --no-verification --fail
```

**FAIL / scan not performed** — exit 2. The `trufflehog` installed by the workflow's `pip install trufflehog` is a Python CLI expecting a `git_url`; it rejects `filesystem`, `.` and the supplied flags. The workflow's `|| true` masks this command failure, so that step does not prove a secret scan.

### 6. Local validation runner and strict Docker smoke

**Local runner:**

```bash
PATH="/tmp/leadgen-cp01-venv/bin:$PATH" \
DATABASE_URL='sqlite:////tmp/leadgen-cp01-local-validate.db' \
  bash scripts/local_validate_mvp.sh
```

**BLOCKED** — exit 1 at preflight: `[LOCAL-VALIDATE] FAILED: docker is not installed`. The runner did not reach its compile/test steps; those were run separately as recorded above.

**Strict Docker smoke:**

```bash
CLEANUP_ON_EXIT=1 bash scripts/smoke_mvp_pipeline_strict.sh
```

**BLOCKED** — exit 127 at `docker compose config`: `docker: command not found`. No container build or smoke service was started.

### 7. Canonical MVP E2E and regression cases

**Focused stabilization command:**

```bash
DATABASE_URL='sqlite:////tmp/leadgen-cp01-focused-tested-sha.db' \
  /tmp/leadgen-cp01-venv/bin/python -m pytest \
  tests/test_mvp_pipeline_e2e.py \
  tests/test_mvp_idempotency.py \
  tests/test_admin_recovery.py \
  tests/test_admin_message_approval_security.py -v
```

**PASS** — 18 passed, 20 warnings in 1.19s on tested SHA `022b5212a5e7bcf655880cfb5e0ed9271a03fd98`.

The canonical `test_real_worker_mvp_pipeline` now exercises the landing approval POST route with authentication and CSRF, real generation and publish workers, the secured message approval POST route, the outbound sender worker, inbound WhatsApp webhook, lead transition to `replied`, and a repeated inbound event that returns `changed: 0` without a duplicate row.

The focused regression cases passing include:

- Duplicate outbound send: `test_sender_second_run_does_not_call_provider_twice`.
- Repeated publish: `test_republishing_approved_landing_is_safe`.
- Duplicate inbound webhook: asserted in `test_real_worker_mvp_pipeline`.
- Generation failure and publication failure: `test_generation_failure_is_visible_and_does_not_create_landing`, `test_publication_failure_does_not_mark_lead_published`.
- Policy-blocked/DNC message remains terminal: `test_terminal_blocked_message_is_not_resendable`.
- Terminal message cannot be re-approved: `test_already_sent_message_cannot_be_approved`.
- Approval is POST-only, authenticated, and CSRF-protected: `test_get_approval_is_rejected`, `test_post_approval_requires_auth`, `test_post_approval_requires_csrf`.
- Recovery cannot requeue succeeded or blocked work: `test_succeeded_generation_is_not_retryable`, `test_blocked_or_dnc_message_cannot_be_requeued`; recovery CSRF and retry behavior also pass.

### 8. Missing retry-safety test investigation

`tests/test_mvp_retry_safety.py` is not tracked, is absent from the `origin/master` tree, and is absent from PR #2's complete diff. The exact checks were:

```bash
git ls-files --error-unmatch tests/test_mvp_retry_safety.py
git ls-tree -r --name-only origin/master | grep -F tests/test_mvp_retry_safety.py
git diff --name-only origin/master...origin/work/mvp-pipeline-stabilization \
  | grep -F tests/test_mvp_retry_safety.py
```

Each check found no tracked file/path. The existing retry/idempotency coverage is in `tests/test_mvp_idempotency.py`, with recovery behavior in `tests/test_admin_recovery.py`. The local runner's stale reference was changed to the existing `tests/test_mvp_idempotency.py`; no dummy test or weakened assertion was added.

## Fixes made within CP-01 scope

- Added `LandingStatus.generated`, which the content-generation worker already uses before publication.
- Created the `.tmp` staging parent before the publisher copies an approved draft, fixing the observed publication failure.
- Made the generation-failure regression test inject a failing adapter and assert its explicit error rather than relying on a nonexistent provider.
- Updated the canonical E2E to use a unique sandbox phone, avoiding cross-test lead association in the shared database, and to exercise the actual landing/message approval routes.
- Made the test DB fixture honor `DATABASE_URL` and perform SQLite-specific file cleanup so a PostgreSQL CI service can be selected rather than silently forcing SQLite.
- Repointed the local validation runner from the absent retry-safety test to the existing idempotency suite; added an explicit unauthenticated approval regression test.
- Applied lint/format cleanup only to touched CP-01 Python paths. No dependencies, architecture, or unrelated files were upgraded or broadly rewritten.

## Known blockers / disposition

1. Coverage remains 59.82% against the required 80% threshold.
2. Repository-wide Ruff and formatter gates remain red on baseline findings; CP-01 introduced no new findings and its touched files pass.
3. SQLite migration upgrade is unsupported at revision 002; PostgreSQL behavior is unproven because the service is unavailable.
4. `pip-audit` reports seven distinct Starlette CVEs. Dependency remediation was intentionally not performed in CP-01.
5. Bandit reports the same 11 findings as master; the configured secret-scan CLI does not run an actual filesystem scan.
6. Docker and PostgreSQL are unavailable locally, so the top-level local runner, strict smoke, and PostgreSQL job remain BLOCKED.

CP-01 stops here with **RESULT: BLOCKED**. PR #2 and PR #3 were not merged, no force-push was used, and CP-02 was not started.

## CP-01R — Blocker Resolution

Recorded: 2026-09-28

**RESULT: BLOCKED** — the SQLite portability and Starlette dependency-audit blockers are resolved, and the canonical MVP path/regressions pass. Coverage remains below the unchanged 80% gate, repository-wide Ruff/format gates remain red on baseline debt, and real PostgreSQL/Docker validations remain externally unavailable. No PR was merged and CP-02 was not started.

### Disposition summary

| Blocker | CP-01R disposition | Evidence summary |
|---|---|---|
| MVP-only coverage at 80% | **REMAINS_BLOCKED** | 287 tests pass, but coverage is 59.82% (2,925/4,890 statements). The 979 missing statements in deferred/out-of-MVP modules leave a 79.98% ceiling if every other missing statement were covered; do not expand into broad legacy testing. |
| Ruff / format policy | **REMAINS_BLOCKED** | CI gates all of `app tests`; 328 Ruff findings and 69 unformatted files remain. CP-01R changed no `app/` or `tests/` files; CP-01's master comparison found zero new findings, and the CP-01R changed-file comparison below also found none. No mass rewrite. |
| SQLite migration portability | **RESOLVED** | Fresh full-chain, downgrade/re-upgrade, schema assertions, and revision-001-with-data upgrade pass. |
| PostgreSQL runtime migration/integration | **EXTERNAL_BLOCKED** | No local PostgreSQL or Docker; loopback port 5432 refused the connection. PostgreSQL offline DDL generation passed but is not represented as a real database test. |
| Starlette dependency CVEs | **RESOLVED** | FastAPI 0.133.1 + Starlette 1.3.1 are pinned; the requirements audit reports no known vulnerabilities; full, focused, and relevant security tests pass. |
| Bandit / secret-scan baseline | **REMAINS_BLOCKED** | Bandit still reports the same 11 findings as master (1 HIGH, 10 LOW); the configured Python `trufflehog` CLI invocation does not perform a filesystem scan. Neither issue was introduced or changed in CP-01R. |
| Docker local runner / strict smoke | **EXTERNAL_BLOCKED** | Docker is not installed; the local validation runner and strict smoke both stop at their Docker preflight. |
| Canonical E2E and regression cases | **RESOLVED** | Full suite 287 passed; focused workflow/recovery/security suite 18 passed; webhook-signature/CSRF tests 10 passed. The worker E2E completes generation → landing approval → publish → message approval → send → inbound webhook → replied and verifies duplicate-webhook idempotency. |

### 1. Coverage and configured gate

**CI policy inspected:** `.github/workflows/ci.yml` runs `pytest tests/ -v --cov=app --cov-report=xml --cov-fail-under=80 --cov-config=.coveragerc`. Ruff and format run repository-wide over `app tests`. No `.coveragerc`, `pyproject.toml`, `setup.cfg`, `tox.ini`, or `pytest.ini` exists in this checkout; `.coveragerc` is referenced by CI but is absent. The equivalent CP-01R run with `--cov-config=.coveragerc` used coverage's default configuration, measured all of `app`, and added no exclusions.

**Command:**

```bash
COVERAGE_FILE=/tmp/leadgen-cp01r-coverage-config-final.data \
DATABASE_URL='sqlite:////tmp/leadgen-cp01r-coverage-config-final.db' \
  /tmp/leadgen-cp01r-venv/bin/python -m pytest tests/ -q \
  --cov=app --cov-report=term --cov-fail-under=80 --cov-config=.coveragerc
```

**REMAINS_BLOCKED** — exit 1 at the unchanged threshold: **287 passed, 22 warnings; 4,890 statements, 1,965 missing, 59.82%**. The prior exact count was 2,925 covered / 4,890 total. Deferred files listed in the CP-01 coverage analysis contain 979 of the missing statements; covering every other missing statement would produce at most 3,911/4,890 = **79.98%**. Reaching 80% therefore requires broad coverage expansion into deferred/out-of-MVP code; per scope, testing stopped here. No threshold reduction, app exclusion, or dummy test was added.

### 2. Ruff and format policy / regression comparison

The workflow's scope is explicitly whole `app tests`, not changed-files-only. CP-01R made no edits under either directory. The current run remains **328 Ruff findings** and **69 files that would be reformatted**; the CP-01 comparison to `origin/master` was 330 findings / 71 files and found zero new findings. No mass-fix was applied.

For completeness, the CP-01R-edited Alembic/Python migration-helper files (outside CI's Ruff target) were also compared with their CP-01 baseline using Ruff 0.16.9: **18 baseline findings, 17 current, zero introduced diagnostic identities**. Formatter output lists the same five already-unformatted files before and after; no additional file became unformatted. The migration helper and scripts remain outside the CI lint/format scope. `git diff --check` passes.

### 3. SQLite migrations and schema assertions

Revision 002 now adds/drops `leads.search_job_id` inside Alembic batch operations, keeps the nullable integer FK and index, and names the FK with PostgreSQL's conventional `leads_search_job_id_fkey` name. After the 002 repair advanced the fresh SQLite run, it exposed the same unsupported FK-column ALTER at revision 004, so that nullable `landing_pages.generation_id` FK also uses batch operations. Revisions 005/006 use batch operations to create/drop their existing named unique constraints, which otherwise use unsupported SQLite constraint ALTERs. These are the smallest additional portability changes needed for the full chain; they preserve the constraint/index names and logical schema on PostgreSQL, while SQLite uses Alembic's table-copy path.

`scripts/check_migrations.py` previously created a second SQLite temp file while Alembic migrated the URL for a different file. It now points Alembic and schema checks at the same database, asserts the new nullable columns, foreign keys, indexes and `foreign_key_check`, and creates a revision-001 database with a lead and search job before upgrading it to head. The existing-row check verifies data preservation, assigns a valid new FK, and confirms SQLite rejects a missing job. The shell checker now reports the current head accurately and includes `api_keys` in the table list.

**Fresh + existing SQLite check:**

```bash
PATH="/tmp/leadgen-cp01r-venv/bin:$PATH" \
  /tmp/leadgen-cp01r-venv/bin/python scripts/check_migrations.py
```

**PASS** — `SQLITE MIGRATION CHAIN VERIFICATION PASSED`; 14 tables present; revision 002/004 nullable-column, FK, and index assertions pass; downgrade one revision, re-upgrade, single-head check, full downgrade to base, full upgrade to head, and existing revision-001-with-data upgrade all pass. Three pre-existing noncritical expected-index warnings remain for `ix_outreach_events_lead_id`, `ix_outreach_events_message_id`, and `ix_outreach_messages_lead_id`.

**Shell-chain check:**

```bash
PATH="/tmp/leadgen-cp01r-venv/bin:$PATH" bash scripts/check_migrations.sh
```

**PASS** — revision `007 (head)`, all 14 tables including `api_keys`, unique constraint and `ix_leads_search_job_id` checks, one-step downgrade and re-upgrade. The script retains warnings for unrelated indexes that its existing SQLite check treats as nonfatal.

**PostgreSQL offline DDL-generation checks (not a live DB test):**

```bash
DATABASE_URL='postgresql+psycopg://leadgen:leadgen@127.0.0.1:5432/leadgen' \
PATH="/tmp/leadgen-cp01r-venv/bin:$PATH" \
  alembic -c alembic.ini upgrade head --sql

DATABASE_URL='postgresql+psycopg://leadgen:leadgen@127.0.0.1:5432/leadgen' \
PATH="/tmp/leadgen-cp01r-venv/bin:$PATH" \
  alembic -c alembic.ini downgrade 007:base --sql
```

Both exit 0 with the PostgreSQL dialect; generated SQL uses `ALTER TABLE ... ADD/DROP COLUMN` and named `ADD/DROP CONSTRAINT` statements. This confirms SQL rendering only and does **not** replace the blocked live PostgreSQL validation.

### 4. PostgreSQL and Docker availability

**EXTERNAL_BLOCKED evidence:** `docker`, `psql`, and `pg_isready` are not installed; `DATABASE_URL` and `POSTGRES_URL` are unset. A TCP probe to `127.0.0.1:5432` returned `ConnectionRefusedError: [Errno 111] Connection refused`. A live attempt with the repository's test URL also failed while running `alembic upgrade head` at the SQLAlchemy connection step. No PostgreSQL integration test was run and SQLite was not substituted.

```bash
PATH="/tmp/leadgen-cp01r-venv/bin:$PATH" \
DATABASE_URL='sqlite:////tmp/leadgen-cp01r-local-validate-final.db' \
  bash scripts/local_validate_mvp.sh
```

**EXTERNAL_BLOCKED** — exit 1: `[LOCAL-VALIDATE] FAILED: docker is not installed`. The script stopped at preflight; its compile, focused, and full-test steps were run separately as recorded below.

```bash
CLEANUP_ON_EXIT=0 PATH="/tmp/leadgen-cp01r-venv/bin:$PATH" \
  bash scripts/smoke_mvp_pipeline_strict.sh
```

**EXTERNAL_BLOCKED** — exit 127 at Compose preflight: `docker: command not found`. No services or containers were started; no infrastructure was added.

### 5. Starlette/FastAPI security remediation

The CP-01 audit found 14 advisory rows / seven distinct Starlette CVEs on transitive `starlette==0.41.3`. The fixes span Starlette 0.47.2, 0.49.1, 1.0.1, 1.1.0, 1.3.0, and 1.3.1; Starlette 1.3.1 is the lowest candidate satisfying the final identified fix. Official FastAPI release notes first add Starlette 1.x support in 0.133.0; PyPI metadata for FastAPI 0.133.1 accepts `starlette>=0.40.0` without an upper bound, and Starlette 1.3.1 requires Python >=3.10. The smallest compatible patch-line candidate was therefore pinned:

```text
fastapi==0.133.1
starlette==1.3.1
```

Sources: [FastAPI release notes](https://fastapi.tiangolo.com/release-notes/), [FastAPI 0.133.1 metadata](https://pypi.org/pypi/fastapi/0.133.1/json), [Starlette 1.3.1 metadata](https://pypi.org/pypi/starlette/1.3.1/json).

FastAPI 0.132+ also defaults to strict JSON `Content-Type` handling; the existing webhook/E2E JSON requests use `json=` and passed on the upgraded versions. The app has no `TemplateResponse`, lifespan event-handler, or `on_event` use found in the compatibility search. `pip check` reports no broken requirements. The upgraded Starlette TestClient emits deprecation warnings for the existing HTTPX-based test client and per-request cookies; tests pass and the warning-producing test setup was not broadened into unrelated dependency changes.

**Final requirements audit:**

```bash
/tmp/leadgen-cp01-security-venv/bin/pip-audit -r requirements.txt
```

**PASS** — exit 0: `No known vulnerabilities found`. No unresolved HIGH/CRITICAL runtime dependency vulnerability is reported by the final audit.

**Relevant security tests:**

```bash
DATABASE_URL='sqlite:////tmp/leadgen-cp01r-security-tests-final.db' \
  /tmp/leadgen-cp01r-venv/bin/python -m pytest \
  tests/test_admin_message_approval_security.py -v

DATABASE_URL='sqlite:////tmp/leadgen-cp01r-security-tests-final.db' \
  /tmp/leadgen-cp01r-venv/bin/python -m pytest \
  tests/test_phase06_comprehensive.py \
  -k 'WebhookSignature or CSRFPhase06' -v
```

**PASS** — 6 admin message-approval security tests and 10 webhook-signature/CSRF tests passed. Bandit remains a baseline-only result: `bandit -r app -f json -o /tmp/leadgen-cp01r-bandit-final.json` exits 1 with the same 11 findings as master (1 HIGH, 10 LOW, no MEDIUM). The HIGH is the existing MD5-based deterministic CSV source ID; no application source was changed in CP-01R. The workflow's TruffleHog command still does not perform a filesystem scan: its installed Python CLI rejects the `filesystem` subcommand/options. These baseline static-scan limitations are recorded, not described as resolved by the dependency audit.

### 6. Full, focused, and canonical MVP tests

The final test environment was Python 3.11.2, pytest 9.1.1, FastAPI 0.133.1, Starlette 1.3.1, and Pydantic 2.10.3.

**Full suite:**

```bash
DATABASE_URL='sqlite:////tmp/leadgen-cp01r-full-final.db' \
  /tmp/leadgen-cp01r-venv/bin/python -m pytest tests/ -q -ra
```

**PASS** — 287 passed, 22 warnings in 2.22s. Warnings include existing Pydantic/SQLAlchemy teardown warnings plus Starlette TestClient deprecations noted above.

**Focused stabilization/E2E/recovery/security suite:**

```bash
DATABASE_URL='sqlite:////tmp/leadgen-cp01r-focused-final2.db' \
  /tmp/leadgen-cp01r-venv/bin/python -m pytest \
  tests/test_mvp_pipeline_e2e.py \
  tests/test_mvp_idempotency.py \
  tests/test_admin_recovery.py \
  tests/test_admin_message_approval_security.py -v
```

**PASS** — 18 passed, 21 warnings in 1.23s. `test_real_worker_mvp_pipeline` executes actual generation and publication workers, authenticated/CSRF-protected landing approval, message approval, outbound send, inbound WhatsApp webhook, lead stage `replied`, and a repeated inbound event returning `changed: 0` with no duplicate row. The focused suite also verifies repeated sends/publishes, generation/publication failure states, terminal policy-blocked messages, retry/recovery guards, POST-only message approval, auth, and CSRF.

**Compile check:**

```bash
/tmp/leadgen-cp01r-venv/bin/python -m compileall app -q
```

**PASS** — exit 0.

### 7. CP-01R final disposition

Resolved within scope: SQLite migration portability and schema assertions; Starlette dependency remediation/audit; canonical MVP, idempotency, recovery, webhook-signature, CSRF, and message-approval security coverage. **REMAINS_BLOCKED:** the 80% coverage gate and repository-wide Ruff/format CI gates. **EXTERNAL_BLOCKED:** live PostgreSQL integration and Docker-backed validation. Bandit/secret-scan findings remain the documented master baseline/tooling limitation. Overall CP-01R remains **BLOCKED**; PR #2 and PR #3 remain open and unmerged, the branch was not force-pushed, and CP-02 was not started.
