# AGENTS — como operar este brain

Este diretório é um brain do **llm-wiki**. Conhecimento mora em Markdown
(`wiki/`), fontes brutas em `raw/` (imutáveis), metadados em `.llmwiki/`.

## Princípios
- `raw/` é imutável: leia, nunca edite.
- O LLM **propõe** mudanças como change request; o humano revisa e aplica.
- `wiki/index.md` e `wiki/log.md` são gerados — não edite à mão.

## Comandos
- `llmwiki ingest <arquivo>` — ler uma fonte e propor mudanças.
- `llmwiki ask "<pergunta>"` — responder usando a wiki.
- `llmwiki lint` — auditar a saúde da base.
- `llmwiki index` — reconstruir índice e metadados.

Ver `WIKI_PROTOCOL.md` para as regras completas de manutenção.
