# llm-wiki

CLI for the Global LLM Wiki.

## Install

```bash
cd cli
npm install
npm run build
npm link
```

`llm-wiki` is now available globally.

## Commands

```bash
llm-wiki init [path] [--git] [--force]
llm-wiki doctor
llm-wiki source add <file> --type <type>
llm-wiki source list [--status <status>]
llm-wiki source status <source>
llm-wiki ingest prepare <source>
llm-wiki ingest commit <source>
llm-wiki search <query>
llm-wiki query prepare <question>
llm-wiki query save <file> --as <type> --title <title>
llm-wiki index rebuild
llm-wiki lint
llm-wiki page new <type> <title>
llm-wiki page validate <path>
llm-wiki links check
llm-wiki log add --type <type> --message <message>

# install wiki integration into an external project
llm-wiki project init [path] [--wiki <wiki-root>] [--force]
#   drops .claude/skills/, AGENTS.md, CLAUDE.md, GEMINI.md,
#   .cursor/rules/llm-wiki.mdc, and .llm-wiki.json into the target project.
```

## Wiki root resolution

The CLI looks for `wiki.config.yaml` walking upward from the current directory. Set `LLM_WIKI_ROOT` env var to override.

## Use cases

The wiki is a persistent, agent-maintained knowledge base. The CLI handles bookkeeping; an LLM agent (Claude Code, Codex, Cursor, Gemini) reads sources and writes the wiki via the installed skills.

### 1. Personal knowledge base

Track psychology, health, goals, self-improvement. Drop journal entries, articles, podcast notes into `raw/`; the agent files them, updates entity pages about people in your life, threads themes across entries.

```bash
llm-wiki source add ~/journal/2026-05-11.md --type document
llm-wiki ingest prepare raw/documents/2026-05-11.md
# agent reads .wiki/cache/ingest-context.md and updates wiki pages
llm-wiki ingest commit raw/documents/2026-05-11.md
```

### 2. Deep research over weeks or months

Reading 30 papers on a topic. Each paper becomes a `wiki/sources/` page; recurring concepts become `wiki/concepts/`; the evolving thesis lives in `wiki/synthesis/`. Contradictions surface automatically as new papers contradict old claims.

```bash
llm-wiki source add ./paper-12.pdf --type document
llm-wiki ingest prepare raw/documents/paper-12.pdf
llm-wiki query prepare "Where does this paper disagree with what we have?"
```

### 3. Companion wiki for a book

Read a novel or non-fiction with a wiki growing alongside. Characters → `wiki/entities/`, themes → `wiki/concepts/`, plot threads → `wiki/synthesis/`. By chapter 30 you have your own Tolkien-Gateway-style cross-referenced companion.

```bash
llm-wiki source add ./book/chapter-04.md --type book
llm-wiki ingest prepare raw/books/chapter-04.md
```

### 4. Team / project knowledge base

Slack threads, meeting transcripts, customer calls, design docs all ingested. The wiki keeps current because the LLM (not a human) does the maintenance. Decisions live under `wiki/decisions/`, playbooks under `wiki/playbooks/`, comparisons under `wiki/comparisons/`.

```bash
llm-wiki project init ~/work/my-product --wiki ~/wiki
# now Claude Code inside ~/work/my-product reads the wiki via .claude/skills/
llm-wiki source add ./meetings/2026-05-11-architecture.md --type transcript
```

### 5. Competitive analysis / due diligence

Track competitors over time. Each competitor → `wiki/entities/`, each report → `wiki/sources/`, each cross-comparison → `wiki/comparisons/`. The wiki becomes the durable artifact instead of one-shot decks.

```bash
llm-wiki query prepare "How has Competitor X's pricing strategy evolved over the past year?"
llm-wiki query save ./answer.md --as synthesis --title "Competitor X pricing evolution"
```

### 6. Course notes / hobby deep-dive

Lecture notes, practice problems, references, tutorials accumulate. The wiki cross-links by topic so review covers connections, not isolated pages.

```bash
llm-wiki source add ./lectures/week-05.md --type document
llm-wiki search "fourier transform" --type concept
```

### 7. Decision log for an organization

Architectural choices, hiring rubrics, product principles. `wiki/decisions/` captures the *why* and the rejected alternatives. New decisions can `supersedes` old ones — the audit trail is preserved.

```bash
llm-wiki page new decision "Adopt Postgres over MongoDB for new services"
# agent fills out rationale, options considered, consequences
```

### 8. Trip / event planning

Restaurants, neighborhoods, contacts, itineraries, prior trips. Cumulative across years — useful next time you go.

```bash
llm-wiki source add ./trips/lisbon-2026.md --type document
llm-wiki query prepare "Best ramen places in Lisbon based on what we've collected?"
```

### Common workflow

For all of these, the loop is the same:

1. **Add a source** — `llm-wiki source add <file> --type <type>`
2. **Prepare ingest** — `llm-wiki ingest prepare <raw-path>` writes a context file the agent reads
3. **Agent updates the wiki** — using the `wiki-ingest` skill installed via `llm-wiki project init`
4. **Commit** — `llm-wiki ingest commit <raw-path>` validates and flips status to `ingested`
5. **Query** — `llm-wiki query prepare "<question>"` gives the agent candidate pages; agent answers grounded in the wiki
6. **Save durable answers** — `llm-wiki query save <file> --as synthesis --title "..."` so answers compound instead of dying in chat
7. **Lint periodically** — `llm-wiki lint` flags broken links, orphan pages, uncited claims, duplicates
8. **Refactor when messy** — agent uses `wiki-refactor` skill to merge, split, deprecate without losing knowledge

Everything is plain Markdown in a Git repo. Obsidian works as a viewer.
