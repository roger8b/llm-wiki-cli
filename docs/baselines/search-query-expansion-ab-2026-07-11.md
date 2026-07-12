# A/B busca: expansão multi-query — 2026-07-11 (#355, épico #348)

Experimento H7 contra o baseline `search-2026-07-07.md` (#349). Golden set
completo, brain seed 176 páginas, geração de variantes com
`anthropic:MiniMax-M3` (cadeia "outline" → modelo barato quando pinado),
cache por consulta.

## Fase 1 — heurística (sem LLM): efeito ZERO

Variante "sem stopwords PT" fundida por RRF: recall@5 agregado e por classe
**idênticos** (0.872 / vague 0.611). A reformulação que ajuda precisa de
vocabulário novo (sinônimos/termos técnicos), não de menos palavras.

## Fase 2 — variantes LLM (modo hybrid, golden completo)

| expand | recall@5 | recall@10 | MRR | vague | lat p50 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0 (off) | 0.872 | 0.955 | 0.845 | 0.611 | 146ms |
| 2 | 0.885 | 0.955 | 0.837 | 0.667 | ~1.6s (geração fria) |
| **3** | **0.910** | 0.936 | 0.837 | **0.778** | 583ms (cache quente) |

Classes exact/multiword/paraphrase: inalteradas em todos os níveis.

## Leitura — VALIDADA para recall, com custo de latência

1. **Gate de recall bate com folga**: vague +16.7 p.p. (0.611→0.778; gate era
   +5) e agregado +3.8 p.p. (0.872→0.910) — o maior ganho de retrieval do
   épico até aqui. MRR estável (−0.8 p.p.).
2. **Gate de latência estoura**: 583ms com cache quente (4× o off) e ~1.6s na
   primeira consulta (geração). O critério "≤ 2×" do spec dispara → **não
   vira default**. No contexto do ask (chamada LLM de 10s+), 0.6s é ruído —
   por isso a config existe.
3. Falha do gerador degrada para a consulta original (mesmo padrão do
   semantic-fail); expansão NÃO se aplica a `related_pages` nem ao prefetch
   da ingestão (custo por conceito multiplicaria).

## Decisão

`search_query_expansion` entra **opt-in (default 0 = busca byte-idêntica)**,
recomendado para quem prioriza recall em consultas vagas (ex.: RAG do ask,
onde a latência de busca é dominada pela geração da resposta).

## Reprodução

```bash
# config: search_query_expansion: 3 (e modelo barato em models.outline, opcional)
python scripts/search_baseline.py --seed-brain ~/.wiki/brains/desktop
```
