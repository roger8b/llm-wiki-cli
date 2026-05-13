import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import fs from "fs-extra";

export function templatesDir(): string {
  // 1. ~/.wiki-cli/templates/ — user-managed source of truth (populated by install.sh)
  const homeTemplates = path.join(os.homedir(), ".wiki-cli", "templates");
  if (fs.existsSync(path.join(homeTemplates, "AGENTS.md"))) return homeTemplates;

  // 2. bundled fallback (dev / npm install)
  const here = path.dirname(fileURLToPath(import.meta.url));
  const candidates = [
    path.resolve(here, "../../templates"),
    path.resolve(here, "../templates"),
    path.resolve(here, "../../../templates"),
  ];
  for (const c of candidates) {
    if (fs.existsSync(path.join(c, "AGENTS.md"))) return c;
  }
  throw new Error("templates/ not found. Ensure ~/.wiki-cli/templates/ exists or reinstall the CLI.");
}
