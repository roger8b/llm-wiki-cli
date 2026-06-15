# CLI machine-readable output (`--json`)

Read commands accept a `--json` flag. With it set, the command prints **a single
JSON object** to stdout and nothing else — no Rich tables, no banners. Logs and
warnings (e.g. the agent fallback notice) go to **stderr**, so stdout is always
safe to pipe into `json.loads`.

## Compatibility policy

- Top-level payloads are always **named objects**, never a bare array — new
  metadata can be added alongside without breaking parsers.
- Fields are only **added**, never removed or renamed. Treat unknown fields as
  forward-compatible and ignore them.

## Payloads per command

### `wiki search <query> --json`

```json
{
  "results": [
    {"path": "wiki/concepts/rag.md", "title": "RAG", "score": 0.92, "source": "keyword", "snippet": "…técnica que «recupera» documentos…", "type": "concept", "tags": ["ai"]}
  ]
}
```

`source` is `keyword` or `semantic`. `snippet`, `type`, `tags` are present when
available (added in #197). No results → `{"results": []}` with exit 0.

### `wiki review --json` (no id)

```json
{"pending": [{"id": "CR-1", "status": "pending_review", "files_changed": 2, "summary": "…"}]}
```

### `wiki review <id> --json`

The full `ChangeRequest` object, including `changes` (each with `diff`,
`operation`, `path`, `quality_score`, `quality_flags`).

### `wiki lint --json`

```json
{"findings": [{"kind": "broken_link", "severity": "error", "message": "…", "pages": ["wiki/a.md"]}], "batches": [], "skipped": []}
```

With `--all`, semantic auditing runs in batches grouped by type directory under
`lint_token_budget` (config, default 60000). `batches` lists the `{name, pages}`
processed and `skipped` lists those deferred over budget (no page is dropped
silently). `--scope <dir>` restricts batches to one type directory. Without
`--all`, `batches`/`skipped` are empty. Exit code is non-zero when any finding
has `severity: "error"`.

### `wiki jobs --json`

```json
{"jobs": [{"id": 1, "type": "ingest", "status": "done", "created_at": "…", "error": null}]}
```

### `wiki jobs stats [--since YYYY-MM-DD] --json`

Per-model agent telemetry aggregated from job results (and CR `meta.json` for
runs without a job). Mirrored by the API at `GET /api/jobs/stats?since=…`
(consumed by the observability dashboard, #151).

```json
{"stats": [{
  "model": "ollama:llama3.1", "runs": 12,
  "tokens_in_avg": 4200.0, "tokens_in_p95": 9000,
  "tokens_out_avg": 800.0, "tokens_out_p95": 1500,
  "latency_ms_avg": 5400.0, "latency_ms_p95": 12000,
  "fallback_rate": 0.08, "phantom_rate": 0.0,
  "applied": 7, "rejected": 2, "est_cost_usd": 0.0
}]}
```

`est_cost_usd` is `null` for models without a known price (`core/pricing.py`);
local `ollama:` models cost `0.0`. **A/B a model swap**: run `wiki evals run`
with each model, compare the `evals/results/*.json`, then cross-check live cost
and quality with `wiki jobs stats`.

### `wiki autolink [--scope <dir>] [--dry-run] --json`

Deterministically wraps the first plain-text mention of an existing page's title
in `[[wikilinks]]` (no LLM). `--dry-run` lists proposals without a CR; otherwise
a single change request is created. Mirrored by `POST /api/wiki/autolink`
(`{scope?, dry_run?}`).

```json
{"dry_run": true, "pages": 1,
 "mentions": [{"page": "wiki/concepts/note.md", "title": "RAG", "target": "wiki/concepts/rag.md", "snippet": "…de «RAG» aqui…"}]}
```

Without `--dry-run`: `{"change_request_id": "CR-1", "files_changed": 1}` (or
`{"mentions": [], "pages": 0}` when nothing matches). Code, inline code, URLs,
markdown links, existing wikilinks, headings and self-links are never touched.

### `wiki ask <question> --json`

```json
{
  "answer": "…",
  "citations": [{"page": "wiki/concepts/rag.md", "source": null, "quote": null, "invalid": false}],
  "suggested_page": null,
  "change_request_id": null
}
```

`change_request_id` is non-null when invoked with `--save`.

### `wiki log --json`

```json
{"entries": ["- 2026-06-14 applied CR-1 …"], "raw": "…full log.md…"}
```

## Error envelope

`wiki ingest` also accepts `--json` (a write command): its success output stays
human, but a failure emits the same error envelope on stderr — e.g. an
already-processed source exits 4, a missing file exits 3.

When a command running with `--json` fails, the error is written to **stderr**
as a JSON object and stdout stays empty:

```json
{"error": {"code": "not_found", "exit_code": 3, "message": "Change request not found: CR-X"}}
```

See [the exit-code table](#exit-codes) below (standardised in #198).

### Exit codes

| code | meaning | examples |
|------|---------|----------|
| 0 | success | |
| 2 | invalid usage | bad flag/arg (Typer) |
| 3 | not found | CR/page/source/brain missing |
| 4 | conflict/duplicate | `SourceAlreadyProcessedError`, colliding slug |
| 5 | provider/LLM | missing API key, model timeout |
| 6 | extraction | `ExtractorUnavailableError`, `EmptyExtractionError` |
| 130 | cancelled | `JobCancelledError` / Ctrl-C |
