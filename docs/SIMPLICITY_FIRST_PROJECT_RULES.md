# Simplicity-First Project Rules

## Purpose

These rules are mandatory for all future projects, major features, integrations, and architecture changes.

The objective is to solve the real user problem with the smallest reliable system, avoid premature complexity, and delay architecture, infrastructure, and automation until they are justified by proven need.

Core principle:

> First prove the simplest working path. Only then add structure, automation, scale, or resilience.

---

## 1. Do not start with code or architecture

Before creating repositories, services, databases, queues, agents, workers, schemas, or instruction files, define the problem in plain language.

The initial project brief must answer:

1. Who has the problem?
2. What specific result is needed?
3. What is the smallest successful outcome?
4. How is the task done manually today?
5. What part is actually painful, slow, expensive, or repetitive?
6. What can remain manual in version 1?
7. What must not be built yet?
8. What evidence will prove that the solution is useful?

No technical planning is allowed until these answers exist.

---

## 2. Research the simplest existing solutions first

Before inventing a new implementation, search for the simplest proven ways to solve the task.

Research must include, when relevant:

- manual workflow;
- spreadsheet or document workflow;
- no-code or low-code solution;
- built-in feature of an existing product;
- simple script;
- single-process application;
- hosted service;
- open-source tool;
- API integration;
- full custom system.

Search in this order, from simplest to most complex.

For each option record:

- what problem it solves;
- setup time;
- monthly cost;
- number of services;
- number of accounts or API keys;
- technical skill required;
- maintenance burden;
- failure points;
- vendor dependence;
- whether it can be tested in one day;
- whether it can be removed later without damage.

Prefer official documentation and primary sources when comparing current tools and APIs.

---

## 3. Use the solution ladder

Every project must be evaluated through this ladder:

### Level 0 — Manual process

Can the result be produced manually once or several times?

Examples:

- manually collect five leads;
- manually create one landing page;
- manually send one approved message;
- manually prepare one report.

If the manual workflow has not been tested, automation is premature.

### Level 1 — Checklist or template

Can the manual work be made reliable with:

- a checklist;
- a standard prompt;
- a document template;
- a spreadsheet;
- a folder structure;
- a reusable message template?

### Level 2 — Single script

Can one script remove the repetitive part without introducing a server, queue, database, or admin panel?

### Level 3 — Simple local or hosted application

Can the solution run as:

- one process;
- one application;
- one database;
- one deployment target?

### Level 4 — Small integrated system

Only when justified, add:

- one API service;
- one database;
- one background worker;
- one external integration.

### Level 5 — Distributed or production architecture

Queues, multiple workers, observability stacks, event buses, microservices, complex authorization, dead-letter systems, and multi-environment deployment are allowed only after real usage demonstrates the need.

The default target for a new project is Level 1, 2, or 3 — not Level 5.

---

## 4. Perform at least three simplification iterations

After collecting possible solutions, do not immediately choose one.

Run three explicit simplification passes.

### Simplification pass 1 — Remove features

Ask:

- Which features do not directly produce the first useful result?
- What can be manual?
- What can be postponed?
- What is included only because it may be useful later?
- Can version 1 serve one user, one city, one language, one channel, or one workflow?

Remove everything that is not required for the first proof of value.

### Simplification pass 2 — Remove components

Ask:

- Can two services become one process?
- Can several workers become one worker?
- Can a queue be replaced with a direct call?
- Can Redis be avoided?
- Can PostgreSQL be replaced with a file or SQLite for the first test?
- Can an admin panel be replaced by a simple page or command?
- Can an API be replaced by CSV import/export?
- Can a custom system be replaced by an existing hosted service?

### Simplification pass 3 — Remove operational burden

Ask:

- How many commands are required to run it?
- How many services must stay healthy?
- How many secrets must be configured?
- How many paid accounts are required?
- How many places can fail?
- Can one person understand and restart the whole system?
- Can the entire project run with one documented command?

Repeat simplification again if the system is still difficult to explain in a few sentences.

---

## 5. Choose the smallest reversible architecture

The selected solution must be the smallest architecture that:

- solves the current problem;
- is understandable by one person;
- can be tested quickly;
- can be changed without a rewrite;
- can be removed without losing critical data;
- has a clear upgrade path if demand appears.

