---
name: wiki-maintain
description: Keep the llm-wiki brain healthy — audit for broken links, orphan pages, and frontmatter issues, and propose fixes. Use when the user asks to "lint the wiki", "check the brain", "clean up", or after a batch of ingests, or before relying on the brain for canonical decisions.
---

# wiki-maintain — keep the brain healthy

You operate the brain **only** through the `wiki` CLI. Fixes are proposed as
change requests (CRs) and applied by a human — never write to the wiki directly.

## Workflow

1. **Audit** structural health (broken `[[links]]`, orphans, frontmatter). Use
   `--json` when you parse the findings yourself:
   ```bash
   wiki lint --json           # structural, as {"findings": [...]}
   wiki lint --all --json     # also semantic checks via the LLM
   ```
2. **Propose fixes** as a change request:
   ```bash
   wiki maintain       # lint + propose fixes as a CR
   ```
3. **Review and apply** the proposed fixes:
   ```bash
   wiki review <cr-id> --json
   wiki apply <cr-id>
   ```
4. Rebuild the index/metadata when needed:
   ```bash
   wiki index
   ```

## Long-running jobs

`wiki maintain` and `wiki lint --all` call the LLM and can take a while. Track
background work with `wiki jobs --json`; poll at a reasonable interval, not in a
tight loop. There is no cancel subcommand — interrupt a foreground run with
Ctrl-C (exit 130).

## Errors (exit codes, see docs/cli-json.md)

| exit | meaning | what to do |
|------|---------|------------|
| 1 | lint found errors | expected when issues exist; read the findings |
| 3 | not found (bad CR id) | re-list with `wiki review --json` before retrying |
| 5 | provider/LLM (no API key) | only affects `--all`/`maintain`; report it, suggest configuring the provider; don't retry blindly |
| 130 | cancelled (Ctrl-C) | stop |

With `--json`, failures print `{"error": {"code", "exit_code", "message"}}` on
stderr and leave stdout empty.

## Guardrails

- **Never write to `wiki/` directly.** Every fix goes through the CR flow
  (review + apply) — no exceptions.
- `wiki/index.md` and `wiki/log.md` are generated artifacts — don't hand-edit.
- Treat the brain as the source of truth; resolve contradictions explicitly
  rather than silently overwriting.
