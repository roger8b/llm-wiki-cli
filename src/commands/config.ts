import path from "node:path";
import fs from "fs-extra";
import pc from "picocolors";
import {
  globalConfigPath,
  readGlobalConfig,
  writeGlobalConfig,
} from "../utils/global-config.js";

export async function configShow() {
  const cfg = readGlobalConfig();
  console.log(pc.dim(`config: ${globalConfigPath()}`));
  if (Object.keys(cfg).length === 0) {
    console.log(pc.yellow("(empty — no global wiki registered)"));
    console.log(pc.dim("set with: wiki config set-root <path>"));
    return;
  }
  console.log(JSON.stringify(cfg, null, 2));
}

export async function configSetRoot(targetPath: string) {
  const abs = path.resolve(targetPath);
  if (!fs.existsSync(path.join(abs, "wiki.config.yaml"))) {
    console.error(pc.red(`not a wiki: ${abs} (no wiki.config.yaml)`));
    process.exitCode = 1;
    return;
  }
  const cfg = readGlobalConfig();
  await writeGlobalConfig({ ...cfg, wiki_root: abs });
  console.log(pc.green(`✓ global wiki root set to ${abs}`));
}

export async function configClear() {
  await writeGlobalConfig({});
  console.log(pc.green("✓ global config cleared"));
}
