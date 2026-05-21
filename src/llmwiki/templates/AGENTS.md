# AGENTS — how to operate this brain

This directory is a **llm-wiki** brain. Knowledge lives in Markdown
(`wiki/`), raw sources in `raw/` (immutable), metadata in `.llmwiki/`.

## Principles
- `raw/` is immutable: read only, never edit.
- The LLM **proposes** changes as change requests; the human reviews and applies.
- `wiki/index.md` and `wiki/log.md` are generated — do not edit by hand.

## Commands
- `wiki ingest <file>` — read a source and propose wiki changes.
- `wiki ask "<question>"` — answer using the wiki as source.
- `wiki lint` — audit the health of the knowledge base.
- `wiki index` — rebuild the index and metadata.

See `WIKI_PROTOCOL.md` for the full maintenance rules.
