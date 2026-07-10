---
name: simplicity-first
description: Mandatory pre-planning filter for new projects, large features, integrations, infrastructure changes, and architecture decisions. Research the simplest viable approaches, run several simplification passes, and only then prepare implementation files or coder instructions.
---

# Simplicity First

## Purpose

Prevent premature complexity. This skill MUST run before:

- starting a new project;
- adding a large feature;
- choosing architecture or infrastructure;
- introducing a new service, queue, database, framework, integration, repository, worker, monitoring stack, or deployment layer;
- writing a coding plan, PRD, technical specification, file structure, or Codex instructions.

The output of this skill is not code. Its output is a deliberately simplified solution that has passed several reduction rounds.

## Core rule

Do not design the most complete system. Design the smallest system that can prove the business result safely.

Prefer:

- one repository instead of several;
- one deployable application instead of microservices;
- one process or worker instead of many specialized workers;
- built-in framework capabilities instead of new dependencies;
- manual approval instead of premature automation;
- configuration instead of abstraction;
- a simple database table instead of a new subsystem;
- a reversible change instead of a permanent redesign;
- an existing trusted service instead of building infrastructure;
- deleting or postponing features instead of implementing speculative requirements.

## Mandatory workflow

### Stage 1 — Define the actual result

Write a short problem statement containing:

1. Who uses the result.
2. What exact action must become possible.
3. What measurable result proves the idea works.
4. What is explicitly outside the first version.
5. What can be done manually during validation.

Do not mention frameworks, services, databases, queues, APIs, or file structures yet.

### Stage 2 — Research simple approaches

Search current primary sources, official documentation, and proven examples.

Find at least three approaches:

- the simplest manual or semi-manual approach;
- the simplest implementation using existing tools;
- a more automated approach only for comparison.

For each approach record:

- setup effort;
- number of moving parts;
- ongoing maintenance;
- cost;
- failure modes;
- vendor or infrastructure dependencies;
- what business assumption it validates.

Do not choose the most technologically impressive option.

### Stage 3 — Simplification pass 1: remove speculative scope

Remove every item that is not required to prove the first business result.

Typical items to postpone:

- roles and permissions for hypothetical teams;
- advanced analytics;
- complex dashboards;
- multiple providers;
- background schedulers;
- event buses;
- microservices;
- distributed locks;
- extensive plugin systems;
- generalized workflow engines;
- multi-tenant support;
- automated scaling;
- complex retry and dead-letter interfaces;
- custom monitoring stacks;
- multiple deployment targets.

### Stage 4 — Simplification pass 2: combine components

Ask for every component:

- Can it run in the existing application?
- Can two processes become one?
- Can one database replace several stores?
- Can a synchronous operation replace a queue for current volume?
- Can a cron job replace a scheduler service?
- Can an admin page replace a separate frontend?
- Can a manual button replace automatic triggering?
- Can a configuration file replace a management subsystem?

Target for an MVP:

- one repository;
- one main application;
- one database;
- zero or one background worker;
- one deployment path;
- the minimum number of external services.

Any exception requires written justification.

### Stage 5 — Simplification pass 3: remove dependencies

Review every dependency and external service.

Keep it only when:

- the standard library or existing framework cannot reasonably do the job;
- it materially reduces risk or implementation time;
- it is actively maintained;
- replacing it later would be more expensive than using it now.

Reject dependencies added only for elegance, abstraction, future scale, or hypothetical reuse.

### Stage 6 — Simplification pass 4: operational reality

Simulate the normal workflow:

1. How is it started?
2. How is it stopped?
3. How is it configured?
4. How is a failure diagnosed?
5. How is data backed up?
6. How is the system restored?
7. How many commands are required for a new operator?
8. How many services must be healthy?

Prefer a design that a non-specialist can operate with a short runbook.

### Stage 7 — Simplicity score

Score the proposed MVP from 0 to 2 for each item:

- one clear business outcome;
- minimal number of services;
- minimal number of dependencies;
- one obvious deployment path;
- easy local start;
- easy rollback;
- manual fallback exists;
- no speculative features;
- understandable by one developer;
- testable end to end.

Maximum score: 20.

A plan may proceed only when:

- score is at least 16;
- no item scores 0 without explicit user approval;
- the project can be explained in five sentences;
- the first useful result can be demonstrated without building later-stage infrastructure.

### Stage 8 — Stop conditions

Stop and simplify again when any of these appears before validation:

- more than one repository;
- more than one database;
- more than one queue technology;
- more than one deployment platform;
- more than one worker unless required by measured load;
- a new service without immediate business value;
- architecture designed for hypothetical scale;
- automated workflow with no manual version proven first;
- infrastructure that takes longer to build than the user workflow;
- more than eight environment variables for the core MVP;
- more than five runtime containers for the normal local launch.

These are warnings, not absolute bans, but every exception must be justified in writing.

## Required output before coding

Produce a document named `SIMPLICITY_REVIEW.md` or a project-specific equivalent with these sections:

1. Business result.
2. Non-goals.
3. Approaches researched.
4. Simplification pass 1.
5. Simplification pass 2.
6. Simplification pass 3.
7. Simplification pass 4.
8. Final MVP workflow.
9. Components kept.
10. Components postponed.
11. Components rejected.
12. Simplicity score.
13. Risks and manual fallback.
14. Criteria for adding complexity later.

Only after this document is approved may the agent create:

- architecture documents;
- file trees;
- database schemas;
- implementation plans;
- Codex instructions;
- new repositories;
- deployment configurations.

## Complexity budget

Default MVP budget:

- repositories: 1;
- application services: 1;
- databases: 1;
- background workers: 0 or 1;
- queues: 0 or 1;
- deployment targets: 1;
- external providers per function: 1;
- admin interfaces: reuse the main application;
- monitoring: logs and health endpoint first;
- languages/frameworks: one primary stack.

Increasing the budget requires evidence from a working MVP, such as measured volume, observed failure, customer demand, compliance requirement, or proven maintenance pain.

## Rules for coder instructions

When the simplicity review is approved, coding instructions must:

- state the exact MVP outcome first;
- list non-goals prominently;
- prohibit speculative infrastructure;
- require reuse of the existing repository and stack;
- request the fewest files necessary;
- prefer one cohesive commit or a small number of reversible commits;
- require an end-to-end smoke test;
- include a deletion list for unused legacy code;
- include rollback steps;
- forbid claiming completion without a working user flow.

## Completion rule

This skill is complete only when the final proposal is simpler than the initial proposal and the removed or postponed complexity is explicitly documented.
