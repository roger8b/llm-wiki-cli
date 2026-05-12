#!/usr/bin/env node
import { Command } from "commander";
import pc from "picocolors";
import { bootstrapCmd } from "./commands/bootstrap.js";
import { doctorCmd } from "./commands/doctor.js";
import { sourceAdd, sourceList, sourceStatus } from "./commands/source.js";
import { pageNew, pageValidate, pageSave, pageUpdate } from "./commands/page.js";
import { indexRebuild } from "./commands/index.js";
import { searchCmd } from "./commands/search.js";
import { lintCmd } from "./commands/lint.js";
import { ingestPrepare, ingestCommit } from "./commands/ingest.js";
import { queryPrepare, querySave } from "./commands/query.js";
import { logAdd } from "./commands/log.js";
import { linksCheck } from "./commands/links.js";
import { projectInit } from "./commands/project.js";
import { configShow, configSetRoot, configClear } from "./commands/config.js";
import {
  protocolShow,
  schemaList,
  schemaShow,
  pageList,
  pageShow,
  indexShow,
  logShow,
  sourceShow,
  ingestContextShow,
  queryContextShow,
} from "./commands/read.js";

const program = new Command();
program
  .name("wiki")
  .description("CLI for your brain (Global LLM Knowledge Base)")
  .version("0.2.0");

program
  .command("init [path]")
  .description("wire a project to the brain — interactive agent setup (default: cwd)")
  .option("--wiki <path>", "brain root (uses global config / $LLM_WIKI_ROOT otherwise)")
  .option("--force", "overwrite / re-append even if wiki section already present")
  .option("-y, --yes", "non-interactive: install claude-code with copy method")
  .action((p, o) => projectInit(p, o));

program
  .command("bootstrap [path]")
  .description("create the brain and register it globally (run once per machine)")
  .option("--git", "initialize git in the brain root")
  .option("--force", "overwrite existing files")
  .option("--register", "force registration as the global brain")
  .option("--no-register", "skip global registration")
  .action((p, o) => bootstrapCmd(p, o));

const config = program.command("config").description("manage global config");
config.command("show").action(configShow);
config.command("set-root <path>").description("register the global brain root").action(configSetRoot);
config.command("clear").description("clear global config").action(configClear);

program.command("doctor").description("validate brain structure").action(doctorCmd);

// ── read-only navigation (no paths needed) ───────────────────────────────────

program.command("protocol").description("show the brain protocol").action(protocolShow);

const schema = program.command("schema").description("schema operations");
schema.command("list").description("list available page-type schemas").action(schemaList);
schema.command("show <type>").description("show a schema by type").action(schemaShow);

// ── sources ──────────────────────────────────────────────────────────────────

const source = program.command("source").description("manage raw sources");
source
  .command("add <file>")
  .description("register a file as a brain source (copies into raw/)")
  .option("--type <type>", "source type", "article")
  .action(sourceAdd);
source.command("list").description("list registered sources").option("--status <status>").action(sourceList);
source.command("status <source>").description("show source metadata").action(sourceStatus);
source.command("show <source>").description("print a raw source file content").action(sourceShow);

// ── ingest ───────────────────────────────────────────────────────────────────

const ingest = program.command("ingest").description("ingestion workflow");
ingest.command("prepare <source>").description("write ingest context for the agent").action(ingestPrepare);
ingest.command("context").description("show the current ingest context").action(ingestContextShow);
ingest.command("commit <source>").description("validate and mark source as ingested").action(ingestCommit);

// ── query ────────────────────────────────────────────────────────────────────

const query = program.command("query").description("query workflow");
query.command("prepare <question>").description("write query context for the agent").action(queryPrepare);
query.command("context").description("show the current query context").action(queryContextShow);
query
  .command("save <file>")
  .description("save a durable answer into the brain")
  .requiredOption("--as <type>", "page type (synthesis, comparison, ...)")
  .requiredOption("--title <title>", "page title")
  .action(querySave);

program
  .command("search <query>")
  .description("full-text search across brain pages")
  .option("--type <type>")
  .option("--status <status>")
  .action(searchCmd);

// ── index ────────────────────────────────────────────────────────────────────

const idx = program.command("index").description("index management");
idx.command("show").description("print the brain index").action(indexShow);
idx.command("rebuild").description("regenerate the index from current pages").action(indexRebuild);

program.command("lint").description("audit brain health").action(lintCmd);

// ── pages ────────────────────────────────────────────────────────────────────

const page = program.command("page").description("page operations");
page.command("list").description("list pages").option("--type <type>").option("--status <status>").action(pageList);
page.command("show <slug>").description("print a page by slug").action(pageShow);
page.command("new <type> <title>").description("scaffold a new page from schema").action(pageNew);
page
  .command("save")
  .description("create a page from a content file or stdin (no path needed)")
  .requiredOption("--type <type>", "page type (concept, decision, synthesis, …)")
  .requiredOption("--title <title>", "page title")
  .option("--file <path>", "content file (omit or use '-' for stdin)")
  .option("--status <status>", "status (default: draft)")
  .option("--force", "overwrite if a page with the same slug exists")
  .action((o) => pageSave(o));
page
  .command("update <slug>")
  .description("replace content of an existing page (preserves frontmatter)")
  .option("--file <path>", "content file (omit or use '-' for stdin)")
  .option("--status <status>", "new status")
  .action((slug, o) => pageUpdate(slug, o));
page.command("validate <path>").description("validate a page's frontmatter").action(pageValidate);

const links = program.command("links").description("link operations");
links.command("check").description("check for broken internal links").action(linksCheck);

// ── log ──────────────────────────────────────────────────────────────────────

const log = program.command("log").description("log operations");
log.command("show").description("print the brain log").option("--last <n>", "show last N entries").action(logShow);
log
  .command("add")
  .description("append an entry to the log")
  .requiredOption("--type <type>", "operation type")
  .requiredOption("--message <message>", "log message")
  .action(logAdd);

program.parseAsync(process.argv).catch((e: any) => {
  console.error(pc.red("error: ") + (e?.message ?? String(e)));
  process.exit(1);
});
