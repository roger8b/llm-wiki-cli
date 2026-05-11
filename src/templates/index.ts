export const CONFIG_YAML = `name: llm-global-wiki
version: 0.1.0

paths:
  raw: raw
  wiki: wiki
  schemas: schemas
  skills: skills
  cache: .wiki/cache
  reports: .wiki/reports
  manifests: .wiki/manifests
  temp: .wiki/temp

required_files:
  - AGENTS.md
  - WIKI_PROTOCOL.md
  - wiki/index.md
  - wiki/log.md

page_types:
  - source
  - concept
  - entity
  - project
  - agent
  - workflow
  - decision
  - playbook
  - comparison
  - synthesis
  - open-question
  - glossary
  - lint-report

statuses:
  - draft
  - reviewed
  - canonical
  - deprecated
  - conflicting
  - needs-source
  - needs-review

source_policy:
  raw_is_immutable: true
  require_source_for_canonical: true
  require_source_for_reviewed: true
  require_log_entry_for_updates: true

index:
  group_by: type
  include_status: true
  include_updated_at: true
  include_summary: true

lint:
  stale_after_days: 90
  require_frontmatter: true
  require_sources_for_reviewed: true
  require_sources_for_canonical: true
  check_broken_links: true
  check_orphans: true
  check_duplicate_slugs: true

search:
  default_engine: ripgrep
`;

export const AGENTS_MD = `# Global LLM Wiki — Agent Instructions

This repository is the user's global source of truth.

## Mandatory startup

1. Read \`WIKI_PROTOCOL.md\`.
2. Read \`wiki/index.md\`.
3. Use the relevant skill from \`skills/\`.

## Source of truth rule

Persistent knowledge must be stored in the wiki, not only in chat history.

## Raw source rule

Files under \`raw/\` are immutable. Agents may read them but must not modify them.

## Wiki update rule

1. Use the proper schema from \`schemas/\`.
2. Add valid frontmatter.
3. Add source references.
4. Update \`wiki/index.md\`.
5. Append to \`wiki/log.md\`.
`;

export const PROTOCOL_MD = `# Wiki Protocol

This repository is a persistent, compounding knowledge base maintained by LLM agents.

## Layers

- \`raw/\` — immutable evidence
- \`wiki/\` — synthesized knowledge
- \`schemas/\` — page templates
- \`skills/\` — agent operating skills

## Operations

ingest | query | lint | refactor

## Frontmatter required

\`type\`, \`title\`, \`slug\`, \`status\`, \`created_at\`, \`updated_at\`.
`;

export const INDEX_MD = `# Wiki Index

Auto-managed catalog. Rebuild with \`llm-wiki index rebuild\`.

## sources

_(empty)_

## concepts

_(empty)_
`;

export function logSeed(date: string): string {
  return `# Wiki Log

## [${date}] init | wiki bootstrap
- files: AGENTS.md, WIKI_PROTOCOL.md, wiki.config.yaml
- notes: initial scaffold created by llm-wiki init
`;
}

export const GITIGNORE = `.wiki/cache/
.wiki/temp/
.wiki/reports/
.DS_Store
*.swp
node_modules/
`;

