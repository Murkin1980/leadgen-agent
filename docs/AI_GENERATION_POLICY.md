# AI Content Generation Policy

## Purpose

This document defines the rules and constraints for AI-generated content in the Leadgen Agent system.

## Core Principles

1. **No fabricated facts**: The AI model must never invent company information that is not present in the verified lead data.
2. **No automatic publishing**: All AI-generated content requires explicit human approval before publication.
3. **Full audit trail**: Every generation attempt is recorded with input, output, validation results, and token usage.
4. **Factual claims only**: All claims in generated content must reference their source in the verified data.

## What the AI MUST NOT Generate

- Years in business (unless provided in lead data)
- Guarantees or warranty periods (unless provided)
- Production capacity or volume
- Delivery timeframes (unless provided)
- Prices, discounts, or special offers (unless provided)
- Certifications or awards (unless provided)
- Number of completed projects (unless provided)
- Customer names or testimonials (unless provided)
- Materials or hardware brands (unless provided)
- Any unverifiable business claims

## What the AI CAN Generate

- SEO-optimized titles and descriptions based on verified company name, city, and category
- Service listings derived from the company's category
- Generic advantages common to the industry (clearly marked as template content)
- Work process stages (standard for the industry)
- FAQ items based on common questions
- Contact information copied from verified data

## Claim Verification

Every generated profile includes a `claims` array where each claim specifies:
- `text`: The claim text
- `source_field`: Which verified field supports this claim
- `verified`: Whether this claim is supported by verified data

Claims with `verified: false` are rejected by the content validator.

## Language Rules

- Content is generated in Russian by default
- Kazakh language is supported when explicitly requested
- Russian and Kazakh must not be mixed in a single page
- Template content (advantages, work stages) is provided in both languages

## Quality Checks

Before any content can be published:
1. Schema validation (all required fields present)
2. Phone number consistency between company and contacts
3. City consistency between generated content and lead data
4. No HTML tags in plain text fields
5. No script tags or executable content
6. No API keys or sensitive strings
7. No duplicate services
8. No empty hero or CTA sections
9. No unsupported claims (verified=false)
10. No fabricated business facts

## Model Output Format

The AI model must return JSON only, no HTML or executable code. The application renders HTML through controlled Jinja2 templates.

## Budget Controls

- Daily budget limit (configurable via `OPENAI_DAILY_BUDGET_USD`)
- Maximum requests per job (configurable via `OPENAI_MAX_REQUESTS_PER_JOB`)
- Per-request timeout (configurable via `OPENAI_TIMEOUT_SECONDS`)
- Retry with exponential backoff and jitter
- No retry on authentication or invalid request errors

## Audit Trail

Every generation attempt creates a `ContentGeneration` record containing:
- Provider and model used
- Input snapshot (what data was sent to the model)
- Output JSON (what the model returned)
- Validation results (errors and warnings)
- Token usage (input and output tokens)
- Estimated cost
- Status and timestamps

This audit trail is never deleted and is available for review.
