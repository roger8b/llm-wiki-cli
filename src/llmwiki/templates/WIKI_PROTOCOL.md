# LLM Wiki — operational protocol

The rules that keep this brain trustworthy, auditable, and unambiguous. They
apply to humans and agents alike. `AGENTS.md`/`CLAUDE.md` are the entry points;
this file is the authoritative protocol.

## Goal

Maintain a persistent, interlinked, and **auditable** Markdown knowledge base
that stays the source of truth over time.

## Immutable inputs

- **`raw/` is read-only.** Never edit, move, or delete files in `raw/`. Raw
  material is the evidence; pages cite it. Register new material with
  `wiki source add <file>` (it lands under `raw/`).

## Changes only via change requests (CR)

- **Never write to `wiki/` directly.** Every change to a page — create, update,
  or delete — is proposed as a **change request** (a diff) and only takes effect
  when a human runs `wiki apply`.
- Flow: `wiki ingest <file>` (or `wiki maintain`, `wiki ask --save`) **proposes**
  a CR → `wiki review` shows the diff → `wiki apply <cr>` writes it → `wiki reject`
  discards it (diffs are kept for auditing).
- This guarantees a human is always in the loop and every change is reviewable.

## Generated artifacts (do not hand-edit)

- **`wiki/index.md`** — the map of the wiki. Rebuilt by `wiki index` / on apply.
- **`wiki/log.md`** — the audit log of applied changes. Appended automatically.

Editing these by hand is pointless: the next reindex overwrites `index.md`, and
hand-written log entries break the audit trail.

## Auditability

- The brain is a **git repository**; applied CRs are diffable and revertable.
- Every applied change is recorded in `wiki/log.md`.
- Rejected CRs keep their diffs so the decision history survives.

## Authoring rules

- Prefer **updating an existing page** over creating a near-duplicate.
- Link related pages with `[[Page Title]]`.
- Every important claim **cites its source** (a `raw/` file or another page).
- Mark **contradictions** explicitly rather than silently overwriting.

## Page types

`concept` | `entity` | `source_summary` | `synthesis` | `decision` |
`project` | `research`

## Standard frontmatter

`title`, `type`, `tags`, `sources`, `updated_at`, `confidence`
