# Per-operation model override + conditional self-correction — issue #279

Part of epic #271 (ingestion performance). Two knobs that cut cost and latency
without lowering ingestion quality.

## Per-operation model override (`models`)

`WorkspaceConfig.model` is the single global model. `models` overrides it per
operation:

```yaml
model: ollama:llama3.1          # global fallback
models:
  ingest: anthropic:MiniMax-M3  # strong model where structure matters
  ask: ollama:llama3.1          # cheap/local for interactive Q&A
  maintain: anthropic:MiniMax-M3
```

`factory.resolve_model(cfg, operation)` resolves the effective model: the
override for `ingest` / `ask` / `maintain` if present, else `cfg.model`. An
empty `models` map is the previous single-model behaviour, byte for byte.

### Cost / $ tradeoff

- **Ingestion** runs the agent with tools, multi-pass, and structured output —
  a weak model triggers the structured-output fallback and retries
  (`agent_max_retries`), inflating tokens and wall time. Pinning a strong model
  here is where the spend pays off.
- **Ask** is interactive and high-frequency. Keeping it on a cheap/local model
  avoids paying a premium model on every follow-up question.
- Net effect: spend the strong-model budget on the few ingestion jobs, not on
  the many `ask` calls. Leave `models` empty to keep one model for everything.

## Conditional self-correction

Before re-invoking the agent to fix structural lint findings, ingestion now runs
a deterministic, **LLM-free** repair pass (`lint_service.autofix_contents`):

- `missing_frontmatter` → synthesize minimal frontmatter (title from the H1 or
  filename stem, `type` inferred from `wiki/<dir>/`, `confidence: medium`,
  `updated_at: today`);
- `invalid_page_type` → correct `type` to the one the directory implies.

Findings code can't settle (e.g. broken wikilinks) still go to the agent fix
loop (`agent_fix_retries`). When every finding is code-fixable the agent is
**never re-invoked** — the fix pass costs zero LLM calls.

## Structured-output fallback on ingestion — issue #291

A "fallback" is logged when the agent doesn't return a `structured_response`.
Two changes make that both rarer and cheaper:

1. **JSON-in-text coercion.** Tool-calling-weak models (incl. MiniMax-M3 and the
   `*-mini` family under load) often answer with the schema's JSON *as text*
   instead of calling the final structured-output tool. `factory` now parses the
   last messages (including a ```json``` fence) and validates them into the
   schema **before** giving up. This recovers the structured data with **no
   model re-invoke**, so a model that merely answered as text no longer counts
   as a fallback (`used_fallback` now means real data loss).
2. **`ingest_max_retries`.** Ingestion's transient-error retry budget, separate
   from `agent_max_retries` (which `ask` keeps). `None` inherits
   `agent_max_retries`.

```yaml
agent_max_retries: 2     # ask and everything else
ingest_max_retries: 1    # ingestion only — a strong model rarely needs 2
models:
  ingest: anthropic:MiniMax-M3
```

### Recommended ingest models (fallback / cost tradeoff)

| Model | Tool-calling | Fallback risk | When |
| --- | --- | --- | --- |
| `anthropic:MiniMax-M3` | strong | low | default strong ingest (current wiki config) |
| `anthropic:claude-*` | strong | very low | highest quality, higher $ |
| `ollama:llama3.1` (local) | weak | high | offline only — expect coercion to carry it |

Measure the real rate with the populated baseline (#295):
`python scripts/ingest_baseline.py --seed-brain ~/.wiki/brains/desktop`.
