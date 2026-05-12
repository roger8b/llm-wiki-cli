---
name: wiki-ingest
description: Incorporate a new raw source into the brain. Use this skill whenever the user wants to add a document, article, transcript, PDF, or any file to the brain — even if they just say "add this to the wiki", "ingest this", "save this to the brain", or give you a file path. The skill must run before creating any brain content. Trigger it even when the user only asks for a summary, because the brain pattern is to integrate knowledge into existing pages, not dump one-off summaries into chat.
---

# Brain — Ingest

## Mission

Ingestion is not summarization. The goal is to weave the source into the brain: register a source page, update related concept pages, surface contradictions with prior knowledge, leave the index and log accurate.

You interact with the brain **only through the `wiki` CLI**. Never read or write files inside the brain directly — every operation has a command.

## STOP — CLI gates first

**Do not create any brain page until steps 1 and 2 below have completed successfully.**

The CLI registers the source in the manifest and generates the ingest context. Skipping it leaves the source orphaned — invisible to `wiki source list`, `wiki lint`, and `wiki ingest commit` — and the source page you write will lack the required `raw_path` and `source_hash`.

## Step 1 — Register the source

```bash
wiki source add <absolute-path-to-file> --type <type>
```

Types: `article`, `book`, `document`, `transcript`, `spec`, `image`, `external`.

The CLI copies the file into the brain and assigns it an internal path you'll use in the next steps. The output line shows that path (e.g. `raw/documents/foo.md`) — use it verbatim.

## Step 2 — Prepare the ingest context

```bash
wiki ingest prepare <raw-path-from-step-1>
wiki ingest context                  # read what the CLI generated
```

The context file contains:
- the canonical `raw_path` and `source_hash` to put in your source page frontmatter
- the source's status in the manifest
- candidate related pages found via search

## Step 3 — Read protocol and schemas

```bash
wiki protocol                        # the brain's rules
wiki schema show source              # required frontmatter for source pages
wiki schema show concept             # for concept pages
wiki schema list                     # see all schema types
```

## Step 4 — Read the source

```bash
wiki source show <raw-path>          # or the basename, e.g. foo.md
```

Extract: core claims, named concepts, entities, decisions implied, workflows described, methods, contradictions with prior pages, open questions.

## Step 5 — Find affected pages

```bash
wiki search "<concept>"              # repeat per concept
wiki page list --type concept        # browse existing concepts
wiki page show <slug>                # read each candidate
```

## Step 6 — Create the source summary page

Compose the page content (with the schema's required sections — `raw_path` and `source_hash` from `wiki ingest context` must be filled). Save it with:

```bash
wiki page save --type source --title "<title>" --file /tmp/source-page.md
# or stream via stdin:
cat <<'EOF' | wiki page save --type source --title "<title>"
... content ...
EOF
```

## Step 7 — Update affected pages

For each related page that needs new evidence, contradictions flagged, or cross-links:

```bash
wiki page update <slug> --file /tmp/updated.md
```

Inline conflicts where they appear ("**Conflict:** this contradicts decision `<slug>`"). Never silently overwrite reviewed or canonical material.

## Step 8 — Create new pages only for durable concepts

A new concept page is justified when the idea will likely be referenced again and has a clear definition. Trivial mentions go inline in existing pages.

```bash
wiki page save --type concept --title "<title>" --file /tmp/concept.md
```

## Step 9 — Update index and log

```bash
wiki index rebuild
wiki log add --type ingest --message "<source title> — pages created: …; updated: …"
```

## Step 10 — Commit

```bash
wiki ingest commit <raw-path>
```

This validates: source page exists, log entry references it, source hash unchanged. Fix any errors before finishing.

## Guardrails

- **Never modify raw sources.** Their hash must stay stable for citations.
- **`raw_path` and `source_hash`** in the source page must come from `wiki ingest context`, never invented.
- **Default new synthesized pages to `status: draft`.** Only the user promotes to `reviewed` or `canonical`.
- **Never hide contradictions.** Flag them inline. The brain's main value over RAG is that conflicts are visible.
- **Never invent CLI commands.** If unsure, run `wiki --help`.

## Done criteria

- `wiki source add` and `wiki ingest prepare` ran before any page was created
- A source page exists with valid `raw_path` and `source_hash`
- Affected pages updated with cross-links and conflict flags
- `wiki index rebuild` ran and `wiki log add` recorded the ingest
- `wiki ingest commit` passed without errors
