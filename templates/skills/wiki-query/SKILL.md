---
name: wiki-query
description: Answer a user question using the brain as the source of truth, then save durable conclusions back so the brain compounds. Use this skill whenever the user asks a substantive question that the brain might already cover (concepts, decisions, comparisons, prior research) — not only when they explicitly say "search the brain". Also use it when the user asks for a summary, comparison, synthesis, or analysis that could plausibly be reused later — the natural next step is to file the result so the work does not vanish into chat.
---

# Brain — Query

## Step 0 — Maintain a todo list (in working memory, not as a file)

Before any tool call, create an internal todo list (TodoWrite tool or equivalent) and tick items off. **Never persist the todo list as a file.**

```
[ ] 1. wiki query prepare + wiki query context
[ ] 2. Orient with wiki protocol / wiki index show
[ ] 3. List candidate pages by status and type
[ ] 4. Read evidence via wiki page show / wiki source show
[ ] 5. Compose grounded answer with slug citations
[ ] 6. If durable: pipe content to wiki page save via stdin
[ ] 7. wiki index rebuild
```

## Mission

A query is a chance to (a) give a grounded answer, and (b) deposit a new artifact in the brain. The second part is what makes the brain compound. Without it, each question costs the same to answer next time.

You interact with the brain **only through the `wiki` CLI**. Never read or write files inside the brain directly.

## Workflow

### 1. Prepare query context (optional but useful)

```bash
wiki query prepare "<the question>"
wiki query context             # read the candidate pages the CLI surfaced
```

The context lists relevant pages, related decisions, and nearby open questions.

### 2. Orient

```bash
wiki protocol                  # if unfamiliar with the brain's rules
wiki index show                # what exists, grouped by type
```

### 3. Select pages by priority

```bash
wiki page list --status canonical
wiki page list --status reviewed
wiki search "<topic>"          # keyword search across all pages
wiki page list --type decision # decisions related to the topic
```

Priority order when sources disagree:

1. User's current instruction
2. Pages with status `canonical` (especially decisions)
3. Pages with status `reviewed`
4. Raw sources (`wiki source show <id>`)
5. Pages with status `draft`
6. Your own inference, labeled

### 4. Read evidence

```bash
wiki page show <slug>
wiki source show <id>          # drop into raw evidence when a claim is shaky
```

### 5. Answer

Ground every assertion in a page or source. Cite by slug. Separate facts from inference and label inference explicitly. Disclose gaps — that signals what to ingest next.

### 6. Persist durable knowledge

If the answer is useful to a future reader, save it via the right page type. **Compose content in memory and pipe via stdin — never write to `/tmp/`:**

```bash
cat <<'EOF' | wiki page save --type synthesis --title "<title>"
---
sources: [<bare slugs you cited>]
related: [<bare slugs of related concepts>]
tags: [...]
---

# <title>

(answer body)
EOF
```

Page types: `synthesis` (multi-source analysis), `comparison`, `playbook`, `open-question`, `decision` (use `wiki-decision-capture` skill for the full decision workflow).

The CLI validates refs at save time — all slugs in `sources[]` and `related[]` must exist (run `wiki page list` to confirm) and must not be path-form.

### 7. Refresh the index

```bash
wiki index rebuild
```

## Guardrails

- **Do not answer from memory** when the brain likely covers it. Re-read via `wiki page show`.
- **Do not overrule a canonical page** without explicitly flagging the conflict in your answer.
- **Do not synthesize a "conclusion" from a single weak source.** Mark it as inference or open question.
- **Do not mix fact and opinion without labels.** Readers (human or agent) trust the brain because of this discipline.
- **Never write files in the brain directly.** Use `wiki query save` or `wiki page save`.
- **Never invent CLI commands.** Run `wiki --help` if uncertain.

## Done criteria

- Relevant pages were read via CLI
- Answer is grounded with explicit citations (by slug)
- Uncertainty is labeled
- Durable conclusions were saved or proposed for saving
