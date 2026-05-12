---
name: wiki-lint
description: Audit the brain for structural and knowledge-quality issues — missing frontmatter, broken links, orphan pages, uncited canonical claims, duplicated concepts, stale entries, contradictions between pages. Use this skill whenever the user asks to "lint", "audit", "check", or "clean up" the brain, after a batch of ingests, before sharing or releasing the brain, or when the user has not run a check in a while and is about to make canonical decisions. Pair with the `wiki lint` command, which does the deterministic checks; this skill covers the judgment calls the CLI cannot.
---

# Brain — Lint

## Mission

Linting protects the brain's reliability over time. The structural parts (frontmatter, links, orphans) are mechanical and the CLI handles them. The valuable part is judgment: which concepts are duplicates, which pages contradict, which `reviewed` claims actually lack evidence, which sources are stale.

You interact with the brain **only through the `wiki` CLI**.

## Workflow

### 1. Run the mechanical checks

```bash
wiki lint                          # frontmatter, broken links, duplicates, orphans
wiki links check                   # broken internal links
wiki doctor                        # structural sanity
```

Read the CLI output carefully before doing any judgment work.

### 2. Structural review (cross-check)

Even with the CLI output, scan for:

```bash
wiki page list                                       # see all pages with type/status
wiki page list --status reviewed                     # focus on reviewed pages
wiki page list --status canonical                    # and canonical
```

For each suspicious page:

```bash
wiki page show <slug>                                # inspect frontmatter
```

Watch for: invalid `type` or `status`, pages whose type doesn't match what they discuss.

### 3. Navigation review

```bash
wiki index show
```

Look for: pages not in the index, near-duplicate concepts under different slugs (e.g. `rag` vs `retrieval-augmented-generation`).

### 4. Evidence review

For each `reviewed` or `canonical` page, check that the `sources` field is non-empty and that each cited source resolves:

```bash
wiki page show <slug>                                # check sources field
wiki source list                                     # confirm sources exist
wiki source show <id>                                # spot-check evidence
```

### 5. Freshness review

Look for pages with old `updated_at` values, especially in fast-moving topics. Deprecated pages still linked from active pages without a "see X" pointer. Decisions superseded but not marked with `superseded_by`.

### 6. Contradiction review

This is the hardest and most valuable part. Read related pages side by side:

```bash
wiki search "<concept>"                              # find all mentions
wiki page show <slug-a>
wiki page show <slug-b>
```

Look for: conflicting definitions, decisions that disagree on scope, source pages whose claims weren't propagated to concept pages.

### 7. Produce a health report

Compose the report as a synthesis page (group findings by severity: critical, error, warning, info):

```bash
wiki page save --type synthesis \
  --title "Brain health report — YYYY-MM-DD" \
  --file /tmp/lint-report.md
```

For each finding include: affected slugs, what's wrong, suggested fix. Concrete is better than abstract.

### 8. Log the lint pass

```bash
wiki log add --type lint \
  --message "Health check: <counts by severity> — report: brain-health-report-YYYY-MM-DD"
```

## Guardrails

- **Do not auto-fix critical issues.** They imply a source-of-truth conflict and need the user's call.
- **Do not delete pages even if orphaned.** Deprecate or merge via the `wiki-refactor` skill.
- **Do not file a clean report if you skipped the contradiction review** — that is where the real value is.
- **Never write files in the brain directly.** Use `wiki page save` for the report.
- **Never invent CLI commands.** Run `wiki --help` if unsure.

## Done criteria

- `wiki lint`, `wiki links check`, `wiki doctor` ran
- Judgment-level checks (duplicates, contradictions, evidence gaps) were performed via `wiki page show` / `wiki search`
- A health report synthesis page exists
- The log has the lint entry
- Critical issues are surfaced clearly, separate from cosmetic ones
