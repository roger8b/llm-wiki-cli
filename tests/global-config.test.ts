import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { readGlobalConfig, writeGlobalConfig } from "../src/utils/global-config";
import fs from "fs-extra";
import path from "node:path";
import os from "node:os";

describe("global-config", () => {
  const tempDir = path.join(os.tmpdir(), "wiki-global-config-test-" + Math.random().toString(36).slice(2));
  const configPath = path.join(tempDir, ".llm-wiki", "config.json");
  let originalHomedir: any;

  beforeEach(async () => {
    await fs.ensureDir(tempDir);
    originalHomedir = os.homedir;
    os.homedir = vi.fn(() => tempDir);
  });

  afterEach(async () => {
    os.homedir = originalHomedir;
    await fs.remove(tempDir);
    vi.restoreAllMocks();
  });

  it("should return an empty object if no config file exists", () => {
    const config = readGlobalConfig();
    expect(config).toEqual({});
  });

  it("should return parsed config if file exists", async () => {
    const testConfig = { wiki_root: "/some/path" };
    await fs.ensureDir(path.dirname(configPath));
    await fs.writeJson(configPath, testConfig);
    const config = readGlobalConfig();
    expect(config).toEqual(testConfig);
  });

  it("should return an empty object if file exists but is invalid JSON", async () => {
    await fs.ensureDir(path.dirname(configPath));
    await fs.writeFile(configPath, "{ invalid json ]");
    const config = readGlobalConfig();
    expect(config).toEqual({});
  });

  it("should write config to file properly", async () => {
    const newConfig = { wiki_root: "/new/path" };
    await writeGlobalConfig(newConfig);
    const exists = await fs.pathExists(configPath);
    expect(exists).toBe(true);
    const read = await fs.readJson(configPath);
    expect(read).toEqual(newConfig);
  });
});
