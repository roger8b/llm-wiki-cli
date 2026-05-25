# AGENTS — operating contract for this brain

This directory is a **llm-wiki brain**: a local-first, LLM-maintained Markdown
knowledge base. This file is the operating contract for any human or agent
working here. Claude users also get `CLAUDE.md`. Full rules: `WIKI_PROTOCOL.md`.

## Layout

```
raw/            immutable source material (never edit)
wiki/           the knowledge base — Markdown pages by type
  index.md      GENERATED map of the wiki (do not hand-edit)
  log.md        GENERATED audit log (do not hand-edit)
schemas/        page templates + schema reference
.llmwiki/       brain marker (metadata lives in ~/.wiki/brains/<id>/)
```

## Operating principles (non-negotiable)

- **`raw/` is immutable.** Read it; never edit or delete its files.
- **Changes happen only through change requests (CRs).** The LLM *proposes* a
  diff; a human *reviews* and *applies* it. Never write to `wiki/` directly.
- **`wiki/index.md` and `wiki/log.md` are generated artifacts** — rebuilt by the
  tool, never hand-edited.
- **The brain is the source of truth** for durable knowledge. Prefer updating an
  existing page over creating a new one.
- **Everything stays auditable.** Every applied change is a reviewable diff and
  is recorded in `wiki/log.md`; the brain is a git repo.
- Link pages with `[[Page Title]]`. Every important claim cites its source.
  Mark contradictions explicitly.

## Canonical flow

```
wiki brain create <path>     # scaffold + register + activate a brain
wiki source add <file>       # register raw material under raw/
wiki ingest <file>           # LLM reads a source -> proposes a CR
wiki review [<cr>]           # inspect pending change requests / diffs
wiki apply <cr>              # write the CR to wiki/, reindex, log
wiki ask "<question>"        # answer grounded in the wiki
```

## Command surface

Brains & sources:

- `wiki brain create <path>` — scaffold + register + activate a brain
- `wiki brain list | current | use <ref> | add <path> | rm <ref>` — manage brains
- `wiki source add <file>` / `wiki source list` — manage raw sources in `raw/`

Knowledge in / out (all writes go through a CR):

- `wiki ingest <file>` — LLM reads a source and proposes a CR
- `wiki ask "<question>"` — answer grounded in the wiki (read-only)
- `wiki maintain` — lint + propose fixes as a CR
- `wiki page create <title>` / `wiki page open <path>` — page management

Review & apply CRs:

- `wiki review [<cr>]` — list pending CRs / show a diff
- `wiki apply <cr>` — write the CR to `wiki/`, reindex, log
- `wiki reject <cr>` — discard a CR (diffs kept for auditing)
- `wiki jobs` — list background jobs (ingest / lint / query)

Index, search, health:

- `wiki index` — rebuild metadata and regenerate `wiki/index.md`
- `wiki search "<term>"` — keyword (FTS5) search over pages
- `wiki lint [--all]` — audit health (structural; `--all` adds semantic via LLM)
- `wiki log` — print `wiki/log.md`

Interfaces:

- `wiki serve` — start the API + desktop UI backend
- `wiki mcp` — start the MCP server (exposes the brain to external agents)

> Run `wiki <command> --help` for options. The CLI, the desktop app, and the MCP
> server all operate the **same** brain through these flows.

## Page types & frontmatter

Types: `concept` | `entity` | `source_summary` | `synthesis` | `decision` |
`project` | `research`.

Frontmatter keys: `title`, `type`, `tags`, `sources`, `updated_at`,
`confidence`. Templates live in `schemas/page_templates/`.

See `WIKI_PROTOCOL.md` for the complete maintenance rules.
