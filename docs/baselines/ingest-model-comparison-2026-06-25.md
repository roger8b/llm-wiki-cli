# Ingestion baseline — comparativo de modelos (2026-06-25)

Gerado após #301 (dedup cross-chunk por slug canónico). Pipeline instrumentado por #272/#273.
Brain populado = cópia read-only do `wiki/` do brain `desktop` (166 páginas, cenário #295).

> `gpt-5-mini` corre os 4 casos (empty + populated × 2 amostras); `MiniMax-M3` foi
> reduzido aos 2 casos **populated** (single-pass + multi-chunk) para poupar tempo/custo.

## Headline — long_multi_chunk, brain populado (166 páginas)

| Métrica | `openai:gpt-5-mini` | `anthropic:MiniMax-M3` |
| --- | ---: | ---: |
| Tempo total | 563.0s | **378.6s** |
| outlining | 320.8s | **130.5s** |
| chunks (Σ) | 141.2s | 224.1s |
| fixing_structural_issues | 101.0s | **24.0s** |
| Tokens in / out | 863.876 / 98.829 | 1.728.812 / 41.743 |
| tool calls | 301 | **174** |
| fallback | False | False |
| explore calls | 0 | 0 |
| páginas geradas | 40 | 12 |

## single_pass, brain populado (166 páginas)

| Métrica | `gpt-5-mini` | `MiniMax-M3` |
| --- | ---: | ---: |
| Tempo total | 318.4s | **284.6s** |
| running_agent | 318.4s | 242.6s |
| Tokens in / out | 271.292 / 27.481 | 230.679 / 10.043 |
| tool calls | 28 | 46 |
| fallback | False | False |
| páginas geradas | 8 | 10 |

## Leitura

- **#291 mantém-se nos dois modelos:** `fallback=False` em todos os runs — não há fallback
  de structured-output a inflar latência.
- **Cache/dedup do epic anterior holds:** `explore calls = 0` mesmo com brain de 166 páginas.
- **MiniMax-M3 é mais rápido no caso pesado** (multi-chunk populated: −33% tempo) com
  outlining e fix-pass bem mais baratos, à custa de ~2× tokens de input.
- **gpt-5-mini gera mais páginas** (40 vs 12) — granularidade de conceitos maior; é o
  cenário onde o #301 mais importa (mais páginas = mais risco de slugs duplicados).
- **Bottleneck dominante (ambos):** `running_agent` / `outlining`. Próximos ganhos de
  perf estão aí, não no merge (que o #301 já cobre).

## Validação do fix #301 nos runs reais

Nos logs do `gpt-5-mini long_multi_chunk` a LLM declarou variantes de slug
(`Re-ranking.md` + `re_ranking.md`, `Chunking.md` + `chunking_strategies.md`,
`Vector Store.md` …) mas os ficheiros **escritos** saíram canonizados
(`approximate-nearest-neighbor-search.md`, `summary-retrieval-concepts.md`) — confirmando
a colapsagem para o slug canónico. Após o follow-up (`_merge_results` canoniza os paths
declarados), declarado e escrito passam a bater no `_audit_result`.

## Reprodução

```bash
# gpt-5-mini (config atual)
python scripts/ingest_baseline.py --seed-brain ~/.wiki/brains/desktop

# MiniMax-M3: definir model: anthropic:MiniMax-M3 em ~/.wiki/config.yaml e repetir
```
