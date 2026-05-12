import os from "node:os";
import path from "node:path";
import fs from "fs-extra";

export interface GlobalConfig {
  wiki_root?: string;
}

export function globalConfigPath(): string {
  return path.join(os.homedir(), ".llm-wiki", "config.json");
}

export function readGlobalConfig(): GlobalConfig {
  const p = globalConfigPath();
  if (!fs.existsSync(p)) return {};
  try {
    return fs.readJsonSync(p) as GlobalConfig;
  } catch {
    return {};
  }
}

export async function writeGlobalConfig(cfg: GlobalConfig): Promise<void> {
  const p = globalConfigPath();
  await fs.ensureDir(path.dirname(p));
  await fs.writeJson(p, cfg, { spaces: 2 });
}
