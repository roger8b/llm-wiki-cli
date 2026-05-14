import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { findWikiRoot, loadContext } from "../src/utils/paths";
import * as globalConfigModule from "../src/utils/global-config";
import fs from "fs-extra";
import path from "node:path";
import os from "node:os";

describe("paths utility", () => {
  const tempDir = path.join(os.tmpdir(), "wiki-paths-test-" + Math.random().toString(36).slice(2));
  let originalEnv: NodeJS.ProcessEnv;
  let originalCwd: () => string;

  beforeEach(async () => {
    await fs.ensureDir(tempDir);
    originalEnv = { ...process.env };
    originalCwd = process.cwd;
  });

  afterEach(async () => {
    await fs.remove(tempDir);
    process.env = originalEnv;
    process.cwd = originalCwd;
    vi.restoreAllMocks();
  });

  describe("findWikiRoot", () => {
    it("should find root via LLM_WIKI_ROOT env variable if it contains wiki.config.yaml", async () => {
      const rootDir = path.join(tempDir, "env-root");
      await fs.ensureDir(rootDir);
      await fs.writeFile(path.join(rootDir, "wiki.config.yaml"), "name: test");
      process.env.LLM_WIKI_ROOT = rootDir;

      const root = findWikiRoot(tempDir);
      expect(root).toBe(path.resolve(rootDir));
    });

    it("should fallback if LLM_WIKI_ROOT env var points to a dir without wiki.config.yaml", async () => {
      vi.spyOn(globalConfigModule, "readGlobalConfig").mockReturnValue({});

      const rootDir = path.join(tempDir, "env-root");
      await fs.ensureDir(rootDir);
      process.env.LLM_WIKI_ROOT = rootDir;

      const actualRoot = path.join(tempDir, "actual-root");
      await fs.ensureDir(actualRoot);
      await fs.writeFile(path.join(actualRoot, "wiki.config.yaml"), "name: test");

      process.cwd = () => actualRoot;

      const root = findWikiRoot(actualRoot);
      expect(root).toBe(path.resolve(actualRoot));
    });

    it("should find root via global config if it contains wiki.config.yaml", async () => {
      const rootDir = path.join(tempDir, "global-root");
      await fs.ensureDir(rootDir);
      await fs.writeFile(path.join(rootDir, "wiki.config.yaml"), "name: test");

      vi.spyOn(globalConfigModule, "readGlobalConfig").mockReturnValue({ wiki_root: rootDir });

      const root = findWikiRoot(tempDir);
      expect(root).toBe(path.resolve(rootDir));
    });

    it("should fallback if global config points to dir without wiki.config.yaml", async () => {
      const rootDir = path.join(tempDir, "global-root");
      await fs.ensureDir(rootDir);

      vi.spyOn(globalConfigModule, "readGlobalConfig").mockReturnValue({ wiki_root: rootDir });

      const actualRoot = path.join(tempDir, "actual-root");
      await fs.ensureDir(actualRoot);
      await fs.writeFile(path.join(actualRoot, "wiki.config.yaml"), "name: test");

      const root = findWikiRoot(actualRoot);
      expect(root).toBe(path.resolve(actualRoot));
    });

    it("should find root by walking up directories from the given start dir", async () => {
      vi.spyOn(globalConfigModule, "readGlobalConfig").mockReturnValue({});

      const rootDir = path.join(tempDir, "walk-root");
      const nestedDir = path.join(rootDir, "a", "b", "c");
      await fs.ensureDir(nestedDir);
      await fs.writeFile(path.join(rootDir, "wiki.config.yaml"), "name: test");

      const root = findWikiRoot(nestedDir);
      expect(root).toBe(path.resolve(rootDir));
    });

    it("should return null if no wiki.config.yaml is found anywhere", async () => {
      vi.spyOn(globalConfigModule, "readGlobalConfig").mockReturnValue({});

      const nestedDir = path.join(tempDir, "x", "y");
      await fs.ensureDir(nestedDir);

      const root = findWikiRoot(nestedDir);
      expect(root).toBeNull();
    });
  });

  describe("loadContext", () => {
    it("should throw an error if no wiki root is found", () => {
      vi.spyOn(globalConfigModule, "readGlobalConfig").mockReturnValue({});
      expect(() => loadContext(tempDir)).toThrow(/wiki\.config\.yaml not found/);
    });

    it("should return a correctly populated context object when config is present", async () => {
      vi.spyOn(globalConfigModule, "readGlobalConfig").mockReturnValue({});

      const rootDir = path.join(tempDir, "context-root");
      await fs.ensureDir(rootDir);
      const yamlContent = `
name: "Test Wiki"
version: "1.0"
paths:
  raw: "raw"
  wiki: "wiki"
  schemas: "schemas"
  cache: ".cache"
  reports: "reports"
  manifests: "manifests"
  temp: ".temp"
`;
      await fs.writeFile(path.join(rootDir, "wiki.config.yaml"), yamlContent);

      const ctx = loadContext(rootDir);

      expect(ctx.root).toBe(path.resolve(rootDir));
      expect(ctx.config.name).toBe("Test Wiki");
      expect(ctx.rawDir).toBe(path.join(path.resolve(rootDir), "raw"));
      expect(ctx.wikiDir).toBe(path.join(path.resolve(rootDir), "wiki"));
      expect(ctx.schemasDir).toBe(path.join(path.resolve(rootDir), "schemas"));
      expect(ctx.cacheDir).toBe(path.join(path.resolve(rootDir), ".cache"));
      expect(ctx.reportsDir).toBe(path.join(path.resolve(rootDir), "reports"));
      expect(ctx.manifestsDir).toBe(path.join(path.resolve(rootDir), "manifests"));
      expect(ctx.tempDir).toBe(path.join(path.resolve(rootDir), ".temp"));
    });

    it("should handle optional paths like skillsDir", async () => {
      vi.spyOn(globalConfigModule, "readGlobalConfig").mockReturnValue({});

      const rootDir = path.join(tempDir, "context-root-2");
      await fs.ensureDir(rootDir);
      const yamlContent = `
name: "Test Wiki 2"
version: "1.0"
paths:
  raw: "r"
  wiki: "w"
  schemas: "s"
  skills: "sk"
  cache: "c"
  reports: "rp"
  manifests: "m"
  temp: "t"
`;
      await fs.writeFile(path.join(rootDir, "wiki.config.yaml"), yamlContent);

      const ctx = loadContext(rootDir);
      expect(ctx.skillsDir).toBe(path.join(path.resolve(rootDir), "sk"));
    });
  });
});
