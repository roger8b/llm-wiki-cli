# A/B ask: agent vs RAG single-shot — 2026-07-08 (#350, épico #348)

Experimento da hipótese H2 contra o baseline `search-2026-07-07.md` (#349).
Mesmo harness (`scripts/search_baseline.py --ask`), mesmo brain seed (176
páginas, 217 embeddings), mesmo modelo (`anthropic:MiniMax-M3`), 10 perguntas ×
3 runs (warmup descartado). Único delta: `--ask-mode rag`.

## Resultado

| Métrica | agent (#349) | rag | Δ | gate H2 | veredito |
| --- | ---: | ---: | ---: | --- | --- |
| latency p50 | 11.6s | 12.1s | **+4%** | ↓ ≥ 50% | ❌ |
| latency p95 | 26.2s | 16.6s | −37% | — | ✅ (cauda) |
| tokens_in p50 | 33,626 | 12,268 | **−64%** | ↓ ≥ 60% | ✅ |
| tokens_in p95 | 74,037 | 12,896 | −83% | — | ✅ |
| tokens_out p50 | 804 | 1,174 | +46% | — | (resposta mais completa) |
| tool_calls p50 | 7 | 0 | −100% | 0 no caminho feliz | ✅ |
| citações válidas | 0 (2 inválidas) | 0 | = | > 0 | ❌ (empate — ver abaixo) |

## Leitura — hipótese PARCIALMENTE validada

1. **Custo despenca, latência não.** tokens_in −64% (p50) e −83% (p95), zero
   tool calls. Mas a latência p50 ficou igual: no MiniMax-M3 a geração domina
   (~75–90 tok/s × ~1.2k tokens_out ≈ 13–15s) — o mesmo meta-achado do #333.
   O loop agentico não era o gargalo de *tempo* do ask neste modelo; era o
   gargalo de *tokens*. A cauda melhora (p95 −37%) porque o RAG elimina os
   runs de exploração longa (outlier de 321s no baseline).
2. **Citações continuam quebradas no MiniMax — em ambos os modos.** 8+/30 runs
   em fallback texto também no caminho toolless; o fallback preserva o answer
   mas perde `citations`. Baseline agent: 2 citações, 2 inválidas; rag: 0.
   Empate técnico — o problema é a confiabilidade de structured output do
   modelo, não o caminho. **Evidência direta para o experimento de core (#352)**
   e para re-testar com modelo de tool-calling forte.
3. **O gate de −50% de latência estava calibrado para o gargalo errado** no
   modelo da convenção. Em modelos rápidos (tok/s alto) ou com respostas
   curtas, a vantagem de 1 chamada vs 7+ turnos deve aparecer; fica como
   re-medição opcional fora da convenção MiniMax.

## Decisão

- **Código entra** (merge): `ask_mode` default `"agent"` — comportamento
  idêntico sem config; `rag`/`auto` ficam opt-in com ganho comprovado de −64%
  de tokens_in e p95 −37%.
- **H2 não vira default** por ora: gate de latência p50 não atingido e
  citações não melhoraram (limitação do modelo, não do caminho).
- Follow-ups alimentados: #352 (structured-output fiável é pré-condição para
  citações), #353 (retrieval do RAG usa hybrid — pesar keyword melhora o
  contexto recuperado).

## Reprodução

```bash
# config: model: anthropic:MiniMax-M3
python scripts/search_baseline.py --seed-brain ~/.wiki/brains/desktop --ask --runs 3            # agent
python scripts/search_baseline.py --seed-brain ~/.wiki/brains/desktop --ask --ask-mode rag --runs 3 --tag rag
```
