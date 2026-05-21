# LLM Wiki Agent Protocol

## Goal
Maintain a persistent, interlinked, and auditable Markdown wiki.

## Rules
- Never edit files in `raw/`.
- Always record operations in `wiki/log.md`.
- Always update `wiki/index.md` when creating or changing pages (via `wiki index`).
- Prefer updating existing pages before creating new ones.
- Create internal links with `[[Page Name]]`.
- Every important claim must reference its source.
- Contradictions must be marked explicitly.
- Changes are proposed as change requests (diffs) before being applied.

## Page types
`concept` | `entity` | `source_summary` | `synthesis` | `decision` | `project` | `research`

## Standard frontmatter
`title`, `type`, `tags`, `sources`, `updated_at`, `confidence`