Prefer reversible decisions.

Examples:

- keep advanced code disabled instead of immediately deleting it;
- use adapters only when a second real provider exists;
- use one repository unless there is a strong operational reason to split;
- use one deployable application until independent scaling is proven necessary;
- keep configuration simple and explicit;
- avoid abstractions created only for hypothetical future use.

---

## 6. Apply KISS, YAGNI, and Good Enough

### KISS

Choose the easiest solution that can be clearly explained, tested, and maintained.

### YAGNI

Do not build a feature, abstraction, integration, or service because it might be needed later.

Add it only when a current requirement, measured limitation, or real user behavior demands it.

### Good Enough

Stop when the solution reliably delivers the required outcome.

Do not delay validation while pursuing theoretical completeness.

These principles must not be used to justify unsafe code, data loss, or ignoring essential security. They are used to remove unnecessary scope, not necessary quality.

---

## 7. Mandatory complexity budget

Before implementation, define a complexity budget.

For a typical MVP, the default limits are:

- one repository;
- one main application;
- one database at most;
- one background worker at most;
- one deployment target;
- one primary user role;
- one external communication channel;
- one main workflow;
- no microservices;
- no event bus;
- no Kubernetes;
- no separate observability stack;
- no custom plugin architecture;
- no multiple providers unless two providers are actually used;
- no speculative scaling work.

Exceeding any limit requires a written justification based on a real current constraint.

---

## 8. Mandatory deletion and postponement list

Every plan must contain three lists.

### Build now

Only the functions required to produce the first useful result.

### Keep manual or disabled

Useful capabilities that can remain manual, mocked, feature-flagged, or documented.

### Do not build yet

All features that are not required for validation.

Examples of common postponements:

- multiple roles and permissions;
- analytics dashboards;
- Prometheus and Grafana;
- complex retry systems;
- dead-letter administration;
- multi-channel outreach;
- automatic AI replies;
- multi-language support when only one language is currently used;
- advanced backups before there is valuable production data;
- multi-tenant architecture;
- microservices;
- automatic scaling;
- elaborate design systems;
- integrations without an active user.

---

## 9. No infrastructure without a trigger

Infrastructure may be added only when a trigger occurs.

Examples:

### Add a queue when:

- a synchronous request regularly exceeds an acceptable duration;
- failures need independent retries;
- tasks must survive application restarts;
- concurrent workload is measured, not imagined.

### Add Redis when:

- a queue, distributed lock, shared rate limit, or short-lived cache is actually required.

### Add multiple workers when:

- one worker is a measured bottleneck;
- workloads need different scaling or isolation;
- one task type blocks another in real operation.

### Add microservices when:

- teams, deployment cycles, scaling, security boundaries, or failure isolation truly require separation.

### Add complex monitoring when:

- there is a production service with meaningful traffic and operational risk.

Until the trigger exists, do not add the component.

---

## 10. Design for one complete happy path first

Before edge cases and automation, implement one complete path from start to useful result.

Example:

1. Add one lead manually or through CSV.
2. Generate one landing page.
3. Review it manually.
4. Publish or preview it.
5. Approve one message.
6. Send it to one test contact.
7. Record one response.

Only after this path works should the project add volume, automation, retries, multiple providers, scheduling, or advanced administration.

---

## 11. Architecture must be explainable in five minutes

Before coding, the proposed system must be explainable to a non-specialist in five minutes.

The explanation must cover:

- what enters the system;
- what the system does;
- what comes out;
- where the data is stored;
- what external services are used;
- how to start and stop it;
- what happens when it fails.

If the explanation requires many diagrams, service names, queues, modes, or exceptions, simplify again.

---

## 12. One-command rule

The MVP should run with one documented command whenever practical.

Examples:

```bash
docker compose up --build
```

or:

```bash
python app.py
```

A new developer must be able to understand the startup path without reading many files.

---

## 13. Evidence before expansion

Do not start the next phase merely because the previous phase was coded.

Expansion requires evidence such as:

- real user completed the workflow;
- real lead was processed;
- real landing page was useful;
- real message was approved and sent;
- real response was received;
- current system is too slow or unreliable;
- manual work is now the proven bottleneck;
- a second provider or role is truly needed.

