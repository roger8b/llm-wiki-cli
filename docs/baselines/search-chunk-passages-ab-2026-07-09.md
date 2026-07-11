# A/B busca: passage do chunk em hits semânticos — 2026-07-09 (#354, épico #348)

Experimento H4 contra o baseline `search-2026-07-07.md` (#349). Reindex agora
guarda um excerpt (300 chars) por chunk (`page_embeddings.chunk_text`,
migração aditiva) e o KNN devolve o passage do chunk vencedor, usado como
snippet quando o FTS não trouxe um.

## Retrieval (harness #349, brain seed 176 páginas)

| Modo | recall@5 | recall@10 | MRR | Δ vs baseline |
| --- | ---: | ---: | ---: | --- |
| keyword | 0.731 | 0.763 | 0.708 | idêntico |
| semantic | 0.942 | 0.974 | 0.929 | idêntico |
| hybrid | 0.872 | 0.955 | 0.845 | idêntico |

Esperado: o passage não participa do ranking — só enriquece o resultado.
Verificação viva: hits em `search_pages` agora trazem trecho « » também quando
a origem é semântica (antes: só FTS).

## Premissa de ingestão INVALIDADA pelos dados existentes

A hipótese H4 apostava em cortar o bucket `other` (read_file) da ingestão. O
baseline `ingest-tool-buckets-2026-06-27.md` já mostra **explore tool calls =
0 em 12/12 runs** — o agente de ingestão não usa busca no loop (mesma razão
da morte do #309). Não há chamadas de `search_pages` para o passage encurtar,
logo **não há bucket a cortar na ingestão**; medir de novo seria repetir o
#309. A premissa cai sem run novo.

## Veredito — PARCIAL

- **Entra** (merge): snippet semântico com custo zero (300 chars por chunk no
  reindex, ranking intocado, recall byte-idêntico, stores legados compatíveis).
  Beneficia o ask agentico (escolher página sem `read_file`) e a UX de busca.
- **Cai**: a promessa de redução do bucket `other` na ingestão — invalidada
  pelos dados do próprio épico.

## Reprodução

```bash
python scripts/search_baseline.py --seed-brain ~/.wiki/brains/desktop --tag passages
```
