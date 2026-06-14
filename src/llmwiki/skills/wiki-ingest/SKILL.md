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
3. **Review** the proposed diff (use `--json` when you parse it yourself):
   ```bash
   wiki review --json            # list pending CRs as JSON
   wiki review <cr-id> --json    # full CR incl. diffs, score, warnings
   ```
4. **Apply** (writes to `wiki/`, reindexes, logs) or **reject**:
   ```bash
   wiki apply <cr-id>
   wiki reject <cr-id>    # diffs kept for auditing
   ```

## Long-running jobs

Ingestion (especially long sources, PDFs, audio) runs as a job and can take a
while. Track it instead of busy-waiting:

```bash
wiki jobs --json    # status/progress of each job
```

Poll at a reasonable interval (e.g. several seconds between checks), not in a
tight loop. There is no cancel subcommand — interrupt a foreground run with
Ctrl-C (exit 130). When `wiki ingest` returns, its CR is already listed by
`wiki review`.

## Errors (exit codes, see docs/cli-json.md)

| exit | meaning | what to do |
|------|---------|------------|
| 3 | not found (bad file/path) | check the path; re-list sources before retrying |
| 4 | source already processed | the content is already in the brain. **Do NOT re-ingest with `--force` on your own** — tell the user and ask first |
| 5 | provider/LLM (no API key) | report it and suggest configuring the provider/settings; do not retry blindly |
| 130 | cancelled (Ctrl-C) | stop |

With `--json`, failures print `{"error": {"code", "exit_code", "message"}}` on
stderr and leave stdout empty.

## Guardrails

- **Never edit `raw/`** — it is the immutable evidence.
- **Never write to `wiki/` directly.** Every change goes through the CR flow
  (review + apply) above — no exceptions.
- `wiki/index.md` and `wiki/log.md` are generated — don't hand-edit them.
- Prefer updating an existing page over creating a near-duplicate; cite sources.
