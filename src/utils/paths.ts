import path from "node:path";
import fs from "fs-extra";
import yaml from "js-yaml";

export interface WikiConfig {
  name: string;
  version: string;
  paths: {
    raw: string;
    wiki: string;
    schemas: string;
    skills: string;
    cache: string;
    reports: string;
    manifests: string;
    temp: string;
  };
  required_files: string[];
  page_types: string[];
  statuses: string[];
  source_policy: Record<string, boolean>;
  index: Record<string, unknown>;
  lint: Record<string, unknown>;
  search: Record<string, unknown>;
}

export interface WikiContext {
  root: string;
  config: WikiConfig;
  rawDir: string;
  wikiDir: string;
  schemasDir: string;
  skillsDir: string;
  cacheDir: string;
  reportsDir: string;
  manifestsDir: string;
  tempDir: string;
}

export function findWikiRoot(start: string = process.cwd()): string | null {
  if (process.env.LLM_WIKI_ROOT) {
    const env = path.resolve(process.env.LLM_WIKI_ROOT);
    if (fs.existsSync(path.join(env, "wiki.config.yaml"))) return env;
  }
  let cur = path.resolve(start);
  while (true) {
    if (fs.existsSync(path.join(cur, "wiki.config.yaml"))) return cur;
    const parent = path.dirname(cur);
    if (parent === cur) return null;
    cur = parent;
  }
}

export function loadContext(start?: string): WikiContext {
  const root = findWikiRoot(start);
  if (!root) {
    throw new Error(
      "wiki.config.yaml not found. Run `llm-wiki init` first or cd into a wiki repo.",
    );
  }
  const raw = fs.readFileSync(path.join(root, "wiki.config.yaml"), "utf8");
  const config = yaml.load(raw) as WikiConfig;
  return {
    root,
    config,
    rawDir: path.join(root, config.paths.raw),
    wikiDir: path.join(root, config.paths.wiki),
    schemasDir: path.join(root, config.paths.schemas),
    skillsDir: path.join(root, config.paths.skills),
    cacheDir: path.join(root, config.paths.cache),
    reportsDir: path.join(root, config.paths.reports),
    manifestsDir: path.join(root, config.paths.manifests),
    tempDir: path.join(root, config.paths.temp),
  };
}
