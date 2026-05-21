# LLM Wiki Agent Protocol

## Objetivo
Manter uma wiki Markdown persistente, interligada e auditável.

## Regras
- Nunca editar arquivos em `raw/`.
- Sempre registrar operações em `wiki/log.md`.
- Sempre atualizar `wiki/index.md` ao criar/alterar páginas (via `llmwiki index`).
- Preferir atualizar páginas existentes antes de criar novas.
- Criar links internos com `[[Nome da Página]]`.
- Toda afirmação importante deve referenciar a fonte.
- Contradições devem ser marcadas explicitamente.
- Alterações são propostas como change request (diff) antes de aplicar.

## Tipos de página
`concept` | `entity` | `source_summary` | `synthesis` | `decision` | `project` | `research`

## Frontmatter padrão
`title`, `type`, `tags`, `sources`, `updated_at`, `confidence`
