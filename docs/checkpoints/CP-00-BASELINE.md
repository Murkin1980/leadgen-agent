# CP-00 — Baseline and scope lock

Recorded: 2026-09-27

**RESULT: PASS**

## Baseline SHAs

- **Current `master`:** `08e74c119c3e3a46c2e5dda3fa77b7b38fb34aa1` (confirmed by both `git ls-remote origin refs/heads/master` and the GitHub branches API; local `master`/`origin/master` point to the same commit).
- **PR #2 head:** `b30448eac4e5dd6844fa245a75f1db12abd88b0f` (`work/mvp-pipeline-stabilization`; open, draft, not merged).
- **PR #2 base at inspection:** `b9f8356b3352b8454433b4286d9f016f14fb1baf`. Current master has two later governance commits (`262a792` and `08e74c1`); GitHub compare reports PR #2 as 16 commits ahead and 2 behind current master.
- **Authoritative checkpoint source:** PR #3, file `docs/LEADGEN_MVP_CHECKPOINTS_2026-09-28.md`, read from PR head `9ec4692a9a79e9a4c9e18fa84b1d1e54bc46cc06`.

The working tree was clean before this evidence file was created. No branch switch, merge, or PR #2 modification was made.

## Inspected sources and PR #2 scope

Read for this checkpoint: `AGENTS.md`, `docs/governance/SCOPE-CHANGE-CONTROL.md` (mandatory per `AGENTS.md`), `SIMPLICITY_REVIEW.md`, `skills/simplicity-first/SKILL.md` (mandatory per `AGENTS.md`), the PR #3 checkpoint plan above, and PR #2's description and complete GitHub diff. Also inspected current-master `README.md`, `.github/workflows/ci.yml`, `scripts/check_migrations.py`, `scripts/check_migrations.sh`, and `scripts/mvp_smoke_test.sh` to enumerate existing validation commands.

PR #2's complete diff is **14 files, 2,487 additions, 2 deletions**:

- Runtime: `app/api/admin_messages_secure.py`, `app/api/admin_recovery.py`, `app/main.py`, `app/workers/outreach_sender_worker.py`.
- Documentation: `docs/CODEX_ROUTER_MVP_SIMPLIFICATION_INSTRUCTION.md`, `docs/MURAT_PROJECT_ENGINEER_REEVALUATION_2026-08-08.md`, `docs/MVP_STATUS_TRANSITIONS.md`, `docs/PROJECT_PROGRESS_REVIEW_2026-07-28.md`.
- Validation: `scripts/local_validate_mvp.sh`, `scripts/smoke_mvp_pipeline_strict.sh`.
- Tests: `tests/test_admin_message_approval_security.py`, `tests/test_admin_recovery.py`, `tests/test_mvp_idempotency.py`, `tests/test_mvp_pipeline_e2e.py`.

### Canonical MVP path confirmation

The canonical path is:

**lead → landing generation → operator review → publish → message approval → WhatsApp send → inbound reply**

The PR #2 runtime diff remains a stabilization slice for this path: it adds the secured POST/CSRF message approval route, guards repeated sender execution for terminal statuses, and adds worker-level pipeline/idempotency tests and validation scripts. It adds no provider, database, queue technology, service, or architecture migration.

The one product-code area outside the *normal successful path* is `app/api/admin_recovery.py`: `/admin/recovery` and its POST retry routes support failed/rejected generation, failed approved publication, and retryable send recovery. This is an ancillary operator recovery path, not a new business-flow stage; it uses the existing Redis/RQ setup and is directly related to stabilization. The other new tests and scripts are verification/support code, not additional runtime paths.

**Documentation caveat:** `docs/CODEX_ROUTER_MVP_SIMPLIFICATION_INSTRUCTION.md` is a broad future-simplification instruction (including proposals around Redis/RQ, PostgreSQL, SQLite, and static serving). The reevaluation document also discusses architecture options. These are wider than the PR's narrow stabilization implementation, but no such architecture change is implemented in the diff. They are non-operative for this checkpoint: the newer PR #3 checkpoint plan and the current owner instruction govern execution; this document does not authorize architecture work. The scope check therefore passes for executable/runtime changes, with this documentation scope caveat explicitly recorded and locked out.

## Validation commands available (identified, not run)

### Current `master`

From `README.md`:

```bash
TEXT_GENERATOR_PROVIDER=mock DEPLOYMENT_PROVIDER=mock pytest tests/ -v
bash scripts/mvp_smoke_test.sh
python -m pytest tests/test_mvp_flow.py -v
python scripts/check_migrations.py
alembic upgrade head
alembic downgrade -1
```

Other migration-check entry points present on current master are `bash scripts/check_migrations.sh` and the `alembic heads` single-head check in `.github/workflows/ci.yml`.

The current CI workflow also defines:

```bash
ruff check app tests
ruff format --check app tests
python -m compileall app -q
pytest tests/ -v --cov=app --cov-report=xml --cov-fail-under=80 --cov-config=.coveragerc
alembic upgrade head
pytest tests/ -v --cov=app --cov-report=xml --cov-fail-under=80 --cov-config=.coveragerc -m "not slow"
docker compose up --build -d
bash scripts/smoke_test.sh
pip-audit -r requirements.txt
bandit -r app -f json -o bandit-report.json || true
trufflehog filesystem . --no-verification --fail || true
```

The PostgreSQL CI job runs migrations and the integration test command with PostgreSQL/Redis service environment; the Docker job then runs the smoke script and webhook GET/POST checks. See `.github/workflows/ci.yml` for the exact environment setup.

### Added by PR #2

The intended top-level local runner is:

```bash
bash scripts/local_validate_mvp.sh
```

Its defined steps are:

```bash
python -m compileall app -q
python -m pytest tests/test_mvp_pipeline_e2e.py tests/test_mvp_retry_safety.py tests/test_admin_recovery.py tests/test_admin_message_approval_security.py -v
python -m pytest tests/ -q
docker compose config
docker compose build api worker migrate
CLEANUP_ON_EXIT=1 bash scripts/smoke_mvp_pipeline_strict.sh
```

The strict smoke script starts the default services with:

```bash
docker compose up -d --build postgres redis migrate api worker preview
```

It then checks migration completion, API health, preview reachability, service state, secured admin/recovery route imports, and worker imports. PR #2 adds both shell scripts with mode `100644`, so invoke them through `bash` unless their executable mode is deliberately changed in a later checkpoint.

For CP-01 migration verification, the existing exact entry point is `python scripts/check_migrations.py` (SQLite temporary DB by default; PostgreSQL when `DATABASE_URL` is PostgreSQL). The full suite and strict smoke should also be invoked separately as required by the checkpoint plan; the local runner stops if its focused test command fails.

## Risks and scope findings

1. **PR #2 local runner references a missing test file.** `tests/test_mvp_retry_safety.py` is not present on current master and is not added anywhere in PR #2's complete diff. Therefore the focused pytest command in `scripts/local_validate_mvp.sh` is expected to stop with a missing-file error before the runner reaches its later steps. This was established by file/diff inspection only; the script was not run or changed in CP-00.
2. **Existing PR #2 checks are not green.** At inspection, GitHub reported failures for `Lint & Static Checks`, `Unit Tests (SQLite)`, `PostgreSQL Integration Tests`, and `Security Scan`; `Docker Smoke Test` was skipped. Failure details were not investigated in CP-00.
3. **The strict smoke is a startup/import smoke, not a full API-driven lead-to-reply journey.** The PR adds a worker-level E2E test for that journey; CP-01 must assess both without treating the smoke script alone as full-path proof.
4. **PR #2 is behind current master by two governance commits.** Its diff against current master is the same 14-file set, but the base/head divergence should be kept visible when CP-01 records its tested SHA.
5. **Future architecture instructions in the PR documentation are not authorization.** Do not remove or simplify Redis/RQ/PostgreSQL or perform other deep architecture work under CP-01.

No Python tests, migration checks, builds, Docker commands, or smoke tests were executed in CP-00. This preserves the CP-01 validation boundary.

## Exact next step

**CP-01 — Stabilization validation:** validate PR #2 head `b30448eac4e5dd6844fa245a75f1db12abd88b0f` without merging it. Run `python -m pytest tests/ -q`, `python scripts/check_migrations.py`, `bash scripts/local_validate_mvp.sh`, and `CLEANUP_ON_EXIT=1 bash scripts/smoke_mvp_pipeline_strict.sh`; verify API, worker, and preview startup and that the MVP path does not require production-only dependencies. Record exact commands/results and the missing `tests/test_mvp_retry_safety.py` issue; do not start CP-02 or make architecture changes.
