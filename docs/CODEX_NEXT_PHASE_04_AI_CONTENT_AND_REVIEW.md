# Codex Next Phase 04 — AI Content Generation, Review Workflow and Safe Publishing

## Goal

Implement the next production stage of Leadgen Agent: generate personalized landing-page content from verified lead data, allow manual review and editing, and publish only approved content.

The current collector pipeline must remain functional with `mock`, `csv`, and `two_gis` providers.

## Core workflow

```text
SearchJob
  -> collected and qualified Lead
  -> enrichment
  -> AI or template content draft
  -> validation and safety checks
  -> manual review
  -> approved LandingPage version
  -> render
  -> publish
  -> deploy
```

Do not publish AI-generated content automatically without an explicit approval state.

---

## 1. Content generation provider architecture

Create or complete the provider abstraction:

```python
class TextGenerationAdapter(Protocol):
    def generate_profile(self, lead: Lead, context: GenerationContext) -> GeneratedProfile:
        ...
```

Implement:

- `TemplateTextGenerationAdapter`
- `OpenAITextGenerationAdapter`
- `MockTextGenerationAdapter` for deterministic tests

Provider selection:

```env
TEXT_GENERATOR_PROVIDER=template
```

Allowed values:

- `template`
- `openai`
- `mock`

Use the current official OpenAI Python SDK.

Do not expose API keys in logs, responses, generated files, exceptions, or deployment metadata.

---

## 2. Configuration

Add to `.env.example`:

```env
TEXT_GENERATOR_PROVIDER=template
OPENAI_API_KEY=
OPENAI_MODEL=
OPENAI_TIMEOUT_SECONDS=45
OPENAI_MAX_RETRIES=3
OPENAI_TEMPERATURE=0.4
OPENAI_MAX_OUTPUT_TOKENS=2500
OPENAI_DAILY_BUDGET_USD=5
OPENAI_MAX_REQUESTS_PER_JOB=30
```

Validate configuration at startup:

- `OPENAI_API_KEY` is required only when provider is `openai`;
- model name must not be empty for OpenAI provider;
- timeout and retry values must be positive;
- budget values must be non-negative.

Application startup must remain possible with the default `template` provider and no API key.

---

## 3. Generation data model

Create a new model `ContentGeneration`.

Suggested fields:

- `id`: UUID string
- `lead_id`: FK
- `landing_page_id`: nullable FK
- `provider`
- `model`
- `prompt_version`
- `status`
- `input_snapshot_json`
- `output_json`
- `validation_errors_json`
- `input_tokens`
- `output_tokens`
- `estimated_cost_usd`
- `error_message`
- `created_at`
- `started_at`
- `completed_at`

Statuses:

- `queued`
- `running`
- `succeeded`
- `failed`
- `rejected`

Add an Alembic migration.

Do not overwrite previous generations. Every generation attempt must be auditable.

---

## 4. Landing review states and versions

Extend `LandingPage` with review workflow fields:

- `review_status`
- `approved_at`
- `approved_by`
- `current_version`
- `generation_id`

Review statuses:

- `draft`
- `needs_review`
- `approved`
- `rejected`
- `published`

Create `LandingPageVersion` model:

- `id`
- `landing_page_id`
- `version_number`
- `profile_json`
- `html_snapshot_path`
- `change_source`
- `change_note`
- `created_at`

`change_source` values:

- `template`
- `openai`
- `manual`
- `regeneration`

Each approved or manually edited revision must produce an immutable version record.

---

## 5. Structured generation input

Create `GenerationContext` containing only verified data:

- normalized company name;
- city;
- category;
- verified phone;
- WhatsApp link;
- verified social links;
- rating and review count;
- address;
- approved service categories;
- qualification reasons;
- source metadata;
- language preference;
- optional user-provided notes.

Never instruct the model to invent:

- years in business;
- guarantees;
- production capacity;
- delivery time;
- prices;
- discounts;
- certificates;
- completed-project counts;
- customer names;
- materials or hardware brands not present in verified data.

Missing facts must remain omitted or use neutral wording.

---

## 6. Prompt management

Store prompts as versioned files:

