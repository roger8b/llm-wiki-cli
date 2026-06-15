# ROADMAP — llm-wiki: pipeline de ingestão e geração de conhecimento

> **Audiência deste documento: agentes de IA implementadores.**
> Leia a fase inteira antes de começar uma história. Cada história referencia a
> issue do GitHub (fonte de verdade dos critérios de aceite), os arquivos a
> tocar, o desenho da solução e as dependências. Não pule dependências.
>
> Projeto GitHub: https://github.com/users/roger8b/projects/2
> Repo: https://github.com/roger8b/llm-wiki-cli

---

## Objetivo do produto

llm-wiki transforma fontes brutas (artigos, PDFs, transcrições) em uma wiki
Markdown viva, mantida por agentes LLM com humano no loop (todo write vira
**change request** revisável). O objetivo deste roadmap: **maximizar a
qualidade do pipeline ingestão → conhecimento → consumo**, nesta ordem de
alavancas:

1. Texto limpo entrando (extração).
2. Agente de ingestão escrevendo páginas corretas, linkadas e sem duplicatas.
3. Recuperação (busca) boa — alimenta dedup, query e o app.
4. Revisão humana rápida (gargalo real do pipeline).
5. Agentes externos (CLI/skills) como cidadãos de primeira classe.
6. Qualidade contínua medida (evals, lint, manutenção verificada).

## Regras gerais de implementação (valem para TODAS as histórias)

- **Arquitetura em camadas**: `core/` (puro) → `db/` → `services/` →
  `interfaces/` (cli, api, mcp). `llm_agents/` só é importado lazy pelos
  services. Nunca importe `interfaces/` de dentro de `services/`.
- **Todo write do agente passa pelo `ChangeRequestBackend`**
  (`src/llmwiki/llm_agents/backend.py`). Nunca crie caminho de escrita direta
  em `wiki/`. `raw/` é imutável. `wiki/index.md` e `wiki/log.md` são gerados.
- **Runners injetáveis**: services recebem `runner` opcional para testar sem
  LLM (ver `ingest_service.Runner`). Mantenha o padrão em código novo.
- **Extras opcionais**: dependências pesadas (pypdf, trafilatura, embeddings)
  entram como extras no `pyproject.toml`; o core funciona sem elas com
  mensagem de erro clara (padrão já usado pelo extra `agent`).
- **Qualidade**: ruff + mypy strict + pytest passam antes de concluir.
  Pre-commit existe (`.pre-commit-config.yaml`). Testes em `tests/`.
- **Front**: React + TS + Vite + Tailwind + shadcn/ui + zustand, em `ui/`.
  Views em `ui/src/views/`, stores em `ui/src/stores/`, client API em
  `ui/src/lib/api.ts`, tipos em `ui/src/types/index.ts`. Testes vitest
  (`*.test.ts`) e e2e playwright (`ui/e2e/`).
- **API**: FastAPI em `src/llmwiki/interfaces/api/routers/`. Novo endpoint =
  router + tipo no front + método em `api.ts`.
- **Convenção de issues**: histórias têm título `[<nº do epic>] …`. Ao
  terminar, feche a issue via PR (`Closes #N`).

---

## Visão geral das fases (ordem de execução)

| Fase | Tema | Milestone GitHub | Benefício final |
|------|------|------------------|-----------------|
| 0 | Harness de evals (pré-requisito de medição) | Agentes M3 | Toda mudança de prompt/modelo passa a ser mensurável — sem regressão silenciosa |
| 1 | Extração & ingestão de qualidade | Agentes M1 | Qualquer fonte (PDF/HTML/longa) vira páginas corretas, linkadas e sem duplicatas |
| 2 | Recuperação semântica & query | Agentes M2 | Agentes acham o conhecimento certo com menos tokens; respostas auditáveis |
| 3 | Revisão & edição no app | App M4 | O gargalo humano (revisão) fica 5–10× mais rápido; curadoria sem sair do app |
| 4 | CLI & skills para agentes externos | Agentes M6 | Claude/Codex/etc. operam a wiki de forma barata, estruturada e completa |
| 5 | Ask conversacional, grafo & captura | App M5 | Consumo do conhecimento vira conversa; captura da web sem atrito |
| 6 | Qualidade contínua | Agentes M3 (restante) | Wiki se mantém saudável com custo previsível; escolha de modelo informada |
| 7 | Desktop Tauri: background & SO | App M7 | App vive no tray, jobs sobrevivem ao fechar a janela, captura global e auto-update |

Dentro de cada fase, as histórias estão em **ordem de execução** (dependências
primeiro).

### Status de implementação (atualizado em 2026-06-15)

