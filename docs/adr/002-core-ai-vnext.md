# ADR 002 — Núcleo de IA vNext: veredito das 8 hipóteses (épico #348)

Status: **Accepted** (2026-07-12) — consolida o épico #348 (#349–#356).

Substitui os 6 relatórios A/B que viviam em `docs/baselines/`
(`core-swap-ab-2026-07-09`, `ingest-output-cap-ab-2026-07-08`,
`search-ask-rag-ab-2026-07-08`, `search-chunk-passages-ab-2026-07-09`,
`search-graph-signal-ab-2026-07-09`, `search-query-expansion-ab-2026-07-11`),
deletados no mesmo PR desta ADR. Os baselines de **referência**
(`search-2026-07-07.md`, `ingest-model-comparison-2026-06-25.md`,
`ingest-2026-06-*.md`) permanecem —
são o ponto de comparação de medições futuras, não experimentos encerrados.

## Contexto

O épico #348 atacou o núcleo de IA (retrieval, `ask`, core de agente) com um
programa de 8 hipóteses, cada uma com gate numérico e **critério de descarte
explícito**. Regra herdada do #333: descartar com dados é resultado válido.

Convenção de medição em todas as histórias: brain seed `desktop` (176 páginas,
217 embeddings), modelo `anthropic:MiniMax-M3`, 3 runs com o run 1 (warmup)
descartado, p50 = mediana (média quando n=2), golden set em
`evals/retrieval/golden.yaml`, harness `scripts/search_baseline.py` (hoje
`llmwiki.evals.retrieval`, #366).

## Decisão

**Nenhuma hipótese virou default.** Todo caminho novo entra atrás de config
com fallback byte-idêntico ao comportamento anterior. Duas hipóteses foram
invalidadas e o código correspondente foi cortado (#364).

| # | Hipótese | História | Veredito | Resultado no código |
| --- | --- | --- | --- | --- |
| H1 | Sem baseline não há programa | #349 | ✅ pré-requisito cumprido | harness + `docs/baselines/search-2026-07-07.md` |
| H2 | RAG single-shot no `ask` | #350 | ⚠️ parcial | `ask_mode` (default `agent`) |
| H5 | Cap de output na ingestão | #351 | ⚠️ parcial | `max_output_tokens` / `max_output_tokens_by_op` (default `None`) |
| H6 | Runner minimalista (troca de core) | #352 | ⚠️ parcial | `agent_core` (default `deepagents`) |
| H3 | Sinal de grafo no RRF | #353 | ❌ invalidada | **código removido** (#364) |
| H4 | Retrieval em nível de chunk | #354 | ⚠️ parcial | `page_embeddings.chunk_text` (sempre ligado, custo zero) |
| H7 | Expansão multi-query | #355 | ✅ validada p/ recall | `search_query_expansion` (default `0`) |
| H8 | Chunking token-aware | #356 | ❌ descartada no gate | **sem implementação** |

## Hipótese por hipótese

### H1 — Baseline de retrieval e ask (#349) ✅

Pré-requisito inegociável do épico. Entregou o harness (golden set, recall@k,
MRR, p50/p95 de latência, baseline de `ask` com tokens e tool calls) e o
relatório `docs/baselines/search-2026-07-07.md`, que é o braço A de H2, H3, H4
e H7.

Achado que dirigiu o resto do épico: **hybrid (0.872 recall@5) é pior que
semantic-only (0.942)** — o ruído da lista keyword custa ~7 p.p. A alavanca de
retrieval é pesar/gatear o FTS, não somar sinais novos.

### H2 — RAG single-shot no `ask` (#350) ⚠️ parcial → `ask_mode`

10 perguntas × 3 runs, único delta `--ask-mode rag`.

| Métrica | agent | rag | Δ | gate |
| --- | ---: | ---: | ---: | --- |
| latência p50 | 11.6s | 12.1s | **+4%** | ↓ ≥ 50% ❌ |
| latência p95 | 26.2s | 16.6s | −37% | — ✅ |
| tokens_in p50 | 33.6k | 12.3k | **−64%** | ↓ ≥ 60% ✅ |
| tokens_in p95 | 74.0k | 12.9k | −83% | — ✅ |
| tokens_out p50 | 804 | 1174 | +46% | resposta mais completa |
| tool calls p50 | 7 | 0 | −100% | ✅ |
| citações válidas | 0 (2 inválidas) | 0 | = | > 0 ❌ |

Leitura: o loop agentico era o gargalo de **tokens**, não de **tempo**. No
MiniMax-M3 a geração domina (~75–90 tok/s), então cortar 7 turnos não move o
p50 — só a cauda (p95 −37%, sem os runs de exploração longa). Citações
quebram nos dois modos (fallback de structured output em 8+/30 runs): é
limitação de tool-calling do modelo, não do caminho.

**Decisão**: `ask_mode` entra opt-in (`agent` default, `rag`/`auto`
disponíveis). Não vira default: gate de latência não bateu e citações não
melhoraram.

### H5 — Cap de output na ingestão (#351) ⚠️ parcial → `max_output_tokens_by_op`

Braço B = `max_output_tokens_by_op: {ingest: 2048}` + quality bar conciso.

| Cenário | Métrica | A | B | Δ | gate |
| --- | --- | ---: | ---: | ---: | --- |
| long × populado | total p50 | 284.0s | **171.7s** | **−40%** | −20% ✅ |
| long × vazio | total p50 | 246.8s | 184.5s | −25% | ✅ |
| short × populado | total p50 | 125.4s | 67.3s | −46% | ✅ |
| long × populado | tokens_out | ~33.5k | 28.5k | −15% | −25% ❌ |
| long × vazio | tokens_out | ~27.7k | 22.9k | −17% | ❌ |
| long × populado | tokens_in | 672.8k | **805.6k** | **+20%** | ⚠️ |
| long × populado | páginas | 12 | 10–11 | ≈ | sem colapso |

Leitura: o cap mata as chamadas runaway que saturavam ~4096 tokens de output —
a latência despenca muito além do gate. Mas tokens_out cai pouco (o conteúdo
final continua sendo escrito; o corte é no overshoot por chamada) e **tokens_in
sobe ~20%**, porque mais turnos (134–141 tool calls vs ~100) significam mais
re-send de system + histórico. A ~$0.30/M in e ~$1.20/M out, o job fica ~+14%
mais caro. **O cap compra latência com input.**

Páginas em 10–11 vs 12 dispararam a regra de descarte do #351: **o quality bar
conciso foi revertido no merge**; entrou só a config.

**Decisão**: `max_output_tokens` / `max_output_tokens_by_op` default `None`
(idêntico ao atual). Recomendado `ingest: 2048` quando latência importa mais
que custo de input.

### H6 — Runner minimalista vs DeepAgents (#352) ⚠️ parcial → `agent_core`

Braço B = `agent_core: minimal` (loop nativo de tool-calling), mesmo harness,
mesmo seed.

| Cenário | Métrica | deepagents | minimal | Δ | gate |
| --- | --- | ---: | ---: | ---: | --- |
| long × populado | tokens_in p50 | 672.8k | 501.2k¹ | **−26%** | −30% ❌ por pouco |
| long × vazio | tokens_in p50 | 603.5k | 214.6k | **−64%** | ✅ |
| long × populado | latência p50 | 284.0s | 141.0s | **−50%** | −20% ✅ |
| long × vazio | latência p50 | 246.8s | 126.7s | −49% | ✅ |
| short × populado | tokens_in p50 | 147.4k | 269.3k | **+83%** | ❌ |
| short × populado | latência p50 | 125.4s | 144.4s | +15% | ❌ |
| long × populado | páginas | 12 | 12, 12 | = | ✅ |

¹ inclui um outlier de 726.7k num run com `fallback=True` (retry storm); o
outro run fez 275.8k (−59%).

`system_framework` colapsa de 314k (47% de tokens_in) para **16.5k (4%)** no
long×populado — a hipótese central (overhead do framework) está confirmada.

**Qualidade sobe**: `wiki evals run` agrega **90.9 vs 79.1 de baseline
(+11.8 pts)**, com 04-duplicate saindo de 25 → 100 e **zero fallbacks de
structured output** (baseline: 4/5) — o `submit_result` como tool única final
funciona onde o ToolStrategy do DeepAgents falhava no MiniMax.

O bloqueio é **fontes curtas**: +83% de input, +15% de latência, tool calls
28 → 59–75. Sem o scaffolding de planejamento do DeepAgents, o modelo explora
demais em fonte pequena.

**Decisão**: gate estrito não fecha → **não abre migração total** (ask,
maintain e outline seguem DeepAgents). O `MinimalRunner` permanece atrás de
`agent_core` (default `deepagents`) — desvio consciente da cláusula "sai do
código": os ganhos em fontes longas (−50% de tempo) e a qualidade recorde
fazem dele o caminho vivo da fase seguinte.

### H3 — Sinal de grafo (backlinks) no RRF (#353) ❌ invalidada → código cortado

| Métrica | off | on | Δ | gate |
| --- | ---: | ---: | ---: | --- |
| recall@5 | 0.872 | 0.872 | **0** | tinha que subir ❌ |
| recall@10 | 0.955 | 0.949 | −0.6 p.p. | — |
| MRR | 0.845 | 0.867 | +2.2 p.p. | não caiu ✅ |
| latência p50 | 144.6ms | 148.3ms | +3.7ms | ok |

O grau de backlinks não muda o top-5: as páginas centrais que o grafo
promoveria já estão lá pelos sinais keyword/semantic. O boost só reordena
dentro do top e empurra 1 caso para fora do top-10.

**Decisão**: hipótese invalidada neste corpus. O código ficou default-off por
uma fase e foi **removido na curadoria (#364, PR #372)** — flag, helper de
grau, bloco de re-rank e plumbing. Se a ideia voltar, reimplementa do zero com
esta ADR como referência.

**Follow-up herdado**: re-pesar o RRF (peso menor na lista keyword, ou gate de
match exato) — o baseline mostra +7 p.p. de recall@5 disponíveis (0.872 →
0.942) sem custo novo.

### H4 — Retrieval em nível de chunk (#354) ⚠️ parcial → `chunk_text`

O reindex passa a guardar um excerpt de 300 chars por chunk
(`page_embeddings.chunk_text`, migração aditiva) e o KNN devolve o passage do
chunk vencedor, usado como snippet quando o FTS não trouxe um. Recall
**byte-idêntico** nos três modos (keyword 0.731 / semantic 0.942 / hybrid
0.872) — o passage não participa do ranking, só enriquece o resultado.

A premissa de ingestão caiu **sem run novo**: o baseline de tool
buckets do #333 (2026-06-27, medição local nunca versionada; números citados no
corpo do épico #348) já mostra **explore tool calls = 0 em 12/12 runs** — o agente de ingestão não usa busca no loop, então não há bucket
`other` a cortar (mesma razão da morte do #309).

**Decisão**: o snippet semântico entra (custo zero, stores legados
compatíveis); a promessa de reduzir `read_file` na ingestão cai.

### H7 — Expansão multi-query (#355) ✅ validada para recall → `search_query_expansion`

Fase 1 (heurística, sem LLM — variante "sem stopwords PT"): **efeito zero**,
recall idêntico. A reformulação que ajuda precisa de vocabulário novo, não de
menos palavras.

Fase 2 (variantes geradas por LLM, modo hybrid, golden completo):

| expand | recall@5 | recall@10 | MRR | vague | lat p50 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0 (off) | 0.872 | 0.955 | 0.845 | 0.611 | 146ms |
| 2 | 0.885 | 0.955 | 0.837 | 0.667 | ~1.6s (geração fria) |
| **3** | **0.910** | 0.936 | 0.837 | **0.778** | 583ms (cache quente) |

Gate de recall bate com folga (vague +16.7 p.p., agregado +3.8 p.p. — o maior
ganho de retrieval do épico). Gate de latência estoura: 583ms com cache quente
é 4× o off, ~1.6s na primeira consulta. Falha do gerador degrada para a
consulta original; a expansão **não** se aplica a `related_pages` nem ao
prefetch da ingestão (o custo por conceito multiplicaria).

**Decisão**: `search_query_expansion` opt-in (default `0` = busca
byte-idêntica). Recomendado para o RAG do `ask`, onde 0.6s é ruído dentro de
uma chamada de 10s+.

### H8 — Chunking token-aware (#356) ❌ descartada no gate de medição

Fase 1 do spec (medir antes de implementar): o chunker por caracteres já
produz chunks de tokens **uniformes dentro de cada fonte** — p95/p50 = 1.00 em
prosa EN, prosa PT e código (tiktoken cl100k). A variância real é **entre**
tipos de conteúdo (2.15× código vs prosa), mas não há evidência de que
dimensionar por tokens mova latência ou custo.

**Decisão**: sem implementação. Os drivers medidos são volume de geração (H5)
e re-send por turno (H6).

## Meta-achado do épico

Duas medições independentes (H2 e H5) convergiram no mesmo lugar: **o custo do
sistema está no volume de geração e no re-send de system + histórico por
turno**, não no número de chamadas nem no caminho agentico em si.

- Cortar turnos (H2: 7 → 0) não move a latência p50 quando a geração domina.
- Cortar output por chamada (H5) derruba a latência 25–46% mas **sobe** o input
  20%, porque mais turnos = mais re-send.
- Trocar o framework (H6) é o único lever que ataca o re-send na raiz:
  `system_framework` 47% → 4% de tokens_in.

Consequência prática: qualquer otimização futura de custo deve ser medida em
**tokens_in por turno × turnos**, não em número de tool calls.

## Consequências

- 5 configs novas, todas com fallback byte-idêntico: `ask_mode`, `agent_core`,
  `max_output_tokens` / `max_output_tokens_by_op`, `search_query_expansion`.
  Nenhuma exposta na UI ainda — histórias #368–#371 cobrem isso, com #367
  (`wiki config get/set`) como fundação.
- `page_embeddings.chunk_text` é o único caminho que entrou sempre ligado
  (custo zero, ranking intocado).
- `search_graph_signal` não existe mais (#364).
- Os 6 relatórios A/B foram deletados; a medição vive aqui. Os baselines de
  referência continuam em `docs/baselines/`.

## Reprodução

```bash
# retrieval + ask (H1–H4, H7)
python scripts/search_baseline.py --seed-brain ~/.wiki/brains/desktop
python scripts/search_baseline.py --seed-brain ~/.wiki/brains/desktop --ask --runs 3

# ingestão (H5, H6) — 3 runs, descartar o warmup
python scripts/ingest_baseline.py --seed-brain ~/.wiki/brains/desktop
wiki evals run
```
