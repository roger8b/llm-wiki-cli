---
name: wiki-lint
description: Audit the Global LLM Wiki for structural and knowledge-quality issues — missing frontmatter, broken links, orphan pages, uncited canonical claims, duplicated concepts, stale entries, contradictions between pages. Use this skill whenever the user asks to "lint", "audit", "check", or "clean up" the wiki, after a batch of ingests, before sharing or releasing a wiki, or when the user has not run a check in a while and is about to make canonical decisions. Pair with the `llm-wiki lint` CLI command, which does the deterministic checks; this skill covers the judgment calls the CLI can't.
---

# Wiki Lint

## Mission

Linting protects the wiki's reliability over time. The structural parts (frontmatter, links, orphans) are mechanical and the CLI handles them. The valuable part is judgment: which concepts are duplicates, which pages contradict, which "reviewed" claims actually lack evidence, which sources are stale.

## Workflow

### 1. Run the mechanical checks first

```
llm-wiki lint
```

This produces `.wiki/reports/lint-report-<date>.md` with frontmatter validation, broken-link detection, duplicate-slug detection, pending-source flags, and missing-from-index findings. Read it before doing anything judgmental.

### 2. Structural review (cross-check)

Even with the CLI output, scan the wiki for:

- pages missing required frontmatter fields (`type`, `title`, `slug`, `status`, `created_at`, `updated_at`);
- invalid `type` or `status` values;
- pages in the wrong directory for their type.

### 3. Navigation review

- pages not listed in `wiki/index.md`;
- pages with no inbound links (orphans);
- broken internal links;
- near-duplicate concepts under different slugs (e.g., `rag.md` and `retrieval-augmented-generation.md`).

### 4. Evidence review

- `reviewed` or `canonical` pages with empty `sources` arrays;
- pages citing raw files that no longer exist;
- claims phrased as fact but with no source link.

### 5. Freshness review

- pages older than `lint.stale_after_days` (default 90) with high-traffic topics;
- `deprecated` pages still linked from active pages without a "see X" pointer;
- decisions superseded but not marked with `superseded_by`.

### 6. Contradiction review

This is the hardest and most valuable part. Compare related pages:

- conflicting definitions of the same concept;
- decisions that disagree on scope or terminology;
- source pages whose key claims weren't propagated into the concept pages.

### 7. Produce a lint report page

Save under `wiki/synthesis/wiki-health-report-YYYY-MM-DD.md` using `schemas/lint-report.schema.md`. Group findings by severity:

- `critical` — source-of-truth conflict (canonical pages disagreeing);
- `error` — broken structure (missing required field, invalid type, broken link to important page);
- `warning` — quality issue (orphan page, uncited reviewed claim, near-duplicate);
- `info` — improvement suggestion (stale page, missing tag, sparse summary).

For each finding, include: affected files, what's wrong, suggested fix. Concrete is better than abstract — name the file and the line if you can.

### 8. Log the lint pass

Append to `wiki/log.md`:

```
## [YYYY-MM-DD] lint | wiki health check
- findings: <counts by severity>
- report: wiki/synthesis/wiki-health-report-YYYY-MM-DD.md
```

## Guardrails

- Do not auto-fix critical issues. They imply a source-of-truth conflict and need the user's call.
- Do not delete pages even if orphaned. Deprecate or merge via the `wiki-refactor` skill.
- Do not file a clean report if you skipped the contradiction review — that's where the real value is.

## Done criteria

- The CLI lint ran and the report was read.
- Judgment-level checks (duplicates, contradictions, evidence gaps) were done by you.
- A health report page exists under `wiki/synthesis/`.
- The log has the lint entry.
- Critical issues are surfaced clearly, separate from cosmetic ones.
