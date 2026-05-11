# Global LLM Wiki — Agent Instructions

This repository is the user's global source of truth.

## Mandatory startup

Before working with this repository:

1. Read `WIKI_PROTOCOL.md`.
2. Read `wiki/index.md`.
3. Use the relevant skill from `skills/`.

## Available skills

- `skills/wiki-source-of-truth.md`
- `skills/wiki-ingest.md`
- `skills/wiki-query.md`
- `skills/wiki-lint.md`
- `skills/wiki-refactor.md`
- `skills/wiki-decision-capture.md`

## Source of truth rule

Persistent knowledge must be stored in the wiki, not only in chat history.

## Raw source rule

Files under `raw/` are immutable.

Agents may read them but must not modify them.

## Wiki update rule

When creating or updating wiki pages:

1. Use the proper schema from `schemas/`.
2. Add valid frontmatter.
3. Add source references.
4. Update `wiki/index.md`.
5. Append to `wiki/log.md`.

## Conflict rule

When new information conflicts with existing information:

1. Do not silently overwrite.
2. Flag the contradiction.
3. Add a note to the affected page.
4. Create or update an open question if needed.
5. Prefer reviewed/canonical decisions until replaced.

## Durable output rule

If a conversation produces reusable knowledge, save it or suggest saving it into one of:

- `wiki/synthesis/`
- `wiki/comparisons/`
- `wiki/playbooks/`
- `wiki/decisions/`
- `wiki/open-questions/`

## Source priority

1. Current user instruction.
2. `wiki/decisions/` with status `canonical` or `reviewed`.
3. Raw sources under `raw/`.
4. Wiki pages with status `canonical`.
5. Wiki pages with status `reviewed`.
6. Wiki pages with status `draft`.
7. Agent inference, clearly labeled.
