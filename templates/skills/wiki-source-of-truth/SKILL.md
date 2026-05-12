---
name: wiki-source-of-truth
description: Treat the user's brain as the canonical knowledge base for any persistent fact, decision, concept, or workflow. Use this skill whenever the user asks a question that the brain might already answer, whenever you are about to assert something durable, or whenever you are tempted to answer from chat history alone — even if the user did not explicitly say "use the brain". Also use it before writing any new brain page, to make sure your output respects the protocol, status conventions, and source-priority order.
---

# Brain — Source of Truth

## Mission

The brain is the user's accumulating, versioned knowledge base. If you answer from memory when a relevant page exists, you waste the user's investment and risk contradicting recorded decisions. Read the brain first, answer from it, persist what is new.

You interact with the brain **only through the `wiki` CLI**. Never read or write files inside the brain directly — paths inside the brain are CLI-internal.

## Workflow

### 1. Orient

```bash
wiki protocol         # the brain's rules in full
wiki index show       # what exists, grouped by type
```

### 2. Find candidate pages

```bash
wiki search "<topic>"                         # full-text search
wiki page list --type <type>                  # by type
wiki page list --status canonical             # only authoritative pages
```

### 3. Read evidence

```bash
wiki page show <slug>                         # the page
wiki source show <id-or-name>                 # the raw source it cites
```

### 4. Compose the answer

Ground every assertion in a page or raw source. Cite by slug (e.g., "see decision `postgres-over-mongo`"). Separate facts from your inference — label inference explicitly ("**Inference:** based on …").

### 5. Persist durable conclusions

If the answer is reusable knowledge, save it via the CLI (see the `wiki-query` and `wiki-decision-capture` skills for the right command). Answers that stay in chat get lost.

## Source priority

When sources disagree, higher beats lower:

1. The current user instruction
2. Pages with status `canonical` (especially decisions)
3. Pages with status `reviewed`
4. Raw sources (primary evidence — fetch with `wiki source show`)
5. Pages with status `draft`
6. Your own inference, clearly labeled

Status is how the user encodes confidence. Respect it.

## Guardrails

- **Never write files in the brain directly.** Every write operation has a CLI command. If you don't know which, run `wiki --help`.
- **Never modify raw sources.** They are immutable evidence. The hash backing every citation depends on this.
- **Never silently overwrite canonical or reviewed pages.** Flag the conflict in your answer and propose a new decision or open-question.
- **Never invent answers.** If the brain and its sources lack the answer, say so and suggest what to ingest next.
- **Never invent CLI commands.** Run `wiki --help` if uncertain.

## Done criteria

- Relevant pages were read via `wiki page show` / `wiki source show`
- Contradictions, if any, are surfaced explicitly
- Inference is labeled
- Durable conclusions are saved or proposed for saving via CLI
