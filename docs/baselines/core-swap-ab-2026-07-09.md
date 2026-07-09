# A/B core: DeepAgents vs MinimalRunner — 2026-07-09 (#352, épico #348)

Experimento H6. Braço A = baselines publicados (`ingest-tool-buckets-2026-06-27.md`
perf; `evals/BASELINE.md` qualidade 79.1). Braço B = `agent_core: minimal`
(loop nativo de tool-calling, sem DeepAgents), mesmo harness, mesmo brain seed
(176 páginas), `anthropic:MiniMax-M3`. 3 runs; run 1 (warmup) descartado;
runs 2–3 agregados (p50 = média, n=2).

## Perf (braço B, runs 2–3, vs baseline A)

| Cenário | Métrica | A (deepagents) | B (minimal) | Δ | gate |
| --- | --- | ---: | ---: | ---: | --- |
| long × populado | tokens_in p50 | 672.8k | 501.2k¹ | **−26%** | ❌ por pouco (−30%) |
| long × vazio | tokens_in p50 | 603.5k | 214.6k | **−64%** | ✅ |
| long × populado | latência p50 | 284.0s | 141.0s | **−50%** | ✅ (−20%) |
| long × vazio | latência p50 | 246.8s | 126.7s | −49% | ✅ |
| short × populado | tokens_in p50 | 147.4k | 269.3k | **+83%** | ❌ |
| short × populado | latência p50 | 125.4s | 144.4s | +15% | ❌ |
| long × populado | páginas | 12 | 12, 12 | = | ✅ |
| long × vazio | páginas | 11–12 | 6, 13 | ⚠️ variância | ⚠️ |

¹ inclui outlier de 726.7k num run com `fallback=True` (retry storm); o outro
run fez 275.8k (−59%).

`system_framework` colapsa: 314k (47% de tokens_in) → **16.5k (4%)** no
long×populado — a hipótese central (overhead do framework) confirmada.

## Qualidade (`wiki evals run`, braço B)

**Aggregate 90.9 vs baseline 79.1 (gate ✅, +11.8 pts).** Por caso: 70 / 85 /
100 / **100 (04-duplicate, era 25)** / 100. Frontmatter 100% em todos;
**fallback de structured output: 0/5 casos** (baseline: 4/5) — o
`submit_result` como tool única final funciona onde o ToolStrategy do
DeepAgents falhava no MiniMax. Links 127/128 resolvidos.

## Leitura

1. **A hipótese H6 confirma no alvo**: fontes longas (o gargalo do épico) —
   tokens_in −26/−64%, latência −49/−50%, `system_framework` 47%→4%.
2. **Qualidade SOBE** (+11.8 pts) — em particular dedup (04: 25→100) e
   structured output (0 fallbacks). Resolve na prática a fraqueza de
   tool-calling do MiniMax que o #350 expôs nas citações do ask.
3. **Fontes curtas regridem** (+83% input, +15% latência, tool calls 28→59-75):
   sem o scaffolding de planejamento do DeepAgents, o modelo explora mais em
   fontes pequenas. É o único bloqueio para migração total.
4. **Variância de páginas no long×vazio** (6 vs 13): 1 run enxuto; sem colapso
   em populado (12/12).

## Decisão (gate do #352)

Gate estrito (tokens_in −30% E latência −20% E evals ≥79.1 E páginas ≥
baseline em AMBOS os cenários) → **não fecha completo** (short regride;
long×populado −26% com outlier). Portanto:

- **Não abre migração total** (ask/maintain/outline seguem DeepAgents).
- **MinimalRunner permanece atrás de `agent_core` (default `deepagents`)** —
  desvio consciente da cláusula "sai do código": os ganhos em fontes longas
  (−50% tempo) e a qualidade recorde (90.9) fazem dele o caminho vivo da fase
  seguinte; remover seria re-implementar em semanas.
- **Follow-up sugerido** (nova história no #348): investigar a regressão em
  fontes curtas (ex.: nota de planejamento leve no prompt ou roteamento por
  tamanho `agent_core=minimal` só para multi-chunk) e re-medir o gate.

## Reprodução

```bash
# config: model anthropic:MiniMax-M3, agent_core: minimal
python scripts/ingest_baseline.py --seed-brain ~/.wiki/brains/desktop  # 3x, warmup fora
wiki evals run
```
