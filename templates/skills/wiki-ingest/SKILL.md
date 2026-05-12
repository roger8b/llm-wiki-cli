---
name: wiki-ingest
description: Incorporate a new raw source into the brain. Use this skill whenever the user wants to add a document, article, transcript, PDF, or any file to the wiki — even if they just say "add this to the wiki", "ingest this", "save this to the brain", or give you a file path. The skill must run before creating any wiki pages. Trigger it even when the user only asks for a summary, because the wiki pattern is to integrate knowledge into existing pages, not dump one-off summaries into chat.
---

# Wiki Ingest

## Mission

Ingestion is not summarization. The goal is to weave the source into the brain: create a source page, update related concept pages, surface contradictions with prior knowledge, and leave the index and log accurate.

## STOP — CLI first, always

**Do not create, edit, or write any wiki file until steps 1 and 2 below are complete.**

This is not optional. The CLI registers the source in the manifest and generates the ingest context. Skipping it leaves the source orphaned — invisible to `wiki source list`, `wiki lint`, and `wiki ingest commit`.

## Step 1 — Register the source

If the file is not already under `raw/`, run:

```bash
wiki source add <absolute-path-to-file> --type <type>
```

Types: `article`, `book`, `document`, `transcript`, `spec`, `image`, `external`.

This copies the file into the brain's `raw/<type>/` directory and records it in the manifest.

## Step 2 — Prepare the ingest context

```bash
wiki ingest prepare raw/<type>/<filename>
```

This writes `.wiki/cache/ingest-context.md`. Read that file — it gives you the hash, the raw path, the source status, and candidate related pages.

## Step 3 — Read protocol and schemas

Read:
- `WIKI_PROTOCOL.md`
- `wiki/index.md`
- `schemas/source.schema.md`
- `schemas/concept.schema.md`
- Any other schemas matching what you find in the source

## Step 4 — Read the source

Extract: core claims, named concepts, entities, decisions implied, workflows described, methods, contradictions with prior pages, open questions.

## Step 5 — Find affected pages

Search `wiki/` for the concepts and entities you extracted. Common landing spots: `wiki/sources/`, `wiki/concepts/`, `wiki/entities/`, `wiki/decisions/`, `wiki/synthesis/`, `wiki/comparisons/`.

## Step 6 — Create the source summary page

Create `wiki/sources/<slug>.md` using `schemas/source.schema.md`. Set `raw_path` to the path from step 1 (must be under `raw/`). Copy the `source_hash` from `.wiki/cache/ingest-context.md`. Complete every section — this is the audit trail.

## Step 7 — Update existing pages

For each affected page: add new evidence, update outdated claims, add cross-links, flag contradictions inline (`**Conflict:** this contradicts wiki/decisions/x.md`). Do not silently overwrite reviewed or canonical material.

## Step 8 — Create new pages only for durable concepts

A new concept page is justified when the idea will likely be referenced again and has a clear definition. Trivial mentions go inline.

## Step 9 — Update index and log

- Update `wiki/index.md` with new and modified pages, or run `wiki index rebuild`
- Append to `wiki/log.md`:

```
## [YYYY-MM-DD] ingest | <source title>
- source: raw/<type>/<filename>
- pages created: ...
- pages updated: ...
- contradictions: ...
- open questions: ...
```

## Step 10 — Commit

```bash
wiki ingest commit raw/<type>/<filename>
```

This validates the source page, log entry, and hash — then flips the manifest status to `ingested`. Fix any errors it reports before finishing.

## Guardrails

- Never edit files under `raw/`. The hash must stay stable for citations to remain meaningful.
- `raw_path` in source page frontmatter must be a `raw/` path — never an external path.
- `source_hash` must be filled from the ingest context, never left empty.
- Default new synthesized pages to `status: draft`. Only the user promotes to `reviewed` or `canonical`.
- Never hide contradictions — even small ones. Conflicts flagged, not averaged away.

## Done criteria

- `wiki source add` and `wiki ingest prepare` were run before any file was written
- `wiki/sources/<slug>.md` exists with valid frontmatter, populated `raw_path` and `source_hash`
- Affected pages updated with cross-links
- `wiki/index.md` reflects changes
- `wiki/log.md` has the ingest entry
- `wiki ingest commit` passed without errors
