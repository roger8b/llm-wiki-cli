# Agent evals baseline

First reproducible quality baseline for the ingestion agent, captured right after
merging the evals harness (Phase 0, issue #175). Re-run `wiki evals run` before and
after each Phase 1–2 prompt/tool change and compare against these numbers.

- **Date:** 2026-06-10
- **Model:** `anthropic:MiniMax-M2.7`
- **Aggregate score:** **79.1 / 100**
- **Tokens (in/out):** 160,872 / 11,728
- **Structured-output fallback:** 4/5 cases (weak tool-calling on this model)

## Per-case results

| Case | Score | Pages (new+edit) | Links resolved | Frontmatter | Fallback | Notes |
|------|------:|:----------------:|:--------------:|:-----------:|:--------:|-------|
| 01-short-concept | 90.0 | 1+0 | 0/4 | 100% | yes |  |
| 02-rich-multi | 82.7 | 5+0 | 13/17 | 100% | yes | must_link source 'Retrieval-Augmented Generation' not found |
| 03-long | 100.0 | 8+0 | 29/29 | 100% | no |  |
| 04-duplicate | 25.0 | 1+0 | 0/0 | 100% | yes | none of the expected titles were produced; expected an edit  |
| 05-entities | 97.9 | 5+0 | 22/28 | 100% | yes |  |

## What this baseline tells us

- **Semantic dedup is broken** — `04-duplicate` created a *new* duplicate page
  instead of editing the existing one, so the harness hard-caps it at 25. This is
  exactly what the dedup guardrail (issue #167, story 1.7) must fix.
- **Inter-page linkage is weak** — `01` resolves 0/4 wikilinks and `02` fails its
  required `must_link`. Target of the `related_pages` tool + graph-exploration
  prompt (issue #165, story 1.5).
- **Tool-calling fallback is high** on this model (structured-output fallback in
  most cases) — relevant to the per-model comparison report (issue #176, 6.3).
- **Long sources already work well** — `03-long` (>30k chars) scored 100 even
  before multi-pass chunking (issue #162, 1.6).

> Raw run artifacts are written to `evals/results/<timestamp>-<model>.json`
> (git-ignored). This file is the curated, versioned snapshot.
