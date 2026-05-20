import crypto from "node:crypto";
import fs from "fs-extra";

export function slugify(s: string): string {
  return s
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
}

export function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export async function sha256(filepath: string): Promise<string> {
  const buf = await fs.readFile(filepath);
  return "sha256:" + crypto.createHash("sha256").update(buf).digest("hex");
}

export function normalizeSlugInput(input: string): string {
  let s = input.trim();
  if (s.endsWith(".md")) s = s.slice(0, -3);
  const slashIdx = s.indexOf("/");
  if (slashIdx > -1) s = s.slice(slashIdx + 1);
  return s;
}

