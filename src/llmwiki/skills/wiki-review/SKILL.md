---
name: wiki-review
description: Triage the llm-wiki brain's pending change requests (CRs) so the user applies the obvious ones fast and focuses on the risky ones. Use when the user asks to "review the CRs", "what's pending in the wiki", "triage the queue", or after a batch of ingestions. Classify each CR (apply / needs-attention / reject) with a one-line reason; only run apply/reject after explicit user confirmation.
---

# wiki-review — triage the CR queue

Human review is the bottleneck of the pipeline. Your job: read every pending
change request (CR), classify it, and present a decision table — so the user
clears the easy ones quickly and spends attention on the risky ones. You operate
the brain **only** through the `wiki` CLI.

## Workflow

1. **List pending CRs:**
   ```bash
   wiki review --json
   ```
   `{"pending": [{id, status, files_changed, summary}]}`. Empty → tell the user
   the queue is clear and stop.
2. **Inspect each CR:**
   ```bash
   wiki review <id> --json
   ```
   The full CR includes `summary`, `changes[]` (each with `diff`, `operation`,
   `path`, `quality_score`, `quality_flags`), `warnings`, and `execution` meta
   (model, tokens, `used_fallback`). Some fields may be absent on older CRs —
   tolerate that. **Read the whole diff** before forming an opinion.
3. **Classify** each CR:
   - **apply** — high `quality_score`, diff coherent with the `summary`, no
     `warnings`, confidence not low.
   - **needs-attention** — potential contradiction, possible duplicate page, low
     confidence, `used_fallback: true`, or large/surprising diff. **When in
     doubt, choose this.**
   - **reject** — phantom CR (empty/incoherent), content not matching the source.
4. **Present a table** (one line per CR):

   | CR | verdict | why | pages |
   |----|---------|-----|-------|
   | CR-1 | apply | score 92, matches summary | wiki/concepts/rag.md |
   | CR-2 | needs-attention | fallback used, low confidence | wiki/decisions/x.md |
   | CR-3 | reject | empty CR, no pages written | — |

5. **Act only on explicit confirmation.** Never apply or reject on your own
   initiative. After the user confirms (per-CR or a confirmed batch):
   ```bash
   wiki apply <id>      # writes to wiki/, reindexes, logs
   wiki reject <id>     # diffs kept for auditing
   ```
   Partial apply is possible: `wiki apply <id> --only <path>` (repeatable).

## Guardrails

- **Never apply/reject without explicit user confirmation.**
- When unsure → **needs-attention**, never silent apply.
- Never edit CR content here — content edits belong in the app (page editor).
- Read the full diff of large CRs before judging.

## Errors (exit codes, see docs/cli-json.md)

| exit | meaning | what to do |
|------|---------|------------|
| 3 | not found (bad CR id) | re-list with `wiki review --json` before retrying |
| 130 | cancelled (Ctrl-C) | stop |

With `--json`, failures print `{"error": {...}}` on stderr; stdout stays empty.
