#!/usr/bin/env node
import { Command } from "commander";
import pc from "picocolors";
import { initCmd } from "./commands/init.js";
import { doctorCmd } from "./commands/doctor.js";
import { sourceAdd, sourceList, sourceStatus } from "./commands/source.js";
import { pageNew, pageValidate } from "./commands/page.js";
import { indexRebuild } from "./commands/index.js";
import { searchCmd } from "./commands/search.js";
import { lintCmd } from "./commands/lint.js";
import { ingestPrepare, ingestCommit } from "./commands/ingest.js";
import { queryPrepare, querySave } from "./commands/query.js";
import { logAdd } from "./commands/log.js";
import { linksCheck } from "./commands/links.js";

const program = new Command();
program
  .name("llm-wiki")
  .description("CLI for the Global LLM Wiki")
  .version("0.1.0");

program
  .command("init [path]")
  .description("initialize a wiki at the given path (default: cwd)")
  .option("--git", "initialize git in the wiki root")
  .option("--force", "overwrite existing files")
  .action((p, o) => initCmd(p, o));

program.command("doctor").description("validate wiki structure").action(doctorCmd);

const source = program.command("source").description("manage raw sources");
source
  .command("add <file>")
  .option("--type <type>", "source type", "article")
  .action(sourceAdd);
source.command("list").option("--status <status>").action(sourceList);
source.command("status <source>").action(sourceStatus);

const ingest = program.command("ingest").description("ingestion workflow");
ingest.command("prepare <source>").action(ingestPrepare);
ingest.command("commit <source>").action(ingestCommit);

const query = program.command("query").description("query workflow");
query.command("prepare <question>").action(queryPrepare);
query
  .command("save <file>")
  .requiredOption("--as <type>", "page type (synthesis, comparison, ...)")
  .requiredOption("--title <title>", "page title")
  .action(querySave);

program
  .command("search <query>")
  .option("--type <type>")
  .option("--status <status>")
  .action(searchCmd);

const idx = program.command("index").description("index management");
idx.command("rebuild").action(indexRebuild);

program.command("lint").description("audit wiki health").action(lintCmd);

const page = program.command("page").description("page operations");
page.command("new <type> <title>").action(pageNew);
page.command("validate <path>").action(pageValidate);

const links = program.command("links").description("link operations");
links.command("check").action(linksCheck);

const log = program.command("log").description("log operations");
log
  .command("add")
  .requiredOption("--type <type>", "operation type")
  .requiredOption("--message <message>", "log message")
  .action(logAdd);

program.parseAsync(process.argv).catch((e: any) => {
  console.error(pc.red("error: ") + (e?.message ?? String(e)));
  process.exit(1);
});
