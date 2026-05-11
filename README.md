# llm-wiki

CLI for the Global LLM Wiki.

## Install

```bash
cd cli
npm install
npm run build
npm link
```

`llm-wiki` is now available globally.

## Commands

```bash
llm-wiki init [path] [--git] [--force]
llm-wiki doctor
llm-wiki source add <file> --type <type>
llm-wiki source list [--status <status>]
llm-wiki source status <source>
llm-wiki ingest prepare <source>
llm-wiki ingest commit <source>
llm-wiki search <query>
llm-wiki query prepare <question>
llm-wiki query save <file> --as <type> --title <title>
llm-wiki index rebuild
llm-wiki lint
llm-wiki page new <type> <title>
llm-wiki page validate <path>
llm-wiki links check
llm-wiki log add --type <type> --message <message>
```

## Wiki root resolution

The CLI looks for `wiki.config.yaml` walking upward from the current directory. Set `LLM_WIKI_ROOT` env var to override.
