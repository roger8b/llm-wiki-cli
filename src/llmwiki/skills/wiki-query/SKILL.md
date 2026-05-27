---
name: wiki-query
description: Answer a question using the llm-wiki brain as the source of truth. Use whenever the user asks something the brain might already cover (concepts, decisions, architecture, prior research) — even if they don't say "search the wiki". Prefer the brain over guessing; cite the pages you used.
---

# wiki-query — use the brain to answer

The brain (a llm-wiki knowledge base) is the source of truth for durable
knowledge. Consult it before answering from memory. You operate it **only**
through the `wiki` CLI — never read or write brain files directly.

## Workflow

1. **Ask the brain.** It retrieves and answers grounded in the wiki:
   ```bash
   wiki ask "<the question>"
   ```
2. **Or search** when you need to locate pages by keyword:
   ```bash
   wiki search "<term>"
   wiki page open <path>     # read a specific page
   ```
3. **Answer with citations.** Base the answer on what the brain returned and name
   the pages/sources it cited. If the brain doesn't cover it, say so explicitly.
4. **Capture durable conclusions.** If the answer is reusable knowledge, feed it
   back (see `wiki-ingest`) so the brain compounds instead of losing the work to
   chat.

## Guardrails

- Don't invent facts the brain didn't return; prefer "the wiki doesn't cover this".
- `wiki ask` is read-only — it never changes the brain.
- Saving an answer as a page goes through a change request (review + apply), never
  a direct write.
