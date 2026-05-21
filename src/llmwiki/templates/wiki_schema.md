# Wiki Schema

Convenções de estrutura das páginas da wiki.

## Tipos de página e diretórios
| Tipo | Diretório | Uso |
|---|---|---|
| `concept` | `wiki/concepts/` | Ideia, técnica, abstração. |
| `entity` | `wiki/entities/` | Pessoa, empresa, produto, ferramenta. |
| `source_summary` | `wiki/research/` | Resumo de uma fonte específica. |
| `synthesis` | `wiki/synthesis/` | Comparação/síntese de várias fontes. |
| `decision` | `wiki/decisions/` | Decisão tomada + alternativas rejeitadas. |
| `project` | `wiki/projects/` | Iniciativa em andamento. |
| `research` | `wiki/research/` | Nota de pesquisa exploratória. |

## Frontmatter obrigatório
```yaml
title: <título legível>
type: <um dos tipos acima>
tags: [..]
sources: [raw/...]
updated_at: YYYY-MM-DD
confidence: low | medium | high
```

## Links
Use `[[Título da Página]]` para links internos. O alvo é resolvido pelo título
ou pelo nome do arquivo.