```text
app/generation/prompts/
  system_v1.txt
  landing_profile_v1.txt
```

Prompt requirements:

- return JSON only;
- comply with the Pydantic landing schema;
- use Russian by default;
- support Kazakh through a request parameter;
- avoid unverifiable claims;
- avoid fake testimonials;
- avoid fabricated portfolio items;
- do not copy text from source websites;
- keep wording commercially useful but factual;
- include clear WhatsApp and call CTAs.

Store the prompt version in every `ContentGeneration` record.

---

## 7. Strict structured output

Use a strict Pydantic schema for model output.

At minimum validate:

- metadata title and description;
- company block;
- hero title, subtitle and CTA;
- services;
- advantages;
- work stages;
- FAQ;
- contacts;
- theme;
- factual claims list;

Add a field such as:

```json
{
  "claims": [
    {
      "text": "...",
      "source_field": "rating",
      "verified": true
    }
  ]
}
```

Reject output containing unsupported claims.

Never render raw model HTML. The model may return JSON only. Jinja templates remain controlled by the application.

---

## 8. Content safety and quality validator

Create `GeneratedContentValidator`.

Checks:

- schema validity;
- forbidden claims;
- phone and WhatsApp consistency;
- company name consistency;
- city consistency;
- no fake reviews;
- no unsupported prices or discounts;
- no external scripts;
- no HTML tags in plain-text fields;
- maximum field lengths;
- no prompt leakage;
- no API key-like strings;
- no duplicate services;
- no empty hero or CTA.

Validation failure must:

- mark generation as failed or rejected;
- store validation errors;
- keep the previous approved version unchanged;
- never publish invalid output.

---

## 9. Queue and worker

Create a dedicated Redis queue:

```text
generate_content
```

Create worker:

```text
app/workers/content_generator_worker.py
```

Worker behavior:

1. Load lead and verified context.
2. Create or update `ContentGeneration` status.
3. Call configured provider.
4. Validate structured output.
5. Create a new `LandingPageVersion`.
6. Set landing review status to `needs_review`.
7. Do not publish automatically.
8. Record token usage and estimated cost.
9. Handle retryable and permanent errors separately.

Add the worker to Docker Compose.

---

## 10. API endpoints

Add endpoints:

### Generate content

```http
POST /leads/{lead_id}/content-generations
```

Optional body:

```json
{
  "language": "ru",
  "provider": "openai",
  "notes": "Акцентировать кухни и шкафы"
}
```

### List generations

```http
GET /content-generations
```

Filters:

- `lead_id`
- `status`
- `provider`

### Generation details

```http
GET /content-generations/{generation_id}
```

Do not return API keys, full system prompts, or sensitive internal exception traces.

### Review landing

```http
POST /landings/{landing_id}/approve
POST /landings/{landing_id}/reject
```

Reject body:

```json
{
  "reason": "Слишком общие преимущества"
}
```

### Manual edit

```http
PUT /landings/{landing_id}/profile
```

The request body must use the same strict landing profile schema.

Manual edits create a new version and return the landing to `needs_review` unless an explicit approve operation follows.

### Version history

```http
GET /landings/{landing_id}/versions
GET /landings/{landing_id}/versions/{version_number}
POST /landings/{landing_id}/versions/{version_number}/restore
```

Restoring creates a new version rather than deleting newer history.

---

## 11. Publishing rules

Update publishing logic:

- only `approved` landing pages can be published;
- rejected and `needs_review` pages must return HTTP 409;
- publish the currently approved version only;
- preserve atomic publication;
- set `review_status=published` after successful publication;
- deployment remains a separate operation.

Add tests proving that unapproved AI content cannot reach `sites/public`.

---

## 12. Cost and usage controls

Implement request and budget controls:

- maximum OpenAI requests per SearchJob;
- daily estimated cost limit;
- per-request timeout;
- retry with exponential backoff and jitter;
- no retry for authentication or invalid request errors;
- idempotency protection for duplicate generation requests;
- concurrent generation limit per worker.

Expose safe usage summary:

```http
GET /usage/openai
```

Response may include:

- requests today;
- input tokens;
- output tokens;
- estimated cost;
- configured daily budget;
- remaining estimated budget.