- **Fase 0 — ✅ concluída.** 0.1 evals (#175, PR #210) + baseline versionado
  (`evals/BASELINE.md`, score 79.1, modelo `anthropic:MiniMax-M2.7`).
- **Fase 1 — ✅ 10/10 concluídas.** 1.1 PDF (#160), 1.2 HTML (#161), 1.3
  metadados (#163), 1.4 data/contexto (#164), 1.5 related_pages (#165), 1.5b
  áudio (#76), 1.6 chunking multi-pass (#162, PR #225), 1.7 dedup (#167, +
  hardening PR #223), 1.8 lint pré-CR / auto-correção (#166, PR #226), 1.9
  score (#168).
- **Fase 2 — ✅ 4/4 concluídas.** 2.1 snippets FTS5 (#171, PR #227), 2.2 busca
  semântica local sqlite-vec + RRF (#169, PR #228), 2.3 tool híbrida nos
  agentes (#170, PR #229), 2.4 validação de citations (#172, PR #213).
- **Fase 3 — ✅ 7/7 concluídas.** 3.1 edit-before-apply (#183, PR #214), 3.2
  apply/reject parcial (#184, PR #230), 3.3 telemetria/qualidade na revisão
  (#185, PR #231), 3.4 editor de página com preview (#186, PR #232), 3.5 criar
  página por template (#187, PR #233), 3.6 busca global no app (#188, PR #234),
  3.7 navegação por tags (#189, PR #235).

- **Fase 4 — ✅ concluída.** Epic #181: 4.1 `--json` (#196, PR #242), 4.2
  search com snippets/filtros (#197, PR #243), 4.3 exit codes/erros (#198,
  PR #244). Epic #182 skills v3 (#199/#200/#201, PR #245).
- **Fase 5 — ✅ 6/6 concluídas.** 5.1 Ask com follow-up (#190, PR #246), 5.2
  Streaming de tokens no Ask (#191, PR #248), 5.3 Citações clicáveis (#192,
  PR #247), 5.4 Grafo: filtros, busca e foco (#193, PR #249), 5.5 Grafo:
  layout performático + zoom/pan/fit (#194 + #252, merged together), 5.6
  Ingestão por URL (#195, PR #250). Epic #180 fechado.
- **Fase 6 — ✅ 7/7 concluídas (Epic #159 fechado).** 6.1 lint em lotes (#173,
  PR #254), 6.2 verificação pós-manutenção (#174, PR #255), 6.3 stats por
  modelo/provider (#176, PR #256), 6.4 auto-link (#44, PR #257), 6.5 dashboard
  de observabilidade (#151, PR #258), 6.6 concorrência do worker + ADR 001
  (#140, PR #259), 6.7 curador agendado (#41, PR #260).

main: 526 testes pytest verdes (+6 skip do caminho vec0, que rodam no CI
Linux), frontend vitest 81/81 + build da SPA, ruff + mypy strict limpos.
Issues concluídas fechadas via `Closes #N`.

> **Evals (#175):** não re-rodados nas histórias que mudaram prompt/fluxo
> (1.6, 2.3, 5.x, 6.1) — exigem modelo LLM configurado. Rodar `wiki evals run`
> antes/depois e anotar no PR quando houver credencial.

**Próximo: Fase 7 — Desktop Tauri: background & integração com o SO
(Epic #202: #203–#208).**

---

## FASE 0 — Medição antes de mexer

### 0.1 Harness de evals dos agentes — issue [#175](https://github.com/roger8b/llm-wiki-cli/issues/175)  ✅ **concluída** (PR #210)

**Por que primeiro:** as fases 1–2 mudam prompts, tools e fluxo de ingestão.
Sem baseline, não dá para saber se melhorou. Rode o harness ANTES e DEPOIS de
cada história das fases 1–2.

**Desenho:**
- Dataset versionado em `tests/evals/dataset/`: fonte curta (1 conceito),
  fonte rica (5+ conceitos), fonte longa (>20k chars), fonte duplicada
  (mesmo conceito de outra já ingerida), fonte com entidades. Cada fonte com
  `expected.json` (nº mínimo de páginas, títulos esperados, links esperados,
  tipos).
- Runner: cria brain descartável (tmpdir), ingere o dataset via
  `ingest_service.ingest` real (LLM configurado) ou com runner fake para CI.
- Métricas por run: páginas criadas vs esperadas, % links `[[...]]` que
  resolvem, % frontmatter válido (reusar `lint_structural`), fallback rate e
  tokens (de `ExecutionMeta`, já persistido).
- Saída: JSON em `evals/results/<timestamp>-<model>.json` + tabela no stdout.
- Entrada: comando `wiki evals run` (novo módulo
  `interfaces/cli/commands/evals.py`) ou script `scripts/run_evals.py` —
  preferir o comando CLI.

**Arquivos:** `src/llmwiki/services/evals_service.py` (novo),
`tests/evals/`, comando CLI, docs no README.

**Benefício final:** régua objetiva de qualidade dos agentes; habilita as
comparações da história 6.4.

---

## FASE 1 — Extração & ingestão de qualidade (Milestone "Agentes M1")

> Contexto comum: o agente de ingestão é montado em
> `src/llmwiki/llm_agents/factory.py::run_ingestion` com o prompt
> `src/llmwiki/llm_agents/prompts/ingestion.md`, tools read-only de
> `llm_agents/tools.py`, e escreve via staging do `ChangeRequestBackend`.
> A orquestração está em `src/llmwiki/services/ingest_service.py`.
> Extractors em `src/llmwiki/sources/extractors/`.

### 1.1 Extractor de PDF — issue [#160](https://github.com/roger8b/llm-wiki-cli/issues/160)  ✅ **concluída** (PR #209)

**Problema:** `.pdf` não tem extractor registrado; cai no fallback
`read_text(utf-8)` → lixo binário vai para o LLM.

**Desenho:** novo `sources/extractors/pdf.py` usando `pypdf` (extra
`[pdf]` no pyproject). Registrar em `_REGISTRY` no `__init__.py`. PDF sem
camada de texto (página retorna vazio) → levantar erro tipado claro
(`core/errors.py`), nunca devolver vazio silencioso. Preservar quebras de
parágrafo; juntar hifenização de fim de linha quando trivial.

**Testes:** PDF pequeno fixture em `tests/fixtures/`; caso sem texto.

**Benefício final:** papers e docs PDF entram no pipeline com texto real.

### 1.2 Extractor de HTML — issue [#161](https://github.com/roger8b/llm-wiki-cli/issues/161)  ✅ **concluída** (PR #218)

**Problema:** HTML bruto (nav, scripts, footer) inteiro vai para o prompt.

**Desenho:** `sources/extractors/html.py` com `trafilatura` (extra `[html]`).
Saída: conteúdo principal como markdown/texto. Capturar `<title>` e metatags
(og:title, author, date) — já no formato da história 1.4 (metadados).
Registrar `.html`/`.htm`.

**Benefício final:** artigos web viram texto limpo; pré-requisito da
ingestão por URL (5.6).

### 1.3 Metadados da fonte no pipeline — issue [#163](https://github.com/roger8b/llm-wiki-cli/issues/163)  ✅ **concluída** (PR #219)

**Problema:** só `source_path` + texto chegam ao agente; `sources` do
frontmatter fica pobre.

**Desenho:** mudar contrato dos extractors para retornar
`ExtractedSource { text: str, title: str|None, author: str|None, date:
str|None, url: str|None }` (dataclass em `sources/extractors/__init__.py`).
Manter `extract_text()` como wrapper compat. `run_ingestion` inclui os
metadados no bloco `FONTE:` da mensagem. Atualizar `prompts/ingestion.md`
para usá-los no frontmatter `sources`.

**Ordem:** fazer junto/logo após 1.1–1.2 (extractors novos já nascem no
contrato novo).

**Benefício final:** procedência rastreável em toda página gerada.

### 1.4 Data atual e contexto do workspace no prompt — issue [#164](https://github.com/roger8b/llm-wiki-cli/issues/164)  ✅ **concluída** (PR #211)

**Problema:** exemplo do prompt tem data fixa (`2026-05-21`); agente inventa
`updated_at`. Agente não conhece o estado da wiki (tipos, volume).

**Desenho:** renderizar o prompt como template (substituição simples de
`{{today}}`, `{{wiki_stats}}` em `factory._prompt` ou na montagem da
mensagem — preferir mensagem, prompt estático cacheável). `wiki_stats` =
contagem de páginas por tipo via `PageRepo.by_type` (conexão curta, padrão
de `tools.py`).

**Teste:** páginas staged em ingestão fake têm `updated_at` == hoje.

**Benefício final:** frontmatter confiável sem revisão manual.

### 1.5 Prompt orienta exploração do grafo + tool `related_pages` — issue [#165](https://github.com/roger8b/llm-wiki-cli/issues/165)  ✅ **concluída** (PR #220)

**Problema:** `get_backlinks`/`read_metadata` existem mas o prompt de
ingestão não as menciona; linkagem entre páginas novas e existentes é fraca.

**Desenho:** nova tool `make_related_pages(paths)` em `llm_agents/tools.py`:
recebe título proposto, combina busca FTS pelo título/slug + páginas com
links em comum, retorna candidatos com path/título/tipo. Atualizar
`prompts/ingestion.md`: passo obrigatório de exploração
(search → read_metadata → get_backlinks/related_pages) ANTES de escrever.

**Medição:** rodar evals (0.1) antes/depois — métrica de links válidos por
página deve subir.

**Benefício final:** wiki vira grafo denso e navegável em vez de ilhas.

### 1.5b Extractor de áudio (transcrição batch offline) — issue [#76](https://github.com/roger8b/llm-wiki-cli/issues/76)  ✅ **concluída** (PR #221)

**Problema:** reuniões/palestras/notas de voz não têm caminho para o pipeline
(a POC original de STT foi reescrita como extractor de primeira classe).

**Desenho:** `sources/extractors/audio.py` com **faster-whisper** (extra
`[audio]`, import lazy, CPU/int8 default). Saída no contrato
`ExtractedSource` (1.3) com timestamps `[hh:mm:ss]` a cada ~60s como âncoras
de citação. Config: `whisper_model` (default `small`), `whisper_language`
(None = autodetect). Registrar `.mp3/.wav/.m4a/.ogg/.flac`. Transcrição é
lenta: mover o `extract` para DENTRO do job (depois de `job_repo.create`) e
reportar `set_progress("transcribing")`. Transcrição longa cai naturalmente
no multi-pass (1.6).

**Benefício final:** conhecimento falado (reuniões!) vira páginas da wiki,
100% offline.

### 1.6 Chunking / ingestão multi-pass para fontes longas — issue [#162](https://github.com/roger8b/llm-wiki-cli/issues/162)  ✅ **concluída** (PR #225)

**Problema:** `source_text` inteiro numa mensagem; estoura `num_ctx`
(Ollama) e degrada decomposição.

**Desenho (a maior história da fase — fazer por último):**
- Limiar `chunk_threshold_chars` + `chunk_size`/`chunk_overlap` no
  `WorkspaceConfig` (`core/config.py`), com defaults sensatos.
- Em `ingest_service.ingest`: se `len(text) > threshold`, fluxo multi-pass:
  1. **Passe outline**: agente (sem backend de escrita, read-only) recebe o
     texto resumido por chunks e devolve lista de conceitos esperados
     (schema novo `OutlinePlan` em `llm_agents/models.py`).
  2. **Passes de chunk**: para cada chunk, `run_ingestion` com a mensagem
     incluindo o outline + chunk; **reutilizar o MESMO
     `ChangeRequestBackend`** entre passes — o overlay de staging já faz o
     agente do chunk N ver as páginas do chunk N-1 (evita duplicata
     intra-fonte).
  3. Um único CR no final (`collect_changes` agregado).
- Telemetria: somar `ExecutionMeta` dos passes (tokens, latency) no
  `execution` do CR.
- `job_repo.set_progress` por passe (`chunk 2/5`) — o front já mostra
  progresso via SSE.
- Fonte curta: caminho atual intocado (teste de regressão).

**Benefício final:** transcrições e livros inteiros viram conhecimento sem
perda de conceitos.

### 1.7 Guardrail de duplicata semântica — issue [#167](https://github.com/roger8b/llm-wiki-cli/issues/167)  ✅ **concluída** (PR #222, #223)

**Problema:** nada impede `concepts/rag.md` + novo
`concepts/retrieval-augmented-generation.md`.

**Desenho:** no `ChangeRequestBackend.write`, quando `operation` seria
`create` (arquivo não existe no disco nem no staging): comparar
slug/título contra páginas existentes — slug normalizado (reusar
`core/markdown.slugify`) com distância de edição baixa OU hit forte de FTS
no título → retornar `WriteResult(error=...)` com os candidatos e instrução
"edite a existente ou justifique com outro nome". Adicionar nota no prompt.
Escape hatch: o agente pode reescrever com o mesmo path após ler a página
candidata (segunda tentativa no mesmo path staged passa).

**Cuidado:** falso positivo bloqueia ingestão legítima — limiar conservador,
logar toda recusa.

**Benefício final:** um conceito = uma página; o valor da wiki composta.

### 1.8 Loop de auto-correção pré-CR — issue [#166](https://github.com/roger8b/llm-wiki-cli/issues/166)  ✅ **concluída** (PR #226)

**Problema:** staging vira CR sem validação; erros estruturais chegam ao
revisor.

**Desenho:**
- Extrair de `lint_service.lint_structural` uma função
  `lint_contents(files: dict[str, str], existing_titles) -> list[LintFinding]`
  que valida conteúdos em memória (frontmatter, type válido, links resolvendo
  contra disco+staging). Reusar no lint atual (sem duplicar lógica).
- Em `ingest_service.ingest`, após o primeiro `runner(...)`: lintar
  `backend.staging`. Se houver findings, re-invocar o agente com mensagem
  "corrija estes problemas: …" (máx `agent_fix_retries` no config, default 1–2),
  reutilizando o mesmo backend.
- Findings restantes: anexar ao meta do CR (campo `warnings`) — o front
  exibirá na história 3.3.

**Benefício final:** revisor olha conteúdo, não formato; menos CRs rejeitados.

### 1.9 Score de qualidade por página no CR — issue [#168](https://github.com/roger8b/llm-wiki-cli/issues/168)  ✅ **concluída** (PR #212)

**Desenho:** função heurística pura em `core/` (sem LLM): tamanho do corpo,
nº de wikilinks válidos, frontmatter completo, presença de seções. Resultado
(`score` 0–100 + `flags: list[str]`) anexado a cada `FileChange` em
`collect_changes()` (modelo em `core/models.py`) e persistido no CR.
Exibição: CLI `wiki review <id>` mostra score por arquivo; front na 3.3.

**Benefício final:** revisor prioriza o que está fraco; insumo para a skill
wiki-review (4.6).

---

## FASE 2 — Recuperação semântica & query (Milestone "Agentes M2")

> Contexto comum: `src/llmwiki/search/service.py` já define os protocolos
> `EmbeddingProvider`/`VectorStore` e `hybrid_search` — sem implementação.
> FTS5 real em `db/repo.py::PageFtsRepo`. Reindex em
> `services/index_service.py`.

### 2.1 `search_pages` com snippets — issue [#171](https://github.com/roger8b/llm-wiki-cli/issues/171)  ✅ **concluída** (PR #227)

**Por que primeiro:** barato, melhora todos os agentes imediatamente, e a
fase 4 (CLI) reusa.

**Desenho:** `PageFtsRepo.search` passa a retornar snippet via função FTS5
`snippet(pages_fts, ...)` (1–2 linhas, marcador de highlight). Atualizar
`make_search_pages` em `llm_agents/tools.py` para incluir o snippet na
saída. Limites configuráveis.

**Benefício final:** agente escolhe a página certa sem abrir várias —
menos tokens, menos latência em TODA operação.

### 2.2 Busca semântica local — issue [#169](https://github.com/roger8b/llm-wiki-cli/issues/169)  ✅ **concluída** (PR #228)

**Desenho:**
- Extra `[semantic]`: `sqlite-vec` (vetores dentro do mesmo SQLite do brain,
  local-first — NÃO adicionar serviço externo) + embeddings via provider já
  configurado (Ollama `embed`, OpenAI, etc. — módulo
  `search/embeddings.py` com o mesmo padrão de lazy import de
  `factory._build_remote`).
- Tabela `page_vectors(path, chunk_idx, embedding)` + hash do conteúdo para
  invalidação. Popular no `reindex` (index_service) — embed só de páginas
  cujo hash mudou.
- Implementar `VectorStore` sobre sqlite-vec; plugar em `hybrid_search`
  (normalizar scores keyword vs semantic — RRF é suficiente).
- Sem provider de embedding configurado: tudo funciona como hoje (FTS puro).
- Config: `embedding_model` no `WorkspaceConfig` (None = desligado).

**Benefício final:** achar conhecimento por significado — alimenta dedup
(1.7), query e a busca do app (3.6).

### 2.3 Tool `hybrid_search` para os agentes — issue [#170](https://github.com/roger8b/llm-wiki-cli/issues/170)  ✅ **concluída** (PR #229)

**Depende de:** 2.1 e 2.2.

**Desenho:** upgrade de `make_search_pages` para chamar
`search.service.hybrid_search` quando a camada semântica está configurada
(fallback transparente para FTS). Saída indica origem
(`keyword|semantic`) e score. Atualizar prompts de ingestão/query para
mencionar a busca por significado.

**Benefício final:** dedup e linkagem do agente de ingestão melhoram sem
nenhum outro código mudar.

### 2.4 Validação de citations — issue [#172](https://github.com/roger8b/llm-wiki-cli/issues/172)  ✅ **concluída** (PR #213)

**Desenho:** pós-processamento em `services/query_service.ask`: para cada
`Citation`, resolver `page` contra páginas indexadas (`PageRepo`) e `source`
contra `raw/**`. Adicionar campo `invalid: bool = False` ao modelo
`Citation` (`llm_agents/models.py`). Logar + contar em telemetria
(estender `ExecutionMeta` ou meta do history). CLI e front exibem distinção
(front detalha na 5.3).

**Benefício final:** respostas do `wiki ask` auditáveis; zero citação
fantasma.

---

## FASE 3 — Revisão & edição no app (Milestone "App M4")

> Contexto comum: front em `ui/`. Review em `ui/src/views/ReviewView.tsx` +
> store `ui/src/stores/crs.ts`. Wiki em `ui/src/views/WikiView.tsx`. API
> client `ui/src/lib/api.ts`. Routers FastAPI em
> `interfaces/api/routers/` (`changes.py`, `wiki.py`, `search.py`).
> CRs no backend: `services/change_request_service.py`.

### 3.1 Edit before apply — issue [#183](https://github.com/roger8b/llm-wiki-cli/issues/183)  ✅ **concluída** (PR #214)

**Problema:** o botão existe em `ReviewView.tsx` SEM `onClick` (feature
morta; atalho ⌘E anunciado e não tratado).

**Desenho:**
- Backend: endpoint `PATCH /changes/{cr_id}/files` (body: `{path,
  new_content}`) em `routers/changes.py` → função nova em
  `change_request_service` que valida status `pending_review`, roda
  `validate_change_path`, regenera diff (`core/diff.make_diff`) e marca
  `edited_by_reviewer: true` no meta.
- Front: na aba `after`, botão Edit troca o `MonoBlock` por textarea
  (suficiente; CodeMirror é opcional) com Save/Cancel. Save → PATCH →
  refetch do CR. Ligar o `onClick` do botão existente e o handler ⌘E no
  efeito de teclado já presente.

**Benefício final:** CR 90% bom é consertado em 30s em vez de rejeitado e
re-gerado (outra chamada LLM).

### 3.2 Apply/reject parcial por arquivo — issue [#184](https://github.com/roger8b/llm-wiki-cli/issues/184)  ✅ **concluída** (PR #230)

**Desenho:**
- Semântica escolhida: apply parcial aplica os paths enviados e marca os
  demais como rejeitados (CR settled de uma vez — estado simples). Documentar
  no docstring do service.
- Backend: `POST /{cr_id}/apply` aceita body opcional `{paths: [...]}`;
  `change_request_service.apply` filtra changes. Reindex/log só do aplicado.
- CLI: `wiki apply <cr-id> --only <path>` (repetível) em
  `interfaces/cli/commands/review.py`.
- Front: checkbox por arquivo na lista do `CrDetail`; botão vira
  "Apply selected (n)" quando há seleção parcial.

**Benefício final:** uma página ruim não bloqueia as quatro boas da mesma
ingestão — throughput de revisão sobe.

### 3.3 Telemetria e qualidade do CR na revisão — issue [#185](https://github.com/roger8b/llm-wiki-cli/issues/185)  ✅ **concluída** (PR #231)

**Depende de:** 1.9 (score) já dá mais valor, mas o `execution` meta
(modelo, tokens, latência, fallback — issues #130/#136, já implementadas)
pode ser exibido imediatamente.

**Desenho:** header do `CrDetail` ganha linha discreta: modelo, tokens
in/out, latência, badge amarelo se `used_fallback`. Lista de arquivos mostra
`confidence` (já vem no `FileChange`) e flags/score de 1.9. Warnings de
auditoria (1.8) em banner.

**Benefício final:** confiança calibrada antes de ler o diff.

### 3.4 Editor de página com preview — issue [#186](https://github.com/roger8b/llm-wiki-cli/issues/186)  ✅ **concluída** (PR #232)

**Desenho:**
- Backend: endpoint `POST /wiki/pages/{path}/propose-edit` (ou reuso do
  fluxo: montar `ChangeRequestBackend`, `backend.write(path, content)`,
  `create_from_changes` com summary "Manual edit: <título>" — exatamente o
  padrão de `query_service.promote_answer`).
- Front: botão Edit no header da página do `WikiView` → editor markdown
  com preview lado a lado (`MarkdownReader` já renderiza). Frontmatter como
  campos de formulário (title, type select, tags, confidence) + corpo no
  textarea. Autocomplete de `[[` usando a lista de páginas já carregada
  (`titleMap` existente).
- Salvar → CR → toast com link para Review (padrão do delete já existente).

**Benefício final:** curadoria manual sem sair do app — corrige na hora o
que a revisão encontrou.

### 3.5 Criar página com template — issue [#187](https://github.com/roger8b/llm-wiki-cli/issues/187)  ✅ **concluída** (PR #233)

**Depende de:** 3.4 (reusa o editor).

**Desenho:** ação "New page" no `WikiView` e no `CommandPalette`
(`ui/src/components/layout/CommandPalette.tsx`). Dialog: tipo (select),
título, tags → carrega template de `templates/page_templates/` (expor via
endpoint GET) → abre o editor de 3.4 pré-preenchido. Path =
`wiki/<dir-do-tipo>/<slug>.md`; avisar colisão de slug.

**Benefício final:** decisões e conceitos manuais entram com frontmatter
correto sem CLI.

### 3.6 Busca global FTS no app — issue [#188](https://github.com/roger8b/llm-wiki-cli/issues/188)  ✅ **concluída** (PR #234)

**Depende de:** 2.1 (snippets). Usa híbrida automaticamente se 2.2 ativa.

**Desenho:** `CommandPalette` (⌘K) ganha modo busca de conteúdo: digitar
consulta → chamar endpoint de search (já existe router `search.py`;
garantir que retorna snippets) → resultados com highlight agrupados por
tipo; Enter abre a página no `WikiView`.

**Benefício final:** achar conhecimento sem lembrar título — requisito
básico de uma wiki que cresce.

### 3.7 Navegação por tags — issue [#189](https://github.com/roger8b/llm-wiki-cli/issues/189)  ✅ **concluída** (PR #235)

**Desenho:** endpoint `GET /wiki/tags` (tag, count) + filtro
`GET /wiki/pages?tag=` (tags já estão no índice — verificar
`index_service`/`PageRepo`; persistir se necessário). Front: chips de tag
clicáveis no header da página → filtra a sidebar; seção "Tags" na sidebar.

**Benefício final:** exploração transversal aos diretórios de tipo.

---

## FASE 4 — CLI & skills para agentes externos (Milestone "Agentes M6")

> Contexto comum: CLI Typer em `src/llmwiki/interfaces/cli/` (comandos em
> `commands/`). Skills em `src/llmwiki/skills/*/SKILL.md`, instaladas pelo
> fluxo v2 (`services/skills_service.py`, registry em `core/agents.py`).

### 4.1 `--json` nos comandos de leitura — issue [#196](https://github.com/roger8b/llm-wiki-cli/issues/196)

**Desenho:** opção `--json` em `search`, `review` (lista e detalhe), `lint`,
`jobs`, `ask`, `log`. Os schemas Pydantic já existem
(`core/models.py`, `llm_agents/models.py`) — serializar com
`model_dump_json`. Regra dura: com `--json`, stdout contém SÓ o JSON;
qualquer log/aviso vai para stderr. Helper compartilhado
(`interfaces/cli/_output.py`). Documentar schema em `docs/`.

**Benefício final:** agentes externos param de parsear tabelas Rich —
integração robusta.

### 4.2 `wiki search` com snippets e filtros — issue [#197](https://github.com/roger8b/llm-wiki-cli/issues/197)

**Depende de:** 2.1 (snippets no repo FTS); usa 2.2 se configurada.

**Desenho:** `commands/wiki.py::search` ganha `--type`, `--tag`, `--limit`,
`--keyword-only`; chama `search.service.hybrid_search`. Saída humana mostra
snippet com highlight; `--json` inclui score e origem.

**Benefício final:** base do modo retrieval (4.4) — a forma mais barata de
um agente usar a wiki.

### 4.3 Exit codes e erros padronizados — issue [#198](https://github.com/roger8b/llm-wiki-cli/issues/198)

**Desenho:** mapa central exceção→exit code em `interfaces/cli/main.py`
(handler único): 0 ok, 2 uso inválido, 3 não encontrado, 4
conflito/duplicado (`SourceAlreadyProcessedError`), 5 erro de provider/LLM,
130 cancelado. Com `--json`, erro vira
`{"error": {"code": "...", "message": "..."}}` em stderr. Tabela documentada
em `docs/`.

**Benefício final:** agente trata "fonte duplicada" programaticamente em vez
de adivinhar pelo texto.

### 4.4 Modo retrieval na skill wiki-query — issue [#199](https://github.com/roger8b/llm-wiki-cli/issues/199)

**Depende de:** 4.1, 4.2.

**Desenho:** reescrever `skills/wiki-query/SKILL.md`: caminho padrão =
`wiki search --json` → escolher páginas → `wiki page open <path>` → o
PRÓPRIO agente sintetiza citando as páginas. `wiki ask` rebaixado a
ferramenta para síntese complexa multi-página ou quando o chamador quer a
resposta pronta. Guardrails mantidos (citar páginas, não inventar, dizer
quando a wiki não cobre). Validar com run real (Claude Code) comparando
tokens/latência vs `wiki ask`.

**Benefício final:** consumo da wiki por agentes fica ~2× mais barato e
rápido (elimina o segundo LLM).

### 4.5 Skills documentam jobs, --json e erros — issue [#200](https://github.com/roger8b/llm-wiki-cli/issues/200)

**Desenho:** nas 3 SKILL.md: seção "Long-running jobs" (`wiki jobs`,
acompanhar/cancelar), seção "Errors" (códigos de 4.3 + ação recomendada —
ex.: exit 4 em ingest = fonte já processada, só re-ingerir com `--force` se
o usuário pedir), exemplos migrados para `--json`. Bump de versão das
skills para o updater v2 propagar.

**Benefício final:** agentes não ficam perdidos em ingestões longas nem
repetem operações que já falharam.

### 4.6 Nova skill wiki-review — issue [#201](https://github.com/roger8b/llm-wiki-cli/issues/201)

**Depende de:** 4.1 (review --json); melhor com 1.9/3.3 (score).

**Desenho:** `skills/wiki-review/SKILL.md`: workflow = `wiki review --json`
(lista) → para cada CR pendente, ler diff e meta → classificar em
**apply / needs-attention / reject** com justificativa de 1 linha cada →
apresentar tabela ao usuário. REGRA: a skill recomenda; só aplica/rejeita
com confirmação explícita do usuário no chat. Registrar no instalador
(mesma estrutura das outras três).

**Benefício final:** o gargalo humano ganha um triador automático — fila de
20 CRs vira 5 minutos de decisões.

---

## FASE 5 — Ask conversacional, grafo & captura (Milestone "App M5")

### 5.1 Ask com follow-up — issue [#190](https://github.com/roger8b/llm-wiki-cli/issues/190)

**Desenho:**
- Backend: `POST /ask` aceita `conversation_id` opcional; history
  (`ask_history`, router `ask.py`) ganha coluna `conversation_id`
  (migração em `db/migrations/`). `query_service.ask` monta a mensagem com
  os turns anteriores (janela: últimos N turns ou M chars, config).
  Backend continua `read_only=True`.
- Front: `AskView` vira thread (perguntas/respostas empilhadas, input fixo
  embaixo, botão "New conversation"). Store `ask.ts` guarda
  `conversationId`. Histórico agrupado por conversa.

**Benefício final:** aprofundar um tema sem re-contextualizar — o app vira
interface de diálogo com o conhecimento.

### 5.2 Streaming de tokens no Ask — issue [#191](https://github.com/roger8b/llm-wiki-cli/issues/191)

**Desenho:** o worker (`workers/runner.py`) publica chunks no canal SSE já
existente (`GET /jobs/{job_id}/events`) com evento novo `token`. No agente:
usar streaming do LangChain (callback/astream_events) — encanar só o texto
da resposta final, não os tool calls. Front: `AskView` renderiza markdown
incremental (cuidado com markdown parcial — re-render do bloco corrente).
Fallback: provider sem stream → comportamento atual. Cancelamento
(`cancelJob`) continua funcionando no meio.

**Benefício final:** percepção de velocidade; perguntas longas deixam de
parecer travadas.

### 5.3 Citações clicáveis — issue [#192](https://github.com/roger8b/llm-wiki-cli/issues/192)

**Depende de:** 2.4 (campo `invalid`).

**Desenho:** `AskView` renderiza `citations` como cards/footnotes: `page` →
navega `WikiView` (padrão `?q=` já existe), `source` em `raw/` → abre
leitor da `SourcesView` (endpoint `/sources/content` já existe), `quote` em
popover. Citação `invalid` riscada com tooltip.

**Benefício final:** confiança verificável em um clique.

### 5.4 Grafo: filtros, busca e foco — issue [#193](https://github.com/roger8b/llm-wiki-cli/issues/193)

**Desenho:** em `GraphView.tsx`: legenda de tipos vira toggles; campo de
busca de nó (highlight + pan até o nó); clique em nó = modo foco
(vizinhança a 1–2 saltos via BFS nas edges, resto com opacity baixa);
duplo clique abre a página. Filtro por tag se o endpoint `/wiki/graph`
expuser tags nos nós (adicionar).

**Benefício final:** grafo vira ferramenta de exploração real.

### 5.5 Grafo: layout performático — issue [#194](https://github.com/roger8b/llm-wiki-cli/issues/194)

**Desenho:** substituir o force-layout hand-rolled O(n²)/350-iterações por
`d3-force` rodando em Web Worker; render em `<canvas>` quando nós > ~300
(SVG abaixo disso é ok). Cachear posições por path em
localStorage/zustand persist; re-layout incremental só de nós novos.
Medir com wiki sintética de 1000 páginas antes/depois.

**Benefício final:** view utilizável em wikis grandes — onde grafo mais
importa.

### 5.6 Ingestão por URL — issue [#195](https://github.com/roger8b/llm-wiki-cli/issues/195)

**Depende de:** 1.2 (extractor HTML), 1.3 (metadados).

**Desenho:**
- Core: `sources/manager.py` ganha `add_url(url)`: download (httpx, já
  dependência? verificar — senão extra), extração via extractor HTML,
  salvar `raw/web/<slug>.md` com frontmatter da captura (url, título, data).
- CLI: `wiki source add --url <url>` (`commands/source.py`).
- API: `POST /sources/url`; front: campo URL na `SourcesView` + entrada no
  CommandPalette, com preview (título + primeiras linhas) antes de
  confirmar.
- Erros claros: 404, paywall (conteúdo extraído < limiar), timeout.

**Benefício final:** captura da web em um passo — o atrito de alimentar o
brain cai para perto de zero.

---

## FASE 6 — Qualidade contínua (Milestone "Agentes M3", restante)

### 6.1 Lint semântico em lotes — issue [#173](https://github.com/roger8b/llm-wiki-cli/issues/173)

**Desenho:** em vez de `run_lint` mandar "audite a wiki", o
`lint_service` particiona as páginas (por diretório de tipo; depois por
cluster de links se necessário) e roda um agente por lote com a LISTA
EXPLÍCITA de páginas na mensagem. Orçamento: `lint_token_budget` no config;
lotes que não couberem são adiados e reportados. Passe final determinístico
de dedup de findings (mesmo kind+pages). `wiki lint --scope <dir>` para
subconjunto.

**Benefício final:** auditoria com custo previsível e cobertura garantida,
em qualquer tamanho de wiki.

### 6.2 Verificação pós-manutenção — issue [#174](https://github.com/roger8b/llm-wiki-cli/issues/174)

**Depende de:** 1.8 (`lint_contents` em memória).

**Desenho:** em `maintenance_service`: após `run_maintenance` propor fixes,
rodar `lint_contents` sobre disco+staging e comparar com os findings de
entrada. Não resolvidos → re-invocar agente (máx N tentativas) → restantes
listados como `unresolved` no meta do CR. `MaintenanceResult.fixed` passa a
ser validado, não autodeclarado.

**Benefício final:** CR de manutenção que você aplica de olhos fechados.

### 6.3 Relatório comparativo por modelo — issue [#176](https://github.com/roger8b/llm-wiki-cli/issues/176)

**Desenho:** agregação SQL sobre os `execution` meta já persistidos em
jobs/CRs: por modelo → tokens médios, latência média, taxa de fallback,
taxa de CR fantasma. CLI `wiki jobs stats [--json]` + endpoint
`GET /jobs/stats` (o dashboard da issue #151 consome depois). Integrar com
evals (0.1) para A/B de modelos.

**Benefício final:** escolha de modelo por dado, não por fé.

### 6.4 Auto-link de menções plain-text — issue [#44](https://github.com/roger8b/llm-wiki-cli/issues/44)

**Desenho:** `services/autolink_service.py` **determinístico, sem LLM**:
match case-insensitive de títulos existentes no corpo (≥ 4 chars, word
boundaries; só a primeira ocorrência por título/página), excluindo
frontmatter, code, URLs, headings, links existentes e self-link; match mais
longo vence. Resultado sanity-checked com `lint_contents` (1.8) e proposto
como UM CR. CLI `wiki autolink [--scope] [--dry-run] [--json]`. Revisão (com
apply parcial, 3.2) é o controle de falso positivo.

**Benefício final:** o estoque de páginas ganha densidade de grafo
retroativamente — complementa 1.5, que só cobre páginas novas.

### 6.5 Dashboard de observabilidade no app — issue [#151](https://github.com/roger8b/llm-wiki-cli/issues/151)

**Depende de:** 6.3 (endpoint `GET /jobs/stats`).

**Desenho:** view nova `/observability` ("Insights" no nav): cards de resumo
por período (runs, tokens, custo, fallback %, rejeição %), tabela por modelo
(payload de 6.3) e atividade recente com link para o CR. Sem lib de chart
nova (SVG/CSS) salvo justificativa no PR. Fetch on mount + refresh manual.

**Benefício final:** saúde/custo/qualidade do pipeline visíveis sem `jq`.

### 6.6 Concorrência do worker (ADR + implementação) — issue [#140](https://github.com/roger8b/llm-wiki-cli/issues/140)

**Executar após 1.6** (multi-pass muda o perfil dos jobs — medir com ele).

**Desenho:** investigação com protótipos (A: pool de N threads + WAL;
B: read/write split — asks paralelos sempre, writes serializados;
C: single-thread + ask fura fila) → `docs/adr/NNN-worker-concurrency.md`
com medições → implementar a vencedora atrás de `worker_concurrency: int = 1`
(default = comportamento atual byte a byte). Garantias: dois jobs nunca
escrevem o mesmo path; cancelamento/SSE por job preservados.

**Benefício final:** perguntar durante uma ingestão longa deixa de enfileirar.

### 6.7 Curador agendado — issue [#41](https://github.com/roger8b/llm-wiki-cli/issues/41)

**Depende de: 6.1 (#173), 6.2 (#174) e 6.4 (#44). Última da fase — fecha o
ciclo.**

**Desenho:** camada FINA de orquestração `services/curator_service.py`:
lint em lotes → filtrar findings com CR pendente (`annotate_with_pending_crs`)
→ manutenção verificada → auto-link incremental (páginas tocadas desde
`last_curation_at`). Nunca aplica — só propõe CRs. Triggers: `wiki curate`
(+ endpoint, job com progresso) e scheduler no lifespan do backend
(`curation_interval_hours`, default desligado; sem cron de SO). Notificação
via 7.3 quando criar CRs. Custo herdado do orçamento de 6.1.

**Benefício final:** wiki se mantém limpa sozinha; o humano só revisa CRs.

---

## FASE 7 — Desktop Tauri: background & integração com o SO (Milestone "App M7")

> Contexto comum: shell Tauri 2 em `ui/src-tauri/` (`src/lib.rs` ~220 linhas,
> `tauri.conf.json`, capability `capabilities/default.json`). O shell sobe o
> sidecar Python (PyInstaller onedir) numa porta dinâmica, espera
> `/api/health`, abre a WebView (`WebviewUrl::External`) injetando o token de
> sessão. Hoje: fechar a janela encerra tudo e o backend morre com
> `child.kill()` (**SIGKILL**) — jobs em andamento morrem no meio.
> Decisão do epic: lógica de tray/notificação no lado **Rust** (sem
> `withGlobalTauri` até #207); plugins oficiais Tauri v2 sempre que existir.

### 7.1 Instância única + shutdown gracioso — issue [#203](https://github.com/roger8b/llm-wiki-cli/issues/203)

**Por que primeiro:** background (#204) multiplica o tempo de vida do sidecar
e precisa de ciclo de vida sólido antes.

**Desenho:** `tauri-plugin-single-instance` (registrar primeiro; segunda
instância foca a janela). Exit: SIGTERM → aguardar até 5s (`try_wait`) →
SIGKILL só como último recurso. Lockfile `<brain>/.llmwiki/server.lock`
(`{pid, port}`) escrito pelo backend; `kill_stray_backends` passa a usar o
lockfile (validando o nome do processo) em vez de `pkill -f`. Backend marca
jobs `running` órfãos como `interrupted` no startup pós-crash.

**Benefício final:** zero backends órfãos/duplicados; SQLite nunca mais leva
SIGKILL no meio de um write.

### 7.2 Rodar em background com tray — issue [#204](https://github.com/roger8b/llm-wiki-cli/issues/204)

**Desenho:** `WindowEvent::CloseRequested` → `prevent_close()` + hide;
`ActivationPolicy::Accessory` quando escondido (padrão menubar do macOS).
Tray (feature `tray-icon` do core): `Open llm-wiki` (reusa porta/token da
sessão via state `AppSession`; extrair helper `open_main_window`),
`Jobs running: N` (poll Rust a cada 15s em `/api/jobs` só quando escondido)
e `Quit` (dispara o shutdown de 7.1). Config `run_in_background` (default
true) com toggle no Settings; `RunEvent::Reopen` reabre a janela.

**Benefício final:** fechar a janela não cancela ingestões; a wiki vive a um
clique do tray.

### 7.3 Notificações nativas de jobs/CRs — issue [#205](https://github.com/roger8b/llm-wiki-cli/issues/205)

**Desenho:** `tauri-plugin-notification`; o poll de 7.2 mantém snapshot
`{job_id: status}` e notifica transições `running → done|failed`. Clique →
mostra a janela e navega (`window.eval("location.assign('/review')")` —
aceitável sem ponte Tauri). Suprimir quando a janela está focada. Toggle
`notify_on_jobs` no Settings.

**Benefício final:** background ganha valor — o usuário volta ao app na hora
certa, sem vigiar a janela.

### 7.4 Quick capture global — issue [#206](https://github.com/roger8b/llm-wiki-cli/issues/206)

**Depende de:** 7.2; modo URL depende de 5.6 (#195) — sem ele, lançar só
texto.

**Desenho:** `tauri-plugin-global-shortcut` (`Cmd+Shift+K`) abre janela
pequena always-on-top com rota nova `/capture` do front (fora do AppShell):
textarea pré-preenchida com o clipboard (`tauri-plugin-clipboard-manager`),
detecção automática URL vs texto, `Save source` (`POST /sources/text|url`) e
`Save & ingest` (enfileira o job; notificação de 7.3 avisa o fim). Esc fecha.

**Benefício final:** alimentar o brain de qualquer app em ~3 segundos — o
atrito de captura cai a quase zero.

### 7.5 Autostart no login — issue [#207](https://github.com/roger8b/llm-wiki-cli/issues/207)

**Desenho:** `tauri-plugin-autostart` (LaunchAgent) com arg `--hidden` (sobe
direto no tray, sem janela). Toggle "Start at login" (default **false**,
opt-in) no Settings — esta história habilita `withGlobalTauri` e expõe os
comandos `get_autostart`/`set_autostart` via `invoke` (ponte mínima e
auditável; capability atualizada).

**Benefício final:** brain sempre disponível (captura global, MCP, API) sem
lembrar de abrir nada.

### 7.6 Auto-update assinado — issue [#208](https://github.com/roger8b/llm-wiki-cli/issues/208)

**Desenho:** `tauri-plugin-updater` com chave própria (privada em GitHub
Actions secret, pública no `tauri.conf.json`); manifest `latest.json` nos
GitHub Releases; CI de release via `tauri-apps/tauri-action` em tag `v*`
(builda sidecar + app assinado + manifest). UX: check no startup + 24h +
item "Check for updates…" no tray; instalar só com confirmação e NUNCA
reiniciar com job rodando (gate em `/api/jobs?status=running`). Assinatura
inválida → recusa (`docs/SIGNING.md` cobre a parte macOS).

**Benefício final:** melhorias do pipeline chegam sozinhas, sem dmg manual.

## Mapa de dependências (resumo)

```
0.1 evals ───────────────┐ (medição para tudo da F1/F2)
1.1 pdf ─┐               │
1.2 html ┼→ 1.3 metadados┼→ 1.6 chunking
         │               │
1.4 data/contexto        │
1.5 related_pages        │
1.7 dedup semântico ←──── 2.2 (melhora, não bloqueia)
1.8 lint pré-CR ─→ 6.2 verificação manutenção
1.9 score ─→ 3.3 telemetria na revisão ─→ 4.6 skill wiki-review
2.1 snippets ─→ 2.3 tool híbrida, 3.6 busca app, 4.2 search CLI
2.2 semântica ─→ 2.3, (3.6, 4.2 opcionais)
2.4 citations ─→ 5.3 citações clicáveis
3.4 editor ─→ 3.5 criar página
4.1 --json ─→ 4.2 ─→ 4.4 retrieval skill; 4.1 ─→ 4.6
4.3 exit codes ─→ 4.5 skills documentadas
1.2+1.3 ─→ 5.6 ingestão por URL
1.1+1.3 ─→ 1.5b extractor de áudio (#76) ─→ ganha com 1.6 chunking
6.3 stats ─→ 6.5 dashboard (#151)
1.6 chunking ─→ 6.6 concorrência do worker (#140)
6.1 + 6.2 + 6.4 auto-link ─→ 6.7 curador agendado (#41)
7.1 lifecycle ─→ 7.2 tray ─→ 7.3 notificações, 7.4 capture, 7.5 autostart, 7.6 updater
5.6 URL ─→ 7.4 quick capture (modo URL)
```

## Issues arquivadas (decisão registrada — não implementar)

- [#74](https://github.com/roger8b/llm-wiki-cli/issues/74) STT em tempo real
  (vosk) — produto diferente; caso real coberto por 1.5b.
- [#46](https://github.com/roger8b/llm-wiki-cli/issues/46) pesquisa
  Swift-native — superseded pela Fase 7 (Tauri entrega tray/hotkey/updater).
- [#40](https://github.com/roger8b/llm-wiki-cli/issues/40) detecção de
  contradições por claims — lint semântico (6.1) já cobre o kind; reavaliar
  só se insuficiente.
- [#42](https://github.com/roger8b/llm-wiki-cli/issues/42) git sync,
  [#43](https://github.com/roger8b/llm-wiki-cli/issues/43) export site
  estático, [#75](https://github.com/roger8b/llm-wiki-cli/issues/75)
  diarization, [#77](https://github.com/roger8b/llm-wiki-cli/issues/77) STT
  cloud — parqueadas; reabrir sob demanda (75/77 só após 1.5b provar valor).

## Definição de pronto (toda história)

1. Critérios de aceite da issue atendidos (a issue é a fonte de verdade).
2. `ruff check` + `mypy` strict + `pytest` verdes; front: `npm test` e build.
3. Guardrails preservados: nenhum write fora do fluxo de CR; `raw/` imutável.
4. Para mudanças em prompts/agentes: evals (0.1) rodados antes/depois e
   resultado anotado no PR.
5. PR fecha a issue (`Closes #N`); docs/README atualizados quando o
   comportamento visível mudar.