export const SCHEMAS: Record<string, string> = {
  "concept.schema.md": `---
type: concept
title: ""
slug: ""
status: draft
confidence: medium
created_at: YYYY-MM-DD
updated_at: YYYY-MM-DD
sources: []
related: []
tags: []
---

# {{title}}

## Definition

## Why it matters

## How it works

## Related concepts

## Evidence

## Examples

## Open questions

## Change history
`,
  "source.schema.md": `---
type: source
title: ""
slug: ""
status: reviewed
confidence: high
created_at: YYYY-MM-DD
updated_at: YYYY-MM-DD
raw_path: ""
source_type: article
source_hash: ""
authors: []
published_at: null
ingested_at: YYYY-MM-DD
related: []
tags: []
---

# {{title}}

## Source metadata

## Executive summary

## Key claims

## Extracted concepts

## Entities mentioned

## Decisions or implications

## Contradictions or tensions

## Pages created

## Pages updated

## Open questions
`,
  "decision.schema.md": `---
type: decision
title: ""
slug: ""
status: draft
confidence: medium
created_at: YYYY-MM-DD
updated_at: YYYY-MM-DD
decision_date: YYYY-MM-DD
decision_owner: ""
sources: []
related: []
tags: []
supersedes: []
superseded_by: []
---

# {{title}}

## Decision

## Context

## Options considered

## Rationale

## Consequences

## Risks

## Follow-up actions

## Evidence

## Change history
`,
  "agent.schema.md": `---
type: agent
title: ""
slug: ""
status: draft
confidence: medium
created_at: YYYY-MM-DD
updated_at: YYYY-MM-DD
sources: []
related: []
tags: []
---

# {{title}}

## Purpose

## When to use

## Inputs

## Outputs

## Responsibilities

## Operating rules

## Skills used

## Quality gates

## Failure modes

## Related workflows

## Change history
`,
  "workflow.schema.md": `---
type: workflow
title: ""
slug: ""
status: draft
confidence: medium
created_at: YYYY-MM-DD
updated_at: YYYY-MM-DD
sources: []
related: []
tags: []
---

# {{title}}

## Purpose

## Trigger

## Inputs

## Steps

## Outputs

## Agents involved

## Skills involved

## Quality gates

## Error handling

## Logging requirements

## Change history
`,
  "synthesis.schema.md": `---
type: synthesis
title: ""
slug: ""
status: draft
confidence: medium
created_at: YYYY-MM-DD
updated_at: YYYY-MM-DD
sources: []
related: []
tags: []
---

# {{title}}

## Executive summary

## Context

## Main synthesis

## Supporting evidence

## Implications

## Risks and limitations

## Related pages

## Open questions

## Change history
`,
  "comparison.schema.md": `---
type: comparison
title: ""
slug: ""
status: draft
confidence: medium
created_at: YYYY-MM-DD
updated_at: YYYY-MM-DD
sources: []
related: []
tags: []
---

# {{title}}

## Subjects compared

## Criteria

## Comparison table

## Analysis

## Recommendation

## Evidence

## Change history
`,
  "playbook.schema.md": `---
type: playbook
title: ""
slug: ""
status: draft
confidence: medium
created_at: YYYY-MM-DD
updated_at: YYYY-MM-DD
sources: []
related: []
tags: []
---

# {{title}}

## Purpose

## When to use

## Prerequisites

## Steps

## Checks

## Pitfalls

## Related pages

## Change history
`,
  "open-question.schema.md": `---
type: open-question
title: ""
slug: ""
status: draft
confidence: low
created_at: YYYY-MM-DD
updated_at: YYYY-MM-DD
sources: []
related: []
tags: []
---

# {{title}}

## Question

## Why it matters

## What is known

## What is missing

## Hypotheses

## Next steps

## Change history
`,
  "lint-report.schema.md": `---
type: lint-report
title: ""
slug: ""
status: draft
created_at: YYYY-MM-DD
updated_at: YYYY-MM-DD
---

# {{title}}

## Summary

## Findings

## Recommended fixes
`,
};

export const SKILLS: Record<string, string> = {
  "wiki-source-of-truth.md": `---
name: wiki-source-of-truth
description: Use this skill when treating the Global LLM Wiki as the source of truth.
---

# Wiki Source of Truth

Read WIKI_PROTOCOL.md and wiki/index.md before answering. Prefer canonical/reviewed pages. Do not invent. Persist durable knowledge.
`,
  "wiki-ingest.md": `---
name: wiki-ingest
description: Use this skill to incorporate a new raw source into the wiki.
---

# Wiki Ingest

Read source, create wiki/sources/<slug>.md, update related pages, update index.md, append log.md. Flag contradictions. Never edit raw/.
`,
  "wiki-query.md": `---
name: wiki-query
description: Use this skill to answer questions using the wiki.
---

# Wiki Query

Read index, select pages, ground answer in wiki, cite sources, persist durable conclusions to wiki/synthesis/ or wiki/comparisons/.
`,
  "wiki-lint.md": `---
name: wiki-lint
description: Use this skill to audit wiki health.
---

# Wiki Lint

Check structure, frontmatter, links, orphans, missing sources, stale pages, contradictions. Produce report under wiki/synthesis/ or .wiki/reports/.
`,
  "wiki-refactor.md": `---
name: wiki-refactor
description: Use this skill to restructure the wiki without losing knowledge.
---

# Wiki Refactor

Merge, split, rename, deprecate. Preserve sources and backlinks. Prefer deprecation over deletion.
`,
  "wiki-decision-capture.md": `---
name: wiki-decision-capture
description: Use this skill to capture durable decisions during conversation.
---

# Wiki Decision Capture

Write to wiki/decisions/<slug>.md using schemas/decision.schema.md. Include rationale and trade-offs.
`,
};

export const WIKI_SUBDIRS = [
  "concepts",
  "entities",
  "projects",
  "agents",
  "workflows",
  "decisions",
  "playbooks",
  "comparisons",
  "synthesis",
  "sources",
  "open-questions",
  "glossary",
];

export const RAW_SUBDIRS = [
  "articles",
  "books",
  "documents",
  "transcripts",
  "specs",
  "images",
  "external",
];
