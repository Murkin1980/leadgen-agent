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
