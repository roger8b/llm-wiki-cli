---
name: wiki-query
description: Answer a question using the llm-wiki brain as the source of truth. Use whenever the user asks something the brain might already cover (concepts, decisions, architecture, prior research) — even if they don't say "search the wiki". Default to retrieving pages yourself (wiki search --json + wiki page open) and synthesising the answer; only delegate to wiki ask for broad multi-page synthesis. Prefer the brain over guessing; cite the exact pages you read.
---

# wiki-query — use the brain to answer

The brain (a llm-wiki knowledge base) is the source of truth for durable
knowledge. Consult it before answering from memory. You operate it **only**
through the `wiki` CLI — never read or write brain files directly.

You are a capable agent: prefer **retrieving the raw pages and synthesising the
answer yourself** over paying for a second LLM inside `wiki ask`. It is cheaper
and faster.

## Mode A — Retrieval (DEFAULT)

1. **Search** with structured output and filters:
   ```bash
   wiki search "<terms>" --json --limit 5
   # narrow when you know the shape:
   wiki search "<terms>" --json --type decision --tag auth --limit 5
   ```
   Each result has `path`, `title`, `score`, `source`, `snippet`, `type`, `tags`.
2. **Judge the snippets.** If they don't convince you, search again with
   alternative terms (synonyms, broader/narrower) before reading.
3. **Read the 1–3 most relevant pages:**
   ```bash
   wiki page open <path>
   ```
4. **Synthesise the answer yourself**, citing the exact `path`s you read. If the
   pages don't actually answer it, say the wiki doesn't cover it.

## Mode B — Delegated synthesis (exception)

Use `wiki ask "<question>"` (which runs an internal agent = a second LLM) **only**
when:
- (a) the question requires sweeping many pages, or
- (b) the user explicitly asked for the brain's own answer, or
- (c) retrieval (Mode A) failed after 2 attempts with different terms.

```bash
wiki ask "<question>" --json   # answer + citations as JSON
```

## Guardrails

- Cite **exact `path`s**. Never invent facts the brain didn't return — prefer
  "the wiki doesn't cover this".
- Read-only. Both modes never change the brain. Capturing a durable conclusion
  is a separate step → use `wiki-ingest` (goes through a change request).
- On a non-zero exit see **Errors** below; don't retry blindly.

## Errors (exit codes, see docs/cli-json.md)

| exit | meaning | what to do |
|------|---------|------------|
| 3 | not found (bad path/id) | re-run `wiki search` to get a valid `path` before retrying |
| 5 | provider/LLM (no API key) | only affects `wiki ask`; report it and suggest configuring the provider — prefer Mode A retrieval, which needs no LLM |
| 130 | cancelled (Ctrl-C) | stop |

With `--json`, a failure prints `{"error": {"code", "exit_code", "message"}}` on
stderr and leaves stdout empty.
