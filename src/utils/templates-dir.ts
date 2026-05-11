import path from "node:path";
import { fileURLToPath } from "node:url";
import fs from "fs-extra";

export function templatesDir(): string {
  const here = path.dirname(fileURLToPath(import.meta.url));
  const candidates = [
    path.resolve(here, "../../templates"),
    path.resolve(here, "../templates"),
    path.resolve(here, "../../../templates"),
  ];
  for (const c of candidates) {
    if (fs.existsSync(path.join(c, "AGENTS.md"))) return c;
  }
  throw new Error("templates/ not found alongside CLI install");
}
