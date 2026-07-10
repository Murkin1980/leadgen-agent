# Codex Next Phase 02 — Deployment Hardening and Real Lead Collection Foundation

## Current audit result

The stabilization commit fixed the main repository issues:

- all application services and Nginx now share `./sites` through bind mounts;
- the obsolete named `sites` volume was removed;
- `sites/public/` is no longer ignored by Git;
- Git and Cloudflare deployment scripts are separated;
- the deployment branch is aligned to `master`;
- Alembic migrations run through a dedicated `migrate` service;
- slug validation and atomic publication were added;
- GitHub Actions and additional tests were added.

One blocking issue remains:

- `POST /jobs/{id}/deploy` enqueues `run_deployer` into the `publish` RQ queue;
- `run_deployer` calls `npx wrangler`;
- the Python Docker image does not contain Node.js, npm, npx, or Wrangler;
- therefore deployment started through the API will fail with `npx not found`.

This task must fix that issue before connecting a real 2GIS collector.

---

## Goal

Deliver a reliable deployment subsystem and prepare the project for the first real lead source adapter.

The final flow must be:

```text
POST /jobs
→ collect
→ enrich
→ generate
→ publish locally
→ preview through Nginx
→ explicit Cloudflare deployment request
→ deploy queue
→ dedicated deployer service with Wrangler
→ deployment status stored in PostgreSQL
```

---

## Part 1. Create a dedicated deploy queue

Do not use the `publish` queue for Cloudflare deployment.

Create a Redis queue named:

```text
deploy
```

Update:

```http
POST /jobs/{job_id}/deploy
```

so it enqueues:

```python
Queue("deploy", connection=redis_conn)
```

The publish worker must only copy generated files into `sites/public/`.

The deploy worker must only perform external deployment.

---

## Part 2. Add a dedicated deployer Docker image

Create a separate Dockerfile:

```text
Dockerfile.deployer
```

Recommended base image:

```dockerfile
FROM node:22-alpine
```

The deployer image must contain:

- Node.js;
- npm;
- Wrangler;
- Python 3 if the existing Python RQ worker is retained;
- project Python dependencies required by the deployer worker.

Preferred implementation:

1. use a multi-runtime image based on `python:3.12-slim`;
2. install Node.js and npm from an official supported source;
3. install Wrangler using the repository `package.json` and `npm ci`;
4. run the existing Python RQ deploy worker.

Alternative implementation:

- create a small Node deployment worker;
- keep queue communication compatible with Redis;
- do not duplicate business logic unnecessarily.

The simpler and safer MVP option is a Python deploy worker in an image that also has Node.js and Wrangler.

---

## Part 3. Add a deployer service to Docker Compose

Add:

```yaml
deployer:
  build:
    context: .
    dockerfile: Dockerfile.deployer
  env_file: .env
  command: ["python", "-m", "rq", "worker", "--url", "redis://redis:6379/0", "deploy"]
  depends_on:
    migrate:
      condition: service_completed_successfully
    redis:
      condition: service_healthy
  volumes:
    - ./sites:/app/sites
  restart: unless-stopped
```

The service must have access to:

```text
/app/sites/public
```

Do not install Node.js into every Python service unless there is a strong reason.

---

## Part 4. Cloudflare configuration

Add and validate these environment variables:

```env
CLOUDFLARE_API_TOKEN=
CLOUDFLARE_ACCOUNT_ID=
CLOUDFLARE_PAGES_PROJECT=leadgen-agent
CLOUDFLARE_PAGES_BRANCH=master
CLOUDFLARE_PUBLIC_URL=https://leadgen-agent.pages.dev
```

Update `.env.example` without real secrets.

The worker must not hardcode:

- project name;
- branch;
- account ID;
- public URL.

Read them from settings.

Before starting deployment, validate:

- `CLOUDFLARE_API_TOKEN` is present;
- `CLOUDFLARE_ACCOUNT_ID` is present;
- `sites/public` exists;
- `sites/public` contains at least one `index.html` inside a landing directory.

Return a clear configuration error instead of a generic subprocess failure.

---

## Part 5. Add deployment persistence

Create a new SQLAlchemy model:

```text
Deployment
```

Fields:

- `id` — UUID string;
- `job_id` — nullable foreign key to `search_jobs`;
- `provider` — `cloudflare_pages`;
- `status`;
- `project_name`;
- `branch`;
- `deployment_url`;
- `provider_deployment_id`;
- `stdout_excerpt`;
- `stderr_excerpt`;
- `error_message`;
- `created_at`;
- `started_at`;
- `completed_at`.

Statuses:

- `queued`;
- `running`;
- `succeeded`;
- `failed`.

Add an Alembic migration.

Do not overload `SearchJob.status` with Cloudflare deployment failures.

A lead collection job can remain `completed` even if a later external deployment fails.

---

## Part 6. Improve deployment API

### Start deployment

```http
POST /jobs/{job_id}/deploy
```

Response:

```json
{
  "deployment_id": "uuid",
  "job_id": 1,
  "status": "queued"
}
```

Rules:

- verify the job exists;
- verify the job has published landing pages;
- create a `Deployment` record;
- enqueue only the `deployment_id`;
- do not enqueue full ORM objects;
- prevent duplicate active deployments for the same job.

### Get deployment

```http
GET /deployments/{deployment_id}
```

Return full deployment status.

### List deployments

```http
GET /deployments
```

Filters:

- `job_id`;
- `status`;
- `limit`;
- `offset`.

---

## Part 7. Make Wrangler execution configurable

Move subprocess execution into an adapter:

```python
class DeploymentAdapter(Protocol):
    def deploy(self, public_dir: Path) -> DeploymentResult:
        ...
```

Implement:

```text
CloudflarePagesDeploymentAdapter
MockDeploymentAdapter
```

`CloudflarePagesDeploymentAdapter` must:

- run Wrangler without shell interpolation;
- use a list of subprocess arguments;
- use a timeout;
- capture stdout and stderr;
- limit stored log size;
- parse the resulting deployment URL where possible;
- never print secrets;
- raise typed deployment exceptions.

`MockDeploymentAdapter` must be used in tests.

Add provider selection:

```env
DEPLOYMENT_PROVIDER=mock
```

Supported values:

```text
mock
cloudflare
```

Development and tests must default to `mock`.

---

## Part 8. Fix landing status ownership

Do not update every published landing globally after one deployment.

Current behavior selects all rows with status `published` and marks all of them `deployed`.

Change the relationship so only landing pages belonging to the requested job are affected.

Because `LandingPage` currently has no direct `job_id`, choose one of these approaches:

Preferred:

- add `search_job_id` to `Lead`;
- set it when a lead is collected;
- resolve deployment landing pages through `Lead.search_job_id`.

Alternative:

- add a many-to-many relation between jobs and leads if one lead may belong to several searches.

For the MVP, a direct nullable `search_job_id` on `Lead` is acceptable.

Add the migration and tests.

---

## Part 9. Cloudflare deployment script

Keep:

```text
scripts/deploy_cloudflare.sh
```

as a manual administrative fallback.

Update it to use the same environment variables as the adapter.

It must not contain hardcoded secrets.

It must execute the locally installed Wrangler binary where possible:

```bash
./node_modules/.bin/wrangler
```

Use `npx --no-install` only as a fallback.

Do not allow `npx` to silently download a different Wrangler version during production deployment.

Commit `package-lock.json` so the Wrangler version is reproducible.

Remove `package-lock.json` from `.gitignore`.

Use:

```bash
npm ci
```

instead of an unpinned dynamic installation.

---

## Part 10. Docker integration smoke test

Add a script:

```text
scripts/smoke_test.sh
```

It must:

1. start Docker Compose;
2. wait for `/health`;
3. create a test search job;
4. poll until the job is completed or failed;
5. verify at least one lead exists;
6. verify at least one landing is published;
7. verify `sites/public/{slug}/index.html` exists;
8. request the landing through Nginx;
9. verify HTTP 200;
10. create a mock deployment;
11. poll deployment status;
12. verify it becomes `succeeded`;
13. shut down the stack.

The smoke test must not contact real Cloudflare, OpenAI, or 2GIS.

---

## Part 11. GitHub Actions

Extend `.github/workflows/ci.yml` with:

### Unit tests

- install Python dependencies;
- run compile check;
- run pytest.

### Docker build

- run `docker compose config`;
- build all images, including deployer.

### Integration smoke test

Run the smoke test with:

```env
TEXT_GENERATOR_PROVIDER=template
DEPLOYMENT_PROVIDER=mock
```

Do not require repository secrets for the normal CI pipeline.

---

## Part 12. Begin the real collector foundation

After deployment tests pass, prepare but do not yet aggressively scrape 2GIS.

Create a provider-neutral collector interface supporting pagination:

```python
class CollectorAdapter(Protocol):
    def search_page(
        self,
        city: str,
        category: str,
        page: int,
        page_size: int,
    ) -> CollectedPage:
        ...
```

`CollectedPage` must contain:

- `items`;
- `page`;
- `page_size`;
- `has_more`;
- `provider_metadata`.

Implement:

- updated mock adapter;
- a disabled `TwoGisCollectorAdapter` skeleton;
- configuration switch `COLLECTOR_PROVIDER=mock|two_gis`.

The real adapter must remain disabled unless all required configuration is present.

Do not add stealth, CAPTCHA bypass, credential theft, or terms-of-service evasion.

Prefer an official API or user-authorized data access where available.

Add rate limiting, retries, and response caching abstractions, but keep network calls mocked in tests.

---

## Required tests

Add tests for:

- deployment record creation;
- duplicate active deployment prevention;
- missing Cloudflare configuration;
- mock deployment success;
- mock deployment failure;
- deployment timeout handling;
- only the current job's landings become deployed;
- deployment API status retrieval;
- deploy queue selection;
- deployer Docker image configuration;
- `package-lock.json` tracked in Git;
- no secrets stored in output logs;
- Docker smoke-test path;
- collector provider selection;
- paginated mock collection.

All existing tests must remain passing.

---

## Acceptance criteria

The task is complete when:

1. `docker compose up --build -d` starts all services, including the deployer.
2. The Python application containers no longer need Node.js.
3. The deployer container contains a pinned Wrangler installation.
4. `POST /jobs/{id}/deploy` creates a deployment record and uses the `deploy` queue.
5. Mock deployment succeeds in local development and CI.
6. Cloudflare deployment fails clearly when credentials are missing.
7. Deployment failure does not change a completed search job to failed.
8. Only landings belonging to the selected job are marked deployed.
9. Local Nginx preview still works.
10. Unit and integration tests pass.
11. CI builds every Docker image and runs the smoke test.
12. The collector layer is ready for a future real 2GIS adapter without enabling uncontrolled scraping.

---

## Deliverables

After implementation provide:

1. list of changed files;
2. Alembic migration IDs;
3. Docker service diagram;
4. deployment state diagram;
5. commands for local startup;
6. commands for mock deployment testing;
7. commands for real Cloudflare deployment;
8. test results;
9. CI result;
10. remaining tasks before enabling the real 2GIS adapter.
