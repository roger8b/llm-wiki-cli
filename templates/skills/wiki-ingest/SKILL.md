---
name: wiki-ingest
description: Incorporate a new raw source — article, paper, transcript, doc, spec — into the user's Global LLM Wiki. Use this skill whenever the user adds a file under `raw/`, says "ingest this", drops a link or PDF they want preserved, or runs `llm-wiki ingest prepare`. Use it even when the user only asks for a summary of a new document, because the wiki pattern is to integrate every new source into existing pages (concepts, decisions, comparisons) rather than dump a one-off summary into chat.
---

# Wiki Ingest

## Mission

Ingestion is not summarization. The goal is to weave the source into the wiki: create a source page, update related concept pages, surface contradictions with prior knowledge, and leave the index and log accurate. A good ingest is judged later, when someone asks a question and the answer falls out of the wiki cleanly.

## Inputs

Required:

- A source path under `raw/` (e.g., `raw/articles/foo.md`).

Optional but useful:

- source type (`article`, `book`, `transcript`, `document`, `spec`, `image`, `external`);
- target domain or emphasis from the user;
- related pages the user already knows about.

If you ran `llm-wiki ingest prepare <source>`, read `.wiki/cache/ingest-context.md` — it gives you the hash, candidate related pages, and the checklist already.

## Workflow

### 1. Read the protocol

Read `WIKI_PROTOCOL.md`, `wiki/index.md`, and these schemas: `schemas/source.schema.md`, `schemas/concept.schema.md`, plus any others matching what you find.

### 2. Read the source carefully

Extract: core claims, named concepts, entities, decisions implied, workflows described, methods proposed, contradictions with prior pages, open questions, reusable definitions.

### 3. Find affected pages

Use `wiki/index.md` and grep/search across `wiki/` for the concepts and entities you extracted. Common landing spots: `wiki/sources/`, `wiki/concepts/`, `wiki/entities/`, `wiki/decisions/`, `wiki/synthesis/`, `wiki/comparisons/`.

### 4. Create the source summary

Create one page under `wiki/sources/<slug>.md` using `schemas/source.schema.md`. Set `raw_path` to the source path, fill `source_hash`, and complete every section. The source page is your audit trail — if a future reader doubts a claim elsewhere, they come here.

### 5. Update existing pages

For each affected page: add the new evidence, update outdated claims, add cross-links to the source page and to other related pages, flag contradictions inline ("**Conflict:** this contradicts `wiki/decisions/x.md`"), preserve still-valid prior context. Do not overwrite reviewed/canonical material silently.

### 6. Create new pages only when the concept is durable

A new concept page is justified when the idea is likely to be referenced again, has a clear definition, and would not fit as a section of an existing page. Trivial mentions go inline, not into new files.

### 7. Update the index

Add new pages and refresh modified ones in `wiki/index.md`. Group by type. Include status and `updated_at`. Or just run `llm-wiki index rebuild` afterward.

### 8. Append the log

Add an entry to `wiki/log.md`:

```
## [YYYY-MM-DD] ingest | <source title>
- source: <raw path>
- pages created: ...
- pages updated: ...
- contradictions: ...
- open questions: ...
```

### 9. Validate

Run `llm-wiki ingest commit <source>` to flip the manifest status to `ingested` and check the source summary, log, and hash.

## Guardrails

- Never edit files in `raw/`. The hash must stay stable for citations to remain meaningful.
- Default new synthesized pages to `status: draft`. Only the user promotes pages to `reviewed` or `canonical`.
- Never hide contradictions — even small ones. The wiki's main value over RAG is that conflicts are flagged, not averaged away.
- Trace every claim. If you write something in a page, the source page or a `raw/` file must back it.

## Done criteria

- `wiki/sources/<slug>.md` exists with valid frontmatter and complete sections.
- Affected pages updated with cross-links.
- New pages, if any, have valid frontmatter.
- `wiki/index.md` reflects the changes.
- `wiki/log.md` has the ingest entry.
- Contradictions are explicit.
- The raw source file is byte-for-byte unchanged.
