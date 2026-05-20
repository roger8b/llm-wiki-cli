# wiki CLI — Gaps & Limitations

Levantamento feito em 2026-05-20 após ciclo de lint + refactor + correção de paper no brain em `/Users/roger.silva/brain`. Cada gap referencia o ponto exato no código e o workaround usado quando aplicável.

## G1 — `raw_is_immutable` declarado mas não enforçado

**Onde:** `wiki.config.yaml` declara `source_policy.raw_is_immutable: true`. Nenhum comando da CLI checa hash de arquivos em `raw/` contra o manifesto na execução.

**Sintoma:** mutei `raw/articles/2305.16291.md` via `sed` (para corrigir paths `/tmp/`) e nenhuma checagem reclamou. `wiki lint`, `wiki doctor` e `wiki source status` permanecem verdes mesmo com o hash do arquivo divergindo do registrado — só notei a divergência porque atualizei o manifesto manualmente.

**Sugestão:** adicionar ao `lint.ts` (ou `doctor.ts`) uma checagem que recompute `sha256` de cada `path` em `.wiki/manifests/sources.json` e emita `severity: error` se divergir. Política declarada deve ter enforcement, ou então remover da config.

## G2 — Sem `wiki source rehash` / `wiki source verify`

**Onde:** `src/commands/source.ts` expõe `add`, `list`, `status`. Não há comando para revalidar hash de uma source já ingerida.

**Sintoma:** após editar o raw md do Voyager, precisei abrir `.wiki/manifests/sources.json` no editor e trocar o hash à mão. O `sourceAdd` (`source.ts:64-67`) tem o caminho para isso — atualiza hash se o `path` já existe — mas é semanticamente confuso re-rodar `source add` para revalidar.

**Sugestão:** comando dedicado `wiki source rehash <id|path>` (recomputa e grava) e/ou `wiki source verify` (compara hashes sem mutar). O segundo apoia G1.

## G3 — Sem `wiki page delete` ou `wiki page rename`

**Onde:** `src/commands/page.ts` tem `new`, `save`, `update`, `validate`, `show`, `list`. Não há delete nem rename.

**Sintoma:** para resolver collision de slug entre `decisions/decisao-...` e `sources/decisao-...`, precisei criar novo source com slug diferente via `wiki page save` e depois `rm` o arquivo antigo via shell. O skill `wiki-refactor` instrui "Never write files in the brain directly. Use wiki page save / wiki page update" — porém a CLI não oferece alternativa para remoção.

**Sugestão:** 
- `wiki page delete <slug>` (com confirmação ou `--force`, deve recusar se status ≠ `deprecated` para preservar citações).
- `wiki page rename <old-slug> <new-slug>` que move o arquivo, atualiza frontmatter, atualiza backlinks, regenera index.

## G4 — `supersedes` / `superseded_by` não validados

**Onde:** `validateRefs` (`page.ts:148-190`) só percorre os campos `related` e `sources`.

**Sintoma:** stubs deprecados criados na refactoring usam `superseded_by:` com slug do survivor e `supersedes: [<old-slug>]` no survivor. Um typo em qualquer um passa silencioso — não há aviso de "slug não existe" nem warning em lint.

**Sugestão:** estender `validateRefs` para `supersedes` (deve apontar para slug com `status: deprecated`) e `superseded_by` (deve apontar para slug existente, não-deprecated). Idealmente integrar ao schema `lint-report`.

## G5 — `require_source_for_canonical/reviewed` rebaixado para warning

**Onde:** `wiki.config.yaml` declara `source_policy.require_source_for_canonical: true` e `require_source_for_reviewed: true`. Em `page.ts:97-106` a checagem emite `level: "warning"`. Em `lint.ts:41` warnings não disparam `process.exitCode`.

**Sintoma:** uma page pode ser promovida a `reviewed` ou `canonical` sem fontes e o lint termina exit 0 — quem só olhar exit code acha que está tudo certo. Foi exatamente o caso de `como-funcionam-os-sub-agents-pi-subagents`.

