---
name: wiki-refactor
description: Restructure the brain without losing knowledge — merge duplicated pages, split overgrown ones, rename slugs, deprecate outdated pages, evolve schemas, normalize links and taxonomy. Use this skill whenever the user says "merge these", "split this page", "rename", "deprecate", "clean up the taxonomy", "the brain is getting messy", or when a lint pass surfaced duplicates or stale structures the user agreed to fix. Use it even for small renames, because rename safely means updating backlinks, index, and log — easy to forget by hand.
---

# Brain — Refactor

## Mission

The brain is a living codebase. Concepts split, merge, rename, and decay. The whole point of treating it like code is that refactors are safe — backlinks update, history is preserved, deprecations leave breadcrumbs.

You interact with the brain **only through the `wiki` CLI**. Never read or write files inside the brain directly.

## When to use

- Two pages are near-duplicates and should merge
- A page has outgrown itself and should split
- A slug or title is misleading and should be renamed
- A concept has been superseded and should be deprecated (not deleted)
- The taxonomy needs reorganizing
- A schema gained or lost a field and existing pages need migration

## Workflow

### 1. Identify and scope

State, in writing, what you are changing and why:
- the issue;
- affected slugs (read them all);
- desired end state;
- risk level (low if cosmetic, high if touching canonical pages).

Share this with the user before touching pages if the risk is non-trivial.

```bash
wiki page list --type <type>
wiki page show <slug>                  # for each affected page
wiki search "<term>"                   # find references
```

### 2. Preserve knowledge

For every affected page collect:
- unique claims (anything not duplicated elsewhere);
- source references (which raw sources and which pages are cited);
- inbound links (`wiki links check` + `wiki search <slug>`);
- outbound links.

A refactor that loses any of these is a regression — even if the result is "cleaner".

### 3. Propose a refactor plan

Write a short plan listing pages to create, update, deprecate, and links to rewrite. Share it with the user.

### 4. Apply the changes via CLI

**Merge:**
```bash
# move unique content into the survivor
wiki page update <survivor-slug> --file /tmp/merged.md

# leave the absorbed page as a deprecated stub pointing to the survivor
wiki page update <absorbed-slug> --status deprecated --file /tmp/stub.md
```

**Split:**
```bash
wiki page save --type <type> --title "<new title>" --file /tmp/new-page.md

# update the original to contain only an index + see-pointers
wiki page update <original-slug> --file /tmp/index-pointer.md
```

**Rename:**
```bash
# create new page (use the new title)
wiki page save --type <type> --title "<new title>" --file /tmp/content.md

# deprecate the old slug with a superseded_by pointer
wiki page update <old-slug> --status deprecated --file /tmp/stub.md
```

**Deprecate:**
```bash
wiki page update <slug> --status deprecated --file /tmp/with-deprecation-note.md
```

**Schema evolution:** migrate one page at a time. After each:
```bash
wiki lint
```

### 5. Update navigation

```bash
wiki index rebuild
wiki links check                       # confirm no broken links
```

### 6. Log the refactor

```bash
wiki log add --type refactor \
  --message "<summary> — before: <old slugs>; after: <new slugs>; backlinks updated"
```

## Guardrails

- **Prefer deprecation over deletion.** Deletion breaks citations; deprecation preserves them.
- **Preserve every raw source reference.** If you can't see where a source should live in the new structure, the structure is wrong.
- **Do not rewrite canonical decisions silently.** If a refactor changes meaning, that's a new decision (use `wiki-decision-capture`), not a refactor.
- **After every change** the brain should still pass `wiki doctor` and `wiki lint`. Finish the job before stopping.
- **Never write files in the brain directly.** Use `wiki page save` / `wiki page update`.
- **Never invent CLI commands.** Run `wiki --help` if unsure.

## Done criteria

- No source references lost
- `wiki links check` clean
- No orphaned canonical pages
- `wiki index rebuild` ran
- `wiki log add` entry present
- Old slugs resolve as deprecated stubs (citations still work)
