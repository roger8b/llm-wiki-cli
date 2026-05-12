---
name: wiki-ingest
description: Incorporate a new raw source into the brain. Use this skill whenever the user wants to add a document, article, transcript, PDF, or any file to the brain — even if they just say "add this to the wiki", "ingest this", "save this to the brain", or give you a file path. The skill must run before creating any brain content. Trigger it even when the user only asks for a summary, because the brain pattern is to integrate knowledge into existing pages, not dump one-off summaries into chat.
---

# Brain — Ingest

## Mission

Ingestion is not summarization. The goal is to weave the source into the brain: register a source page, update related concept pages, surface contradictions, leave the index and log accurate.

You interact with the brain **only through the `wiki` CLI**. Never read or write files inside the brain directly — every operation has a command.

## STEP 0 — Maintain a todo list (in your working memory, not as a file)

Before any tool call, create an internal todo list with these items and tick them off as you go. **Never write the todo list to a file.** Use your platform's in-memory todo mechanism (TodoWrite tool in Claude Code, or equivalent).

```
[ ] 1. Register source with wiki source add
[ ] 2. Run wiki ingest prepare + wiki ingest context
[ ] 3. Read protocol and schemas
[ ] 4. Read the source content
[ ] 5. Survey existing pages — what concepts/decisions already exist
[ ] 6. Compose source page (in memory)
[ ] 7. Pipe source page content to wiki page save via stdin
[ ] 8. Compose and save concept/decision pages (with valid slug refs only)
[ ] 9. Update existing affected pages
[ ] 10. wiki index rebuild + wiki log add
[ ] 11. wiki ingest commit
```

If you skip step 5, you will invent slugs that don't exist and `wiki page save` will reject them. Don't.

## STOP — CLI gates first

**Do not write any brain page until steps 1, 2, and 5 below have all completed.**

The CLI registers the source in the manifest, generates the ingest context, and surveys what already exists in the brain. Skipping any of these leaves the source orphaned and the new pages full of dangling refs.

## Step 1 — Register the source

```bash
wiki source add <absolute-path-to-file> --type <type>
```

Types: `article`, `book`, `document`, `transcript`, `spec`, `image`, `external`.

The CLI copies the file into the brain and prints the raw path (e.g. `raw/documents/foo.md`). Use that path verbatim for the next steps.

## Step 2 — Prepare the ingest context

```bash
wiki ingest prepare <raw-path>
wiki ingest context
```

The context contains:
- the canonical `raw_path` and `source_hash` you must put in the source page
- candidate related pages found via search

## Step 3 — Read protocol and schemas

```bash
wiki protocol
wiki schema show source
wiki schema show concept
wiki schema list                    # see all available schemas
```

## Step 4 — Read the source

```bash
wiki source show <raw-path-or-basename>
```

Extract: core claims, named concepts, entities, decisions implied, methods, contradictions with prior pages, open questions.

## Step 5 — Survey existing pages BEFORE writing anything

This is the most-skipped step and the source of every "unknown slug" error:

```bash
wiki page list                       # all pages — note the bare slugs
wiki page list --type concept
wiki page list --type source
wiki page list --type decision
wiki search "<concept-name>"         # repeat per concept you plan to reference
```

**Write down (in your todo list memory) the exact slugs you will reference in `related[]` and `sources[]`.** If a concept doesn't exist yet, do NOT add it to `related[]` — leave the array empty or omit those refs. You can cross-link later, after the related page is created.

Slug rules — these will be enforced at save time:
- Bare slug only: `pi-intercom` ✓ — not `concept/pi-intercom` ✗, not `wiki/concepts/pi-intercom.md` ✗
- The slug must already exist in the brain (verified by `wiki page list`)
- `sources[]` on a non-source page must reference a `type=source` page
- A page cannot reference itself in `related[]` or `sources[]`

## Step 6 — Save the source page (stdin, no temp files)

Compose the page content in your working memory, then pipe to the CLI. **Never write a temp file under `/tmp/` and pass it with `--file`.** Use stdin via heredoc:

```bash
cat <<'EOF' | wiki page save --type source --title "<title>"
---
status: draft
confidence: high
raw_path: <from wiki ingest context>
source_hash: <from wiki ingest context>
source_type: <document|article|book|...>
related: []
tags: [<short tags>]
---

# <title>

## Source metadata
...

## Executive summary
...

(rest of the schema sections)
EOF
```

`wiki page save` will validate refs (`related[]`, `sources[]`) and reject if any slug is unknown, has a path-form, or violates the type=source rule for `sources[]`.

If validation fails, fix the refs in your composed content and re-run the command. Don't try to patch the page after the fact — the page won't exist on disk yet.

## Step 7 — Save concept / decision / workflow pages

For each durable concept the source introduces:

```bash
cat <<'EOF' | wiki page save --type concept --title "<concept title>"
---
status: draft
confidence: medium
sources:
  - <bare slug of the source page you just created>
related:
  - <bare slugs of existing concept pages that this connects to — only ones you confirmed via wiki page list>
tags: [...]
---

# <concept title>

(body)
EOF
```

The source-page slug is the slugified title — e.g. title "Pi Intercom: Local Comms" → slug `pi-intercom-local-comms`. After step 6 the CLI printed `✓ saved: source/<slug>` — use that bare slug here.

## Step 8 — Update affected existing pages

For pages already in the brain that this ingest changes:

```bash
cat <<'EOF' | wiki page update <existing-slug>
---
related:
  - <add new cross-links here>
---
(only frontmatter, body preserved)
EOF
```

Or to also rewrite the body:

```bash
cat <<'EOF' | wiki page update <existing-slug>
---
related: [...]
---

# Existing Title

(new body — frontmatter merged, dates auto-refreshed)
EOF
```

## Step 9 — Refresh index and log

```bash
wiki index rebuild
wiki log add --type ingest --message "<source title> — pages created: <slugs>; updated: <slugs>"
```

## Step 10 — Commit

```bash
wiki ingest commit <raw-path>
```

This validates: source page exists with matching `raw_path` and `source_hash`, all pages have valid ref slugs, log entry references the ingest. If it passes, the CLI:
- flips the manifest status to `ingested`
- creates a git commit in the brain

If commit fails, fix the issues it reports and re-run. Do not bypass the commit.

## Guardrails

- **Never modify raw sources.** Their hash must stay stable for citations.
- **Always use bare slugs in `related[]` / `sources[]`.** No `/`, no `.md`, no `type/slug`.
- **Always survey before saving** (step 5). The CLI will reject unknown slugs.
- **Never write to `/tmp/` to pass content to the CLI.** Use stdin via heredoc.
- **Never write files inside the brain directly.** Use `wiki page save` / `wiki page update`.
- **Never invent CLI commands.** If unsure, run `wiki --help`.
- **Maintain a todo list in working memory** — don't lose track between steps.

## Done criteria

- All 11 todo items checked off
- `wiki source list` shows the source as `ingested`
- `wiki ingest commit` passed without errors
- Git log in the brain shows the new commit