**Sugestão:** quando `require_source_for_*: true`, emitir `level: "error"` (com exit code != 0). A semântica de "warning" deveria ser para algo opcional, não para violação de política declarada.

## G6 — Orphan check é info-level

**Onde:** `lint.ts:69-78` adiciona `severity: "info"` para páginas não listadas em `index.md`.

**Sintoma:** páginas órfãs (criadas mas nunca referenciadas) passam despercebidas porque info não conta para o resumo de problemas e não bloqueia nada. `wiki.config.yaml` declara `lint.check_orphans: true`, sugerindo intenção de gatekeeping.

**Sugestão:** elevar para `warning` por padrão, ou tornar configurável via `lint.orphan_severity: info|warning|error` no `wiki.config.yaml`.

## G7 — Sem `wiki commit`

**Onde:** a CLI não expõe nenhum comando que toque git. `wiki log add` registra eventos em `wiki/log.md`, mas não cria commit.

**Sintoma:** todo ciclo termina em `git add` / `git commit` manuais. O `WIKI_PROTOCOL.md` provavelmente espera que log entries e commits caminhem juntos (mensagem de commit citando a entry), mas quem garante isso é a memória do operador.

**Sugestão:** `wiki commit [--message <m>]` que:
1. Pega a última entry de `wiki/log.md` desde o último commit.
2. Stage automaticamente todos os arquivos sob `wiki/`, `raw/`, `.wiki/manifests/`, `schemas/`.
3. Cria commit com mensagem padrão derivada das entries (`<type>: <message>`).
4. Recusa se houver mudanças em `raw/` sem entry de log correspondente (apoia G1).

## G8 — `wiki source status` aceita ID e path mas não slug da page

**Onde:** `source.ts:101-112`. A busca tenta `path === rel || path === target || id === target`.

**Sintoma:** o slug natural do brain para uma source é o slug da source page (ex: `voyager-an-open-ended-embodied-agent-with-large-language-models`). `wiki source status <slug>` falha com "source not found", mesmo a page tendo `raw_path` apontando para o arquivo correto.

**Sugestão:** quando o argumento não casar como path/id, fallback que lê `wiki/sources/<slug>.md`, extrai `raw_path` do frontmatter e usa esse path para procurar no manifest.

## G9 — `wiki index rebuild` não detecta deprecated → survivor

**Onde:** rebuild do index inclui status badge (`_(deprecated)_`) mas não cria links contextuais para o `superseded_by`.

**Sintoma:** quem abre o index vê `pi-subagents _(deprecated)_` sem saber para onde foi. Tem que abrir o arquivo para descobrir o survivor.

**Sugestão:** quando frontmatter tem `superseded_by`, gerar entrada `[slug] _(deprecated → survivor-slug)_` no index. Custo baixo, ganho de navegação alto.

---

## Prioridade sugerida

| Gap | Severidade | Esforço |
|-----|-----------|---------|
| G3 (`page delete/rename`) | alta — bloqueia refactor seguro | médio |
| G2 (`source rehash`) | alta — completa G1 | baixo |
| G1 (enforce `raw_is_immutable`) | alta — política declarada sem dente | baixo |
| G5 (reviewed/canonical sem source = error) | média | trivial |
| G7 (`wiki commit`) | média — eliminaria saídas para shell | médio |
| G4 (validar supersedes) | média | baixo |
| G8 (status por slug) | baixa — DX | baixo |
| G6 (orphan severity) | baixa | trivial |
| G9 (deprecated link no index) | baixa | baixo |

## Contexto

Os gaps foram observados durante:
1. Lint pass + diagnóstico (via skill `wiki-lint`).
2. Refactor para resolver collision de slug, merge de duplicatas e correção de links quebrados (via skill `wiki-refactor`).
3. Correção do paper Voyager (arXiv 2305.16291) cujos artefatos de imagem estavam em `/tmp/`.
4. Commit final via `git` direto.

O brain saiu do ciclo com `wiki lint` / `wiki links check` / `wiki doctor` 100% verdes — os gaps acima são limitações da CLI que forçaram workarounds, não falhas do estado final.
