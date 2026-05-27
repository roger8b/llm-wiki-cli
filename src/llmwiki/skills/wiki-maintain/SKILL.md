---
name: wiki-maintain
description: Keep the llm-wiki brain healthy — audit for broken links, orphan pages, and frontmatter issues, and propose fixes. Use when the user asks to "lint the wiki", "check the brain", "clean up", or after a batch of ingests, or before relying on the brain for canonical decisions.
---

# wiki-maintain — keep the brain healthy

You operate the brain **only** through the `wiki` CLI. Fixes are proposed as
change requests (CRs) and applied by a human — never write to the wiki directly.

## Workflow

1. **Audit** structural health (broken `[[links]]`, orphans, frontmatter):
   ```bash
   wiki lint           # structural
   wiki lint --all     # also semantic checks via the LLM
   ```
2. **Propose fixes** as a change request:
   ```bash
   wiki maintain       # lint + propose fixes as a CR
   ```
3. **Review and apply** the proposed fixes:
   ```bash
   wiki review <cr-id>
   wiki apply <cr-id>
   ```
4. Rebuild the index/metadata when needed:
   ```bash
   wiki index
   ```

## Guardrails

- All fixes go through the CR flow (review + apply) — no direct writes.
- `wiki/index.md` and `wiki/log.md` are generated artifacts.
- Treat the brain as the source of truth; resolve contradictions explicitly
  rather than silently overwriting.
