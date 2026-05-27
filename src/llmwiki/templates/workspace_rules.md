## Knowledge base (llm-wiki)

This workspace uses a **llm-wiki brain** (`{{brain}}`) as its durable knowledge
base. Treat the `wiki` CLI as a first-class tool.

**Consume — before answering from memory or guessing:**
- `wiki ask "<question>"` — answer grounded in the brain (read-only)
- `wiki search "<term>"` — locate relevant pages

**Feed — capture durable knowledge (architecture, decisions, concepts, learnings):**
- `wiki source add <file>` then `wiki ingest <file>` — proposes a change request
- `wiki review` / `wiki apply <cr>` — review and apply the proposed change

**Rules:** the brain's `raw/` is immutable and you never write to `wiki/`
directly — every change goes through a change request (review + apply). The
brain is the source of truth for durable knowledge.

For richer, trigger-based behavior, install the skills: `wiki skills install`.
