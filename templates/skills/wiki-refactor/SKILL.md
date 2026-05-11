---
name: wiki-refactor
description: Restructure the user's Global LLM Wiki without losing knowledge — merge duplicated pages, split overgrown ones, rename slugs, deprecate outdated pages, evolve schemas, normalize links and taxonomy. Use this skill whenever the user says "merge these", "split this page", "rename", "deprecate", "clean up the taxonomy", "the wiki is getting messy", or when a lint pass surfaced duplicates or stale structures the user agreed to fix. Use it even for small renames, because rename safely means updating backlinks, index, and log — easy to forget by hand.
---

# Wiki Refactor

## Mission

The wiki is a living codebase. Concepts split, merge, rename, and decay. The whole point of treating it like code is that refactors are safe — backlinks update, history is preserved, deprecations leave breadcrumbs. This skill enforces that discipline.

## When to use

- two pages are near-duplicates and should merge;
- one page has outgrown itself and should split;
- a slug or title is misleading and should be renamed;
- a concept has been superseded and should be deprecated (not deleted);
- the directory taxonomy needs reorganizing;
- a schema gained or lost a field and existing pages need migration.

## Workflow

### 1. Identify and scope

State, in writing, what you are changing and why. Include:

- the issue;
- affected files (read them all);
- desired end state;
- risk level (low if cosmetic, high if touching canonical pages).

Share this with the user before touching files if the risk is non-trivial.

### 2. Preserve knowledge

For every affected page collect:

- unique claims (especially anything not duplicated elsewhere);
- source references (which `raw/` files and which wiki pages are cited);
- inbound links (run `llm-wiki links check` and grep for the slug);
- outbound links.

A refactor that loses any of these is a regression — even if the result is "cleaner".

### 3. Propose a refactor plan

Write a short plan:

- files to create;
- files to update (with the specific edits);
- files to deprecate;
- links to rewrite;
- index updates;
- log entry.

### 4. Apply the changes

- **Merge:** move unique content into the survivor page, add the absorbed slugs to the survivor's `related` field, leave a stub at the old path with `status: deprecated` and a `see` pointer to the survivor.
- **Split:** create the new pages, move sections, leave the original with a short index + `see` pointers, or deprecate it if fully migrated.
- **Rename:** keep the old path as a deprecated stub with a `superseded_by` pointer; update the new page's `supersedes` field; rewrite inbound links.
- **Deprecate:** flip `status: deprecated`, add a `deprecation note` section explaining what to use instead, keep the page so old links and history still resolve.
- **Schema evolution:** migrate one page at a time, validate each with `llm-wiki page validate`, then rerun `llm-wiki lint`.

### 5. Update navigation

Run `llm-wiki index rebuild`. Then `llm-wiki links check` to confirm no link is broken.

### 6. Log the refactor

Append to `wiki/log.md`:

```
## [YYYY-MM-DD] refactor | <summary>
- before: <old paths>
- after: <new paths>
- backlinks updated: <count>
- notes: <why>
```

## Guardrails

- Prefer deprecation over deletion. Deletion breaks citations and history; deprecation preserves them.
- Preserve every `raw/` reference. If you can't see where it should live in the new structure, the structure is wrong.
- Do not rewrite canonical decisions silently. If a refactor changes meaning, that's a new decision, not a refactor — open `wiki/decisions/`.
- After every change, the wiki should still pass `llm-wiki doctor` and `llm-wiki lint`. If it doesn't, finish the job before stopping.

## Done criteria

- No source references lost.
- No broken links (`llm-wiki links check` clean).
- No orphaned canonical pages.
- Index rebuilt.
- Log entry present.
- Old slugs resolve (via deprecation stubs).
