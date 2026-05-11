# Wiki Protocol

## Purpose

This repository is a persistent, compounding knowledge base maintained by LLM agents.

The goal is not only to retrieve information, but to progressively synthesize, connect, update, and govern knowledge.

## Core layers

### Raw sources

Immutable evidence layer.

Path: `raw/`

Agents may read but must not edit.

### Wiki

Synthesized knowledge layer.

Path: `wiki/`

Agents may create and update pages following the schemas.

### Schemas

Operational rules and page templates.

Path: `schemas/`

Agents must follow these templates when creating or updating wiki pages.

### Skills

Reusable operational instructions for agents.

Path: `skills/`

## Main operations

### Ingest

Used when a new source is added.

Expected outputs:

- source summary;
- updated concept pages;
- updated entity pages;
- updated synthesis pages;
- updated index;
- log entry;
- contradiction notes when applicable.

### Query

Used when answering a question.

Expected behavior:

- read index;
- read relevant pages;
- inspect raw sources when needed;
- answer with citations or file references;
- suggest durable pages when useful.

### Lint

Used to maintain wiki health.

Expected checks:

- contradictions;
- stale pages;
- missing sources;
- missing links;
- duplicated concepts;
- orphan pages;
- unresolved questions.

### Refactor

Used to improve structure without losing knowledge.

Expected behavior:

- preserve source references;
- update links;
- update index;
- update log;
- prefer deprecation over deletion.

## Page types

`source`, `concept`, `entity`, `project`, `agent`, `workflow`, `decision`, `playbook`, `comparison`, `synthesis`, `open-question`, `glossary`, `lint-report`.

## Statuses

`draft`, `reviewed`, `canonical`, `deprecated`, `conflicting`, `needs-source`, `needs-review`.

## Frontmatter required fields

`type`, `title`, `slug`, `status`, `created_at`, `updated_at`.

## Log entry format

```
## [YYYY-MM-DD] <op> | <subject>
- files: ...
- notes: ...
```