Without evidence, improve usability or remove complexity instead of adding features.

---

## 14. Required planning artifacts before coder instructions

Coder instructions may be created only after the following artifacts are complete.

### A. Problem statement

One page maximum.

### B. Simplest manual workflow

Step-by-step description of how to achieve the result without new software.

### C. Solution comparison

At least three options, including one manual or low-code option.

### D. Three simplification passes

Document what was removed in each pass.

### E. Final MVP scope

Include:

- build now;
- manual or disabled;
- do not build yet;
- success metric;
- failure conditions.

### F. Minimal architecture

Include only:

- components;
- data flow;
- external dependencies;
- startup command;
- rollback method.

### G. Deletion plan

List components or experiments that can be removed safely if unused.

Only after these artifacts are approved may implementation files and Codex instructions be written.

---

## 15. Required coder instruction format

Every coding instruction must begin with:

```text
Goal: the smallest working result.
Do not add architecture, abstractions, services, providers, queues, roles,
monitoring, or future features unless explicitly required below.
When two approaches work, choose the one with fewer components and less maintenance.
```

The instruction must include:

1. exact user-visible outcome;
2. exact files allowed to change;
3. components that must not be added;
4. features intentionally postponed;
5. one happy-path acceptance test;
6. maximum allowed services and dependencies;
7. rollback instructions;
8. deletion list for obsolete code;
9. required report of what was simplified;
10. stop condition.

The coder must stop when the acceptance test passes. The coder must not independently add the next phase.

---

## 16. Stop conditions

Development must stop and return to planning when:

- a new service is proposed;
- a second database is proposed;
- more than one worker is proposed;
- a new framework is introduced;
- a second provider is added without an active need;
- a feature requires many new models or migrations;
- setup requires more than one page of instructions;
- the project cannot run locally with one command;
- the architecture grows faster than the user-visible value;
- the implementation phase creates more operational work than it removes.

At that point, perform another simplification iteration.

---

## 17. Safe exceptions

Complexity is allowed when necessary for:

- preventing data loss;
- protecting credentials;
- legal or compliance requirements;
- essential authentication;
- safe handling of payments;
- medical or other high-risk data;
- proven reliability requirements;
- measured load;
- explicit enterprise requirements.

Even then, choose the simplest control that addresses the actual risk.

---

## 18. Review checklist before implementation

A project is ready for coding only when every answer is yes.

- [ ] The real problem is written in plain language.
- [ ] The manual workflow has been described or tested.
- [ ] Existing simple solutions were researched.
- [ ] At least three solution options were compared.
- [ ] Three simplification passes were completed.
- [ ] The MVP has one clear happy path.
- [ ] The architecture fits within the complexity budget.
- [ ] Unnecessary features are explicitly postponed.
- [ ] Every service has a current justification.
- [ ] Every dependency has a current justification.
- [ ] The project can be explained in five minutes.
- [ ] The project can be started with one documented command.
- [ ] The success metric is measurable.
- [ ] The rollback and deletion plans are defined.
- [ ] The coder has no permission to add future phases independently.

---

## 19. Review checklist after implementation

Before accepting the implementation:

- [ ] The happy path works end to end.
- [ ] The result solves the user problem.
- [ ] No unrequested service was added.
- [ ] No speculative abstraction was added.
- [ ] No duplicate provider or workflow was added.
- [ ] Disabled features remain disabled.
- [ ] Startup remains simple.
- [ ] Documentation matches the actual system.
- [ ] Unused code and dependencies are listed for deletion.
- [ ] The next phase is based on evidence, not imagination.

---

## 20. Default decision rule

When uncertain between two valid designs, choose the design with:

1. fewer services;
2. fewer dependencies;
3. fewer files;
4. fewer database tables;
5. fewer configuration variables;
6. fewer secrets;
7. fewer deployment steps;
8. less maintenance;
9. easier rollback;
10. faster proof of value.

A more complex option may be selected only with a written, current, measurable reason.

---

## Final principle

A project is not successful because it has sophisticated architecture.

A project is successful when the intended user receives useful value reliably, quickly, and with the least necessary operational burden.
