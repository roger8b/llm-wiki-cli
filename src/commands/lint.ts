import path from "node:path";
import fs from "fs-extra";
import fg from "fast-glob";
import matter from "gray-matter";
import pc from "picocolors";
import { loadContext } from "../utils/paths.js";
import { validatePage } from "./page.js";
import { today } from "../utils/misc.js";

type Severity = "info" | "warning" | "error" | "critical";

interface Finding {
  severity: Severity;
  file: string;
  message: string;
}

export async function lintCmd() {
  const ctx = loadContext();
  const findings: Finding[] = [];

  for (const f of ctx.config.required_files) {
    if (!fs.existsSync(path.join(ctx.root, f))) {
      findings.push({ severity: "error", file: f, message: "required file missing" });
    }
  }

  const pageFiles = await fg("**/*.md", { cwd: ctx.wikiDir, absolute: true });
  const slugs = new Map<string, string[]>();
  const pagesByPath = new Map<string, Record<string, any>>();

  for (const f of pageFiles) {
    const base = path.basename(f);
    if (base === "index.md" || base === "log.md") continue;
    const issues = await validatePage(f);
    for (const i of issues) {
      findings.push({ severity: i.level === "error" ? "error" : "warning", file: i.file, message: i.message });
    }
    const raw = await fs.readFile(f, "utf8");
    let fm: Record<string, any> = {};
    try {
      fm = matter(raw).data as Record<string, any>;
    } catch {
      continue;
    }
    pagesByPath.set(f, fm);
    if (fm.slug) {
      if (!slugs.has(fm.slug)) slugs.set(fm.slug, []);
      slugs.get(fm.slug)!.push(path.relative(ctx.root, f));
    }
  }

  for (const [slug, files] of slugs) {
    if (files.length > 1) {
      findings.push({
        severity: "warning",
        file: files.join(", "),
        message: `duplicate slug: ${slug}`,
      });
    }
  }

  const indexPath = path.join(ctx.wikiDir, "index.md");
  if (fs.existsSync(indexPath)) {
    const idx = await fs.readFile(indexPath, "utf8");
    for (const f of pagesByPath.keys()) {
      const rel = path.relative(ctx.wikiDir, f).replace(/\\/g, "/");
      if (!idx.includes(rel)) {
        findings.push({ severity: "info", file: path.relative(ctx.root, f), message: "not listed in index.md" });
      }
    }
  }

  const linkRe = /\[([^\]]+)\]\(([^)]+)\)/g;
  for (const f of pagesByPath.keys()) {
    const raw = await fs.readFile(f, "utf8");
    const dir = path.dirname(f);
    for (const m of raw.matchAll(linkRe)) {
      const href = m[2].split("#")[0];
      if (!href || href.startsWith("http") || href.startsWith("mailto:")) continue;
      const target = path.resolve(dir, href);
      if (!fs.existsSync(target)) {
        findings.push({ severity: "warning", file: path.relative(ctx.root, f), message: `broken link: ${href}` });
      }
    }
  }

  const manifestPath = path.join(ctx.manifestsDir, "sources.json");
  if (fs.existsSync(manifestPath)) {
    const m = await fs.readJson(manifestPath);
    for (const s of m.sources ?? []) {
      if (s.status === "pending_ingest") {
        findings.push({ severity: "info", file: s.path, message: "source pending ingest" });
      }
    }
  }

  const counts: Record<Severity, number> = { info: 0, warning: 0, error: 0, critical: 0 };
  for (const f of findings) counts[f.severity]++;

  for (const f of findings) {
    const color =
      f.severity === "critical" || f.severity === "error" ? pc.red :
      f.severity === "warning" ? pc.yellow : pc.dim;
    console.log(color(`[${f.severity}] ${f.file}: ${f.message}`));
  }
  console.log(
    pc.bold(`\n${findings.length} finding(s)`) +
      `  errors=${counts.error}  warnings=${counts.warning}  info=${counts.info}  critical=${counts.critical}`,
  );

  const reportName = `lint-report-${today()}.md`;
  const report = renderReport(findings);
  await fs.ensureDir(ctx.reportsDir);
  await fs.writeFile(path.join(ctx.reportsDir, reportName), report);
  console.log(pc.dim(`report: ${path.relative(ctx.root, path.join(ctx.reportsDir, reportName))}`));

  if (counts.error > 0 || counts.critical > 0) process.exitCode = 1;
}

function renderReport(findings: Finding[]): string {
  const groups: Record<Severity, Finding[]> = { critical: [], error: [], warning: [], info: [] };
  for (const f of findings) groups[f.severity].push(f);
  const out: string[] = [
    "---",
    "type: lint-report",
    `title: "Lint report ${today()}"`,
    `slug: "lint-report-${today()}"`,
    "status: draft",
    `created_at: ${today()}`,
    `updated_at: ${today()}`,
    "---",
    "",
    `# Lint report ${today()}`,
    "",
    "## Summary",
    "",
    `- findings: ${findings.length}`,
    `- critical: ${groups.critical.length}`,
    `- error: ${groups.error.length}`,
    `- warning: ${groups.warning.length}`,
    `- info: ${groups.info.length}`,
    "",
    "## Findings",
    "",
  ];
  for (const sev of ["critical", "error", "warning", "info"] as Severity[]) {
    out.push(`### ${sev}`, "");
    if (groups[sev].length === 0) out.push("_(none)_", "");
    else {
      for (const f of groups[sev]) out.push(`- \`${f.file}\` — ${f.message}`);
      out.push("");
    }
  }
  return out.join("\n");
}
