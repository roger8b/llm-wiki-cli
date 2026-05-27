---
name: wiki-ingest
description: Add a source (article, doc, PDF, transcript, notes) to the llm-wiki brain so its knowledge is woven into the wiki. Use whenever the user wants to "add this to the wiki", "ingest this", "save this to the brain", or hands you a file/learning worth keeping (architecture, concepts, decisions). Integrate knowledge into the brain instead of dumping a one-off summary into chat.
---

# wiki-ingest — feed the brain

Ingestion weaves a source into the brain. You operate the brain **only** through
the `wiki` CLI, and **every change is proposed as a change request (CR)** that a
human reviews and applies — you never write to the wiki directly.

## Workflow

1. **Register the source** (lands under `raw/`, which is immutable):
   ```bash
   wiki source add <file>
   ```
2. **Ingest** — the LLM reads the source and proposes wiki changes as a CR:
   ```bash
   wiki ingest <file>
   ```
3. **Review** the proposed diff:
   ```bash
   wiki review            # list pending CRs
   wiki review <cr-id>    # show the diff
   ```
4. **Apply** (writes to `wiki/`, reindexes, logs) or **reject**:
   ```bash
   wiki apply <cr-id>
   wiki reject <cr-id>    # diffs kept for auditing
   ```
5. Long-running ingests run as jobs: `wiki jobs`.

## Guardrails

- **Never edit `raw/`** — it is the immutable evidence.
- **Never write to `wiki/` directly.** Changes only via the CR flow above.
- `wiki/index.md` and `wiki/log.md` are generated — don't hand-edit them.
- Prefer updating an existing page over creating a near-duplicate; cite sources.
