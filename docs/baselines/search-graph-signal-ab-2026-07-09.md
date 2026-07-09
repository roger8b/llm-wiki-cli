# A/B busca: sinal de grafo (backlinks) no RRF — 2026-07-09 (#353, épico #348)

Experimento H3 contra o baseline `search-2026-07-07.md` (#349). Mesmo harness,
golden set e brain seed (176 páginas, 217 embeddings). Delta único:
`search_graph_signal` (terceira lista RRF = candidatos re-rankeados por grau
de backlinks, prior sem introduzir páginas). Sem LLM.

## Resultado (modo hybrid, único afetado)

| Métrica | off (baseline) | on | Δ | gate |
| --- | ---: | ---: | ---: | --- |
| recall@5 | 0.872 | 0.872 | **0** | ❌ (tinha que subir) |
| recall@10 | 0.955 | 0.949 | −0.6 p.p. | — |
| MRR | 0.845 | 0.867 | +2.2 p.p. | ✅ (não caiu) |
| latência p50 | 144.6ms | 148.3ms | +3.7ms | ok |
| recall@5 por classe | — | — | idêntico em todas | — |

## Leitura — hipótese INVALIDADA neste corpus

1. **O grau de backlinks não muda o top-5.** As páginas centrais que o grafo
   promoveria já estão no top-5 pelos sinais keyword/semantic; o boost só
   reordena dentro do top (MRR +2.2) e empurra 1 caso para fora do top-10.
2. **O problema do hybrid continua sendo o ruído do keyword**, não a falta de
   sinal: hybrid 0.872 vs semantic-only 0.942 (achado do #349, intocado por
   esta história). A alavanca de retrieval é **pesar/gatear a lista FTS**, não
   somar priors.
3. Critério de descarte do #353 dispara (recall@5 não subiu) → o sinal fica
   **default off**; o código (~30 linhas, 1 query agregada) permanece como
   ferramenta de experimento com fallback byte-idêntico.

## Follow-up recomendado (herda a medição)

Nova história curta no #348: **re-pesar o RRF** (ex.: peso 0.5 na lista
keyword, ou gate "keyword só entra quando a consulta tem match exato de
termo") — o baseline mostra +7 p.p. de recall@5 disponíveis (0.872 → 0.942)
sem nenhum custo novo.

## Reprodução

```bash
python scripts/search_baseline.py --seed-brain ~/.wiki/brains/desktop            # off
python scripts/search_baseline.py --seed-brain ~/.wiki/brains/desktop --graph    # on
```
