# A/B ingestão: cap de output (2048) + quality bar conciso — 2026-07-08 (#351)

Experimento da hipótese H5 do épico #348 (executa o item 6 do #333). Braço A =
baseline publicado `ingest-tool-buckets-2026-06-27.md` (MiniMax-M3, brain seed
`desktop` 176 páginas). Braço B = mesmo harness com
`max_output_tokens_by_op: {ingest: 2048}` + quality bar 150–350 palavras
(mandato de decomposição intocado). 3 runs; run 1 (warmup) descartado; runs
2–3 agregados (p50 = média, mesma convenção n=2 do baseline).

> Nota de execução: 2 runs adicionais morreram com `529 overloaded` do endpoint
> MiniMax antes de completar — excluídos (falha de provider, não do pipeline).

## Resultado (braço B, runs 2–3)

| Cenário | Métrica | A (baseline) | B (cap) | Δ | gate |
| --- | --- | ---: | ---: | ---: | --- |
| long × populado | total p50 | 284.0s | **171.7s** | **−40%** | ✅ (−20%) |
| long × vazio | total p50 | 246.8s | 184.5s | **−25%** | ✅ |
| short × populado | total p50 | 125.4s | 67.3s | −46% | ✅ |
| long × populado | tokens_out | ~33.5k | 28.5k | −15% | ❌ (−25%) |
| long × vazio | tokens_out | ~27.7k | 22.9k | −17% | ❌ |
| short × populado | tokens_out | ~10.6k | 6.7k | −37% | ✅ |
| long × populado | tokens_in | 672.8k | **805.6k** | **+20%** | ⚠️ |
| long × populado | páginas | 12 (ref. model-comparison) | 10–11 | ≈ | ✅ (sem colapso) |
| long × vazio | páginas | — | 12 | — | ✅ |

## Leitura — validada para LATÊNCIA, com trade-off de input

1. **O cap mata as chamadas runaway.** As chamadas que saturavam ~4096 output
   tokens (meta-achado do #333) somem; a latência despenca em todos os
   cenários (−25% a −46%), muito além do gate de −20%. O gargalo de *tempo*
   era o teto de geração por chamada — confirmado.
2. **tokens_out cai menos que o esperado no long** (−15/−17% vs gate −25%):
   o conteúdo final (páginas) continua sendo escrito; o corte real é no
   overshoot por chamada, não no volume total de páginas.
3. **Trade-off: tokens_in sobe ~+20% no cenário pesado** (673k → 806k): com o
   cap, o agente faz mais turnos (134–141 tool calls vs ~100) e cada turno
   re-envia system + histórico. A preço MiniMax (~$0.30/M in, ~$1.20/M out) o
   custo $ do job fica ~+14%. **O cap compra latência com input** — reforça a
   alavanca real do #333 (reduzir re-send por turno) e o experimento de core
   (#352).
4. **Cobertura sem colapso, mas no limite**: 12/12 páginas no long×vazio;
   10–11 vs 12 no long×populado — abaixo do baseline estrito, o suficiente
   para disparar a regra de descarte do prompt (ver decisão pós-review).
   Nenhum run colapsou a fonte em 1 página (modo Exp #5 evitado).

## Decisão pós-review (regra de descarte do spec aplicada)

Páginas no long×populado ficaram em 10–11 vs 12 do baseline — o critério de
descarte do #351 ("páginas < baseline → reverter prompt, manter só a config")
dispara. **O quality bar conciso foi revertido no merge**; entra só o cap
(opt-in). A latência medida é atribuível majoritariamente ao cap (que elimina
as chamadas runaway de ~4096 tokens); re-testar o prompt isoladamente fica
para follow-up se o cap sozinho não segurar o ganho.

## Decisão

- **Código entra** (merge): `max_output_tokens`/`max_output_tokens_by_op`
  default `None` = comportamento idêntico; cap vira ferramenta opt-in de
  latência (recomendado: `ingest: 2048` quando latência importa mais que
  custo de input).
- **Não vira default**: gate de tokens_out não atingido no cenário-alvo e o
  input sobe; a redução líquida de custo do #333 continua dependendo de
  reduzir o re-send (`system_framework` + `assistant_history`) — item do
  experimento de core #352.

## Reprodução

```bash
# config: model anthropic:MiniMax-M3, max_output_tokens_by_op: {ingest: 2048}
python scripts/ingest_baseline.py --seed-brain ~/.wiki/brains/desktop   # 3x, descartar run 1
```
