# CLAUDE — operating this llm-wiki brain

You are operating **inside a llm-wiki brain**: a local-first, LLM-maintained
Markdown knowledge base. `AGENTS.md` is the full agent contract; `WIKI_PROTOCOL.md`
has the complete rules. This file is your quick, must-follow entry point.

## Hard rules

- **Never edit files in `raw/`** — it is immutable source material.
- **Never write to `wiki/` directly.** Propose a **change request** (a diff) and
  let the human review and apply it. Direct edits break auditability.
- **Never hand-edit `wiki/index.md` or `wiki/log.md`** — they are generated.
- Treat the brain as the **source of truth**: prefer updating an existing page
  over creating a near-duplicate, and cite the source of every important claim.

## How knowledge changes (the only path)

```
wiki source add <file>   # register raw material under raw/
wiki ingest <file>       # you read the source and PROPOSE a change request
wiki review [<cr>]       # human inspects the diff
wiki apply <cr>          # the CR is written to wiki/, reindexed, and logged
```

To answer questions, use `wiki ask "<question>"` — it is grounded in the wiki
and stays read-only.

## Stack (for contributors to the tool itself)

- Python 3.12 backend: Typer CLI + FastAPI API + MCP server (`src/llmwiki/`).
- LLM agents via deepagents/langchain; providers: Ollama / Anthropic / OpenAI / Google.
- Per-brain SQLite (`metadata.db`) + plain Markdown files; the brain is a git repo.
- Desktop app: Tauri (Rust shell + WebView) over the FastAPI sidecar (`ui/`).

See `AGENTS.md` for the layout, the canonical flow, page types, and the full
command surface; `WIKI_PROTOCOL.md` for the maintenance protocol.
