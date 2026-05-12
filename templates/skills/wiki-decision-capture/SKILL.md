---
name: wiki-decision-capture
description: Persist decisions the user makes during conversation as durable decision pages — architectural choices, accepted trade-offs, rejected alternatives, operational rules. Use this skill whenever the user picks an approach, settles a debate, says "let's go with X", "we're not doing Y", "from now on", or commits to a non-trivial rule. Use it even when the user does not explicitly say "save this" — decisions that stay in chat get lost, and the brain exists to remember them.
---

# Brain — Decision Capture

## Step 0 — Maintain a todo list (in working memory)

Use TodoWrite (or your platform's equivalent in-memory todo) — never write the list as a file.

## Mission

A decision page is not a summary of a debate. It records: what was decided, why, what alternatives were rejected and on what grounds, and what consequences follow. Future readers consult it instead of re-litigating. If you ingest a great article and update concept pages but skip writing the decisions that came from the discussion, the most valuable output of the session is the part you didn't save.

You interact with the brain **only through the `wiki` CLI**. Never read or write files inside the brain directly.

## When to use

- The user chooses between options ("let's use Postgres", "we'll skip the cache layer")
- An architecture is settled
- An operational rule is added or changed
- A previously-considered alternative is explicitly rejected
- An important trade-off is acknowledged ("we accept lower throughput for clearer code")
- The user reverses a prior decision (now `supersedes` matters)

If you find yourself thinking "this might be worth saving" — it is.

## Workflow

### 1. Identify the decision

State, in one sentence, what was decided. If you cannot, no decision was actually made — drop it.

### 2. Read the schema

```bash
wiki schema show decision
```

This tells you the required sections: Decision, Context, Options considered, Rationale, Consequences, Risks, Follow-up actions, Evidence.

### 3. Check for related decisions and pages

```bash
wiki search "<topic>"
wiki page list --type decision
wiki page show <slug>                   # read prior decisions this might supersede
```

### 4. Compose the page

Fill every section. Defaults to `status: draft` — the user promotes to `reviewed` or `canonical`.

- **Decision** — one paragraph, the rule
- **Context** — what problem prompted this, what state preceded
- **Options considered** — every real alternative, not strawmen
- **Rationale** — why this option, in the user's own framing where possible
- **Consequences** — what changes downstream
- **Risks** — what could go wrong, what would force a revisit
- **Follow-up actions** — concrete next steps
- **Evidence** — citations to raw sources or prior pages (by slug)

### 5. Save the page

Compose in memory, pipe via stdin — **no `/tmp/` files**:

```bash
cat <<'EOF' | wiki page save --type decision --title "<title>"
---
status: draft
sources: [<bare slugs of evidence sources>]
related: [<bare slugs of affected pages>]
supersedes: [<bare slug of decision being replaced, or omit>]
tags: [...]
---

# <title>

## Decision
...
## Context
...
## Options considered
...
(rest of schema sections)
EOF
```

The CLI validates `sources[]` and `related[]` against existing slugs at save time.

### 6. Mark supersession (if applicable)

If this decision supersedes another, the `supersedes` field in step 5 handles the forward link. Now deprecate the old page:

```bash
cat <<'EOF' | wiki page update <old-slug> --status deprecated
---
superseded_by: <new-slug>
---
EOF
```

### 7. Cross-link affected pages

For every page this decision affects (use bare slugs only):

```bash
cat <<'EOF' | wiki page update <affected-slug>
---
related: [<existing related slugs>, <new-decision-slug>]
---
EOF
```

### 8. Refresh index and log

```bash
wiki index rebuild
wiki log add --type decision \
  --message "<title> — supersedes: <slug-or-none>; affected: <slugs>"
```

## Guardrails

- **Do not record decisions that were not actually made.** If the user is still weighing options, save an `open-question` instead (`wiki page save --type open-question …`).
- **Always include rationale.** A decision without reasoning is unrevisable.
- **Always list rejected alternatives.** They are how future-you knows whether to reopen the decision.
- **Mark supersession.** Silent overwrites destroy the audit trail.
- **Never write files in the brain directly.** Use `wiki page save` / `wiki page update`.
- **Never invent CLI commands.** Run `wiki --help` if unsure.

## Done criteria

- A decision page exists with all required sections (verify with `wiki page show <slug>`)
- Rationale and rejected alternatives are explicit
- Related pages have backlinks
- `supersedes` / `superseded_by` set when applicable
- `wiki index rebuild` and `wiki log add` ran