Never expose the API key.

---

## 13. Language support

Support:

- `ru`
- `kk`

Add language to generation context and generated profile.

Template provider must support both languages without OpenAI.

Do not mix Russian and Kazakh in one page unless explicitly requested.

---

## 14. Minimal review interface

Add a small server-rendered admin interface without a frontend framework.

Suggested routes:

```text
/admin/leads
/admin/landings
/admin/landings/{id}
/admin/generations/{id}
```

Use Jinja2 and lightweight CSS.

Landing review page should show:

- lead facts;
- qualification score;
- source/provider;
- generation provider and model;
- validation result;
- structured profile;
- rendered preview iframe or link;
- version history;
- approve button;
- reject button;
- edit form;
- regenerate button.

Add basic authentication controlled through environment variables:

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=
```

Reject startup in production mode if admin password is empty.

Do not store plaintext passwords in the database.

---

## 15. Observability

Add structured events:

- `content_generation_queued`
- `content_generation_started`
- `content_generation_succeeded`
- `content_generation_failed`
- `content_validation_failed`
- `landing_approved`
- `landing_rejected`
- `landing_version_created`
- `landing_published`

Include IDs but do not log full prompts, raw customer data, API keys, or entire model outputs.

---

## 16. Tests

Add unit tests for:

- provider factory;
- template generation in Russian and Kazakh;
- OpenAI adapter with mocked SDK responses;
- strict JSON parsing;
- malformed response handling;
- unsupported claim rejection;
- phone and city consistency;
- prompt version tracking;
- generation audit records;
- version creation;
- manual editing;
- approve and reject transitions;
- restore version behavior;
- publishing blocked before approval;
- budget enforcement;
- request limit enforcement;
- idempotency;
- admin authentication.

Add integration tests using `MockTextGenerationAdapter` only.

Tests and CI must never call the real OpenAI API.

---

## 17. Docker and CI

Add the content generation worker to `docker-compose.yml`.

CI must run with:

```env
TEXT_GENERATOR_PROVIDER=mock
DEPLOYMENT_PROVIDER=mock
COLLECTOR_PROVIDER=mock
```

Extend the smoke test:

1. Create mock collection job.
2. Wait for qualified lead.
3. Request content generation.
4. Wait for generation success.
5. Confirm landing is `needs_review`.
6. Confirm publish fails before approval.
7. Approve landing.
8. Publish landing.
9. Verify preview URL.
10. Run mock deployment.

---

## 18. README and runbook

Update README with:

- provider configuration;
- OpenAI setup;
- safe default template mode;
- generation workflow;
- approval requirement;
- admin interface;
- usage endpoint;
- troubleshooting.

Create:

```text
docs/AI_GENERATION_POLICY.md
docs/CONTENT_REVIEW_RUNBOOK.md
```

The policy must explicitly forbid fabricated company facts and automatic publishing without approval.

---

## Acceptance criteria

The phase is complete when:

1. Template, mock, and OpenAI generation providers share one interface.
2. OpenAI is optional and disabled by default.
3. Generated output is strict JSON validated by Pydantic.
4. Unsupported claims are rejected.
5. Every generation is stored as an audit record.
6. Landing versions are immutable and restorable.
7. AI drafts require manual approval.
8. Unapproved content cannot be published.
9. Admin review pages work without a frontend framework.
10. Russian and Kazakh template generation work.
11. Usage and budget controls are enforced.
12. Tests and smoke tests pass without external API calls.
13. README and policy documentation are updated.

## Constraints

- Do not remove existing collector or deployment providers.
- Do not allow the model to generate raw executable HTML.
- Do not automatically publish AI-generated drafts.
- Do not fabricate business facts.
- Do not log secrets or full prompts.
- Do not make real OpenAI calls in tests or CI.
- Do not introduce a heavy frontend framework.
- Preserve backward compatibility where practical.

## Completion report

After implementation provide:

1. changed-file list;
2. migration summary;
3. architecture changes;
4. new API examples;
5. admin review workflow;
6. test results;
7. smoke-test result;
8. remaining production configuration steps;
9. known limitations.
