---
name: wiki-decision-capture
description: Persist decisions the user makes during conversation as durable `wiki/decisions/` pages — architectural choices, accepted trade-offs, rejected alternatives, operational rules. Use this skill whenever the user picks an approach, settles a debate, says "let's go with X", "we're not doing Y", "from now on", or commits to a non-trivial rule. Use it even when the user does not explicitly say "save this" — decisions that stay in chat get lost, and the wiki's point is to remember them. Pair with `llm-wiki page new decision "<title>"` if you want the CLI to scaffold the page.
---

# Wiki Decision Capture

## Mission

A decision page is not a summary of a debate. It records: what was decided, why, what alternatives were rejected and on what grounds, and what consequences follow. Future readers (you, the user, other agents) consult it instead of re-litigating. If you ingest a great article and update concept pages but skip writing the decisions that came from the discussion, the most valuable output of the session is the part you didn't save.

## When to use

- the user chooses between options ("let's use Postgres", "we'll skip the cache layer");
- an architecture is settled;
- an operational rule is added or changed;
- a previously-considered alternative is explicitly rejected;
- an important trade-off is acknowledged ("we accept lower throughput for clearer code");
- the user reverses a prior decision (now `supersedes` matters).

If you find yourself thinking "this might be worth saving" — it is.

## Workflow

### 1. Identify the decision and its scope

State, in one sentence, what was decided. If you cannot, no decision was actually made — drop it.

### 2. Use the schema

Read `schemas/decision.schema.md`. Create the page at `wiki/decisions/<slug>.md`. You can scaffold with:

```
llm-wiki page new decision "<title>"
```

### 3. Fill the page

The schema's sections matter. Don't skip them.

- **Decision** — one paragraph, the rule.
- **Context** — what problem prompted this, what state preceded.
- **Options considered** — list every real alternative, not strawmen.
- **Rationale** — why this option, in the user's own framing where possible.
- **Consequences** — what changes downstream (other pages to update, behaviors to expect).
- **Risks** — what could go wrong, what would force a revisit.
- **Follow-up actions** — concrete next steps (often: "update X page", "write Y playbook").
- **Evidence** — citations to `raw/` files, prior wiki pages, or external sources.

### 4. Set status carefully

Default to `status: draft`. The user promotes to `reviewed` or `canonical` — that's their call. If this decision supersedes another, set `supersedes: [<old slug>]` and update the old page's `superseded_by`.

### 5. Cross-link

- Add the new decision to the `related` field of every page it affects.
- Update affected concept/workflow/playbook pages to reference the decision ("**Decision:** see `wiki/decisions/<slug>.md`").

### 6. Index and log

Run `llm-wiki index rebuild` (or update `wiki/index.md` by hand). Append to `wiki/log.md`:

```
## [YYYY-MM-DD] decision | <title>
- file: wiki/decisions/<slug>.md
- supersedes: <prior slug or none>
- affected pages: ...
```

## Guardrails

- Do not record decisions that were not actually made. If the user is still weighing options, write an `wiki/open-questions/` page instead.
- Always include rationale. A decision without reasoning is unrevisable.
- Always list rejected alternatives. They are how future-you knows whether to reopen the decision.
- Mark `supersedes` / `superseded_by` whenever a new decision changes a prior one. Silent overwrites destroy the audit trail.

## Done criteria

- A page exists at `wiki/decisions/<slug>.md` with valid frontmatter and complete sections.
- Rationale and rejected alternatives are explicit.
- Related pages have backlinks.
- `supersedes` / `superseded_by` set if applicable.
- Index and log updated.
