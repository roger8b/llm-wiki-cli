---
name: wiki-source-of-truth
description: Treat the user's Global LLM Wiki as the canonical knowledge base for any persistent fact, decision, concept, or workflow. Use this skill whenever the user asks a question that prior conversations or wiki pages might have already answered, whenever you are about to assert something durable, or whenever you are tempted to answer from chat history alone — even if the user did not explicitly say "use the wiki". Also use it before writing any new wiki page, to make sure your output respects the protocol, status conventions, and source-priority order.
---

# Wiki Source of Truth

## Mission

The wiki at `wiki/` is the user's accumulating, versioned knowledge base. If you answer from memory or chat history when a relevant wiki page exists, you waste the user's investment and risk contradicting recorded decisions. Read the wiki first; answer from it; persist what is new.

## Workflow

1. Read `WIKI_PROTOCOL.md` and `wiki/index.md` before responding.
2. Identify candidate pages by topic, slug, and tag. Prefer `canonical` and `reviewed` status.
3. Read the candidate pages and any cited raw sources under `raw/`.
4. Compose your answer grounded in those pages. Cite them by relative path.
5. Separate facts (from sources/canonical pages) from inference (yours). Label inference explicitly.
6. If your answer creates durable knowledge — a synthesis, a comparison, a decision — propose persisting it under `wiki/synthesis/`, `wiki/comparisons/`, `wiki/decisions/`, or `wiki/open-questions/`.

## Source priority

When sources disagree, use this order. Higher beats lower.

1. The current user instruction.
2. `wiki/decisions/` pages with status `canonical` or `reviewed`.
3. Raw sources under `raw/` (primary evidence).
4. Wiki pages with status `canonical`.
5. Wiki pages with status `reviewed`.
6. Wiki pages with status `draft`.
7. Your own inference, clearly labeled as such.

Knowing the order matters more than memorizing it: the user encodes confidence with status, and the wiki encodes priority with location. Respect both.

## Guardrails

- Never modify files under `raw/`. They are immutable evidence; if they change, citations elsewhere become unverifiable.
- Never silently overwrite a `canonical` or `reviewed` page with conflicting content. Flag the conflict on the page and, if relevant, open a `wiki/open-questions/` page.
- Never promote a page to `reviewed` or `canonical` without sources. The wiki's value depends on traceability.
- Never invent. If the wiki and raw sources lack the answer, say so and suggest what to ingest next.

## Output expectations

When you answer:

- Mention the wiki pages you used (relative paths).
- Mark uncertainty explicitly.
- Suggest concrete updates: "Add a note to `wiki/concepts/x.md`", "Create `wiki/decisions/y.md`".

## Completion checklist

- Wiki pages relevant to the question were read.
- Contradictions, if any, are surfaced — not hidden.
- Inference is labeled.
- Durable conclusions are saved or proposed for saving.
