# AGENTS.md

## Mandatory first step: Simplicity First

Before planning or implementing any new project, major feature, integration, infrastructure change, architecture change, or new repository, read and apply:

`skills/simplicity-first/SKILL.md`

This requirement applies before creating:

- PRDs;
- architecture documents;
- technical specifications;
- database schemas;
- file structures;
- implementation phases;
- Codex instructions;
- deployment plans;
- new services or repositories.

## Required gate

The agent must first create or update a `SIMPLICITY_REVIEW.md` document containing:

- the actual business result;
- non-goals;
- researched simple approaches;
- at least three simplification passes;
- the final minimal workflow;
- components kept, postponed, and rejected;
- a simplicity score;
- manual fallback;
- evidence required before adding complexity.

No implementation plan may be produced until the simplicity review passes the gate defined in the skill.

## Default architecture budget

Unless the simplicity review proves otherwise:

- one repository;
- one main application;
- one database;
- zero or one worker;
- zero or one queue;
- one deployment target;
- one external provider per function;
- no speculative microservices;
- no infrastructure for hypothetical scale.

## Existing project rule

For changes to this repository, prefer deletion, consolidation, disabling, or reuse before adding a new component.

Complexity may be added only in response to measured load, a real failure, a legal/compliance requirement, or confirmed user demand.
## Shared unfinished-project deployment ritual

This repository is still under active development. Before every substantial change, read this file and the project README/session notes, check `git status`, preserve unrelated changes, and identify the exact build and deployment target.

Before claiming completion: run the project lint/typecheck/tests and a production build; commit and push the exact tested state; deploy only from a clean checkout; smoke-test the real public URL and the main user journey on desktop and mobile. A screenshot or local preview alone is not proof of a successful deployment.

For Cloudflare/OpenNext projects: prefer the adapter-supported production builder; if `Failed to load chunk server/chunks/ssr/...` occurs, check current OpenNext troubleshooting and use a Webpack build when recommended. Avoid deploying from OneDrive or paths with Cyrillic/spaces when artifacts behave inconsistently; use a clean ASCII-only clone under `C:\tmp`. After DNS/custom-domain creation, distinguish stale local `NXDOMAIN` cache from a server failure by checking a public resolver, direct HTTPS status, Worker logs, and then a fresh browser process.

Never weaken database authorization to make missing data appear. For OAuth migrations, verify user IDs, organization membership, ownership fields, RLS, storage access, and record counts. Never print or commit secrets.