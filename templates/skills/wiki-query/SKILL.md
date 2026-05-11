---
name: wiki-query
description: Answer a user question using the Global LLM Wiki as the source of truth, then save durable conclusions back into the wiki so they compound. Use this skill whenever the user asks a substantive question that the wiki might already cover (concepts, decisions, comparisons, prior research) — not only when they explicitly say "search the wiki". Also use it when the user asks you to write a summary, comparison, synthesis, or analysis that could plausibly be reused later — the natural next step is to file the result under `wiki/synthesis/` or `wiki/comparisons/` so the work does not vanish into chat.
---

# Wiki Query

## Mission

A query is a chance to (a) give a grounded answer, and (b) deposit a new artifact in the wiki. The second part is what makes the wiki compound. Without it, each question costs the same to answer next time.

## Workflow

### 1. Orient

Read `WIKI_PROTOCOL.md` (briefly) and `wiki/index.md`. If you previously ran `llm-wiki query prepare "<question>"`, read `.wiki/cache/query-context.md` for the candidate pages and excerpts.

### 2. Select pages

Pick pages by relevance, prioritizing in this order:

1. `wiki/decisions/` with status `canonical` or `reviewed`;
2. raw sources under `raw/` when precision matters;
3. wiki pages with status `canonical`;
4. wiki pages with status `reviewed`;
5. wiki pages with status `draft`;
6. open questions adjacent to the topic.

### 3. Read evidence

Read the selected pages. Drop into `raw/` if a claim looks shaky, status is `draft`/`needs-source`, or two pages disagree. The wiki is curated but not omniscient — primary sources are the tiebreaker.

### 4. Answer

Ground every assertion in a page or source. Cite by relative path. Separate facts from inference and label inference clearly ("**Inference:** based on X, …"). Disclose gaps — that signals what to ingest next.

### 5. Persist durable knowledge

If the answer would be useful to a future reader (you, the user, another agent), save it. Pick the right type:

- multi-source analysis → `wiki/synthesis/`
- option/tool comparison → `wiki/comparisons/`
- repeatable procedure → `wiki/playbooks/`
- unresolved question → `wiki/open-questions/`
- a choice made → `wiki/decisions/`

You can hand the user the file and run `llm-wiki query save <file> --as <type> --title "<title>"` to file it correctly.

### 6. Log changes

If you created or modified wiki files, append an entry to `wiki/log.md` with date, operation (`query` or `synthesis`), and the affected files. `llm-wiki query save` does this automatically.

## Guardrails

- Do not answer from memory when the wiki likely contains the answer — re-read.
- Do not overrule a canonical decision without explicitly flagging the conflict.
- Do not synthesize a "conclusion" from a single weak source. Mark it inference or open question.
- Do not mix fact and opinion without labels. Readers (human or agent) trust the wiki because of this discipline.

## Done criteria

- The relevant wiki pages were read.
- Answer is grounded with citations.
- Uncertainty is explicit.
- Durable conclusions were saved or proposed for saving.
- Log was updated if files changed.
