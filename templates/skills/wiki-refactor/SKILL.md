---
name: wiki-refactor
description: Restructure the brain without losing knowledge — merge duplicated pages, split overgrown ones, rename slugs, deprecate outdated pages, evolve schemas, normalize links and taxonomy. Use this skill whenever the user says "merge these", "split this page", "rename", "deprecate", "clean up the taxonomy", "the brain is getting messy", or when a lint pass surfaced duplicates or stale structures the user agreed to fix. Use it even for small renames, because rename safely means updating backlinks, index, and log — easy to forget by hand.
---

# Brain — Refactor

## Step 0 — Maintain a todo list (in working memory, not as a file)

Use TodoWrite or your platform's in-memory todo equivalent.

## Mission

The brain is a living codebase. Concepts split, merge, rename, and decay. The whole point of treating it like code is that refactors are safe — backlinks update, history is preserved, deprecations leave breadcrumbs.

You interact with the brain **only through the `wiki` CLI**. Never read or write files inside the brain directly.

The CLI has dedicated commands for the moves that used to require shell tricks:

| Move | Command |
|------|---------|
| Rename a slug (and every backlink) | `wiki page rename <old-slug> "<New Title>"` |
| Remove a deprecated, orphaned page | `wiki page delete <slug>` |
| Reflect an intentional raw edit | `wiki source rehash <id\|path>` |
| Verify all raw hashes vs manifest | `wiki source verify` |
| Stage brain paths and commit | `wiki commit [-m "..."]` |

Prefer these over heredoc + shell; they update backlinks, frontmatter, and manifests in one pass.

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

Always pipe content via stdin (heredoc) — **never write to `/tmp/`**.

**Merge:**
```bash
cat <<'EOF' | wiki page update <survivor-slug>
---
related: [<merged related slugs>]
---

# Survivor Title

(merged body)
EOF

cat <<'EOF' | wiki page update <absorbed-slug> --status deprecated
---
superseded_by: <survivor-slug>
---

# (deprecated) — see <survivor-slug>
EOF
```

**Split:**
```bash
cat <<'EOF' | wiki page save --type <type> --title "<new title>"
---
sources: [...]
related: [<original-slug>]
---

# New Title

(extracted body)
EOF
```

**Rename (slug only or slug + title):**
```bash
wiki page rename <old-slug> "<New Title>"            # rewrites slug + title, updates every backlink
wiki page rename <old-slug> "<New Title>" --keep-title  # rewrites slug only
```

This handles frontmatter (`related`, `sources`, `supersedes`, `superseded_by`) and relative markdown links ending in `<old-slug>.md` across the brain.

**Deprecate:**
```bash
cat <<'EOF' | wiki page update <slug> --status deprecated
---
superseded_by: <replacement-slug>
---

# (deprecated) — see <replacement-slug>

(short deprecation note)
EOF
```

**Delete (only when truly safe):**
```bash
wiki page delete <slug>                              # refuses if status≠deprecated or page has backlinks
wiki page delete <slug> --force                      # skip guards (still prefers deprecation)
```

**Raw file changes:** If you need to edit a registered source file (e.g. fix broken image paths), then run:
```bash
wiki source rehash <id|path>                         # refresh manifest + source page hash
```
Without this, `wiki lint` will flag the drift as an error (raw_is_immutable).

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

### 7. Commit

```bash
wiki commit                          # message defaults to the last log entry
wiki commit -m "refactor: <summary>" # explicit subject when you prefer
```

`wiki commit` stages only brain-managed paths (`wiki/`, `raw/`, `schemas/`, `skills/`, `.wiki/manifests/`, `wiki.config.yaml`, `AGENTS.md`, `WIKI_PROTOCOL.md`) and refuses to commit `raw/` changes when `wiki/log.md` is not also staged (policy: `require_log_entry_for_updates`).

## Guardrails

- **Prefer deprecation over deletion.** Deletion breaks citations; `wiki page delete` enforces this by default (refuses on non-deprecated pages or pages with backlinks).
- **Preserve every raw source reference.** If you can't see where a source should live in the new structure, the structure is wrong.
- **Do not rewrite canonical decisions silently.** If a refactor changes meaning, that's a new decision (use `wiki-decision-capture`), not a refactor.
- **After every change** the brain should still pass `wiki doctor` and `wiki lint`. Finish the job before stopping.
- **Never write files in the brain directly.** Use `wiki page save` / `wiki page update` / `wiki page rename` / `wiki page delete`. For raw edits, follow with `wiki source rehash`.
- **Never invent CLI commands.** Run `wiki --help` if unsure.

## Done criteria

- No source references lost
- `wiki links check` clean
- No orphaned canonical pages
- `wiki index rebuild` ran
- `wiki log add` entry present
- Old slugs resolve as deprecated stubs (citations still work)
