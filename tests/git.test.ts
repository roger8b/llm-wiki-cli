import { describe, it, expect, vi, beforeEach } from "vitest";
import path from "node:path";

vi.mock("fs-extra", () => ({
  default: {
    existsSync: vi.fn(),
  },
  existsSync: vi.fn(),
}));

vi.mock("execa", () => ({
  execa: vi.fn(),
}));

import fs from "fs-extra";
import { execa } from "execa";
import { brainPaths, isGitRepo, stageBrainPaths, gitCommit, stagedFiles } from "../src/utils/git.js";

function ctxFixture(overrides: Record<string, unknown> = {}) {
  return {
    root: "/brain",
    rawDir: "/brain/raw",
    wikiDir: "/brain/wiki",
    schemasDir: "/brain/schemas",
    cacheDir: "/brain/.wiki/cache",
    reportsDir: "/brain/.wiki/reports",
    manifestsDir: "/brain/.wiki/manifests",
    tempDir: "/brain/.wiki/temp",
    config: {
      name: "test",
      version: "0.1.0",
      paths: {
        raw: "raw",
        wiki: "wiki",
        schemas: "schemas",
        skills: "skills",
        cache: ".wiki/cache",
        reports: ".wiki/reports",
        manifests: ".wiki/manifests",
        temp: ".wiki/temp",
      },
      required_files: [],
      page_types: [],
      statuses: [],
      source_policy: {},
      index: {},
      lint: {},
      search: {},
    },
    ...overrides,
  } as any;
}

describe("git.ts - brainPaths", () => {
  it("includes the standard brain directories", () => {
    const paths = brainPaths(ctxFixture());
    expect(paths).toContain("wiki");
    expect(paths).toContain("raw");
    expect(paths).toContain("schemas");
    expect(paths).toContain("skills");
    expect(paths).toContain(".wiki/manifests");
  });

  it("includes the top-level config and protocol files", () => {
    const paths = brainPaths(ctxFixture());
    expect(paths).toContain("wiki.config.yaml");
    expect(paths).toContain("AGENTS.md");
    expect(paths).toContain("WIKI_PROTOCOL.md");
  });

  it("honors a custom skills path from config", () => {
    const ctx = ctxFixture();
    ctx.config.paths.skills = "custom-skills";
    const paths = brainPaths(ctx);
    expect(paths).toContain("custom-skills");
    expect(paths).not.toContain("skills");
  });

  it("defaults skills to 'skills' when config omits it", () => {
    const ctx = ctxFixture();
    delete ctx.config.paths.skills;
    const paths = brainPaths(ctx);
    expect(paths).toContain("skills");
  });

  it("never includes user-only paths like .obsidian or tmp", () => {
    const paths = brainPaths(ctxFixture());
    expect(paths).not.toContain(".obsidian");
    expect(paths).not.toContain("tmp");
    expect(paths).not.toContain("node_modules");
  });
});

describe("git.ts - isGitRepo", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns false when .git is missing", async () => {
    (fs.existsSync as any).mockReturnValue(false);
    const result = await isGitRepo("/brain");
    expect(result).toBe(false);
    expect(fs.existsSync).toHaveBeenCalledWith(path.join("/brain", ".git"));
  });

  it("returns true when .git exists and rev-parse succeeds", async () => {
    (fs.existsSync as any).mockReturnValue(true);
    (execa as any).mockResolvedValue({ exitCode: 0, stdout: "true", stderr: "" });
    const result = await isGitRepo("/brain");
    expect(result).toBe(true);
  });

  it("returns false when rev-parse fails", async () => {
    (fs.existsSync as any).mockReturnValue(true);
    (execa as any).mockResolvedValue({ exitCode: 128, stdout: "", stderr: "fatal" });
    const result = await isGitRepo("/brain");
    expect(result).toBe(false);
  });
});

describe("git.ts - stageBrainPaths", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("only stages existing paths and reports staged when diff has content", async () => {
    (fs.existsSync as any).mockImplementation((p: string) => p.endsWith("wiki") || p.endsWith("raw"));
    (execa as any)
      .mockResolvedValueOnce({ exitCode: 0, stdout: "", stderr: "" })
      .mockResolvedValueOnce({ exitCode: 0, stdout: "", stderr: "" })
      .mockResolvedValueOnce({ exitCode: 0, stdout: "wiki/foo.md\n", stderr: "" });

    const result = await stageBrainPaths(ctxFixture());
    expect(result).toBe(true);

    const addCalls = (execa as any).mock.calls.filter((c: any[]) => c[1][0] === "add");
    expect(addCalls.length).toBe(2);
    const stagedPaths = addCalls.map((c: any[]) => c[1][2]);
    expect(stagedPaths).toContain("wiki");
    expect(stagedPaths).toContain("raw");
  });

  it("returns false when nothing was staged", async () => {
    (fs.existsSync as any).mockReturnValue(false);
    (execa as any).mockResolvedValue({ exitCode: 0, stdout: "", stderr: "" });

    const result = await stageBrainPaths(ctxFixture());
    expect(result).toBe(false);
  });

  it("never invokes git add -A", async () => {
    (fs.existsSync as any).mockReturnValue(true);
    (execa as any).mockResolvedValue({ exitCode: 0, stdout: "wiki/x.md\n", stderr: "" });

    await stageBrainPaths(ctxFixture());

    const addCalls = (execa as any).mock.calls.filter((c: any[]) => c[1][0] === "add");
    for (const call of addCalls) {
      expect(call[1]).not.toContain("-A");
    }
  });
});

describe("git.ts - gitCommit", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns ok when commit succeeds", async () => {
    (execa as any).mockResolvedValue({ exitCode: 0, stdout: "", stderr: "" });
    const r = await gitCommit("/brain", "subject");
    expect(r.ok).toBe(true);
    expect(r.err).toBeUndefined();
  });

  it("passes body as a second -m when provided", async () => {
    (execa as any).mockResolvedValue({ exitCode: 0, stdout: "", stderr: "" });
    await gitCommit("/brain", "subject", "longer body");
    const call = (execa as any).mock.calls[0];
    expect(call[1]).toEqual(["commit", "-m", "subject", "-m", "longer body"]);
  });

  it("returns ok=false and err when commit fails", async () => {
    (execa as any).mockResolvedValue({ exitCode: 1, stdout: "", stderr: "nothing to commit" });
    const r = await gitCommit("/brain", "subject");
    expect(r.ok).toBe(false);
    expect(r.err).toBe("nothing to commit");
  });

  it("uses stdout as err fallback when stderr is empty", async () => {
    (execa as any).mockResolvedValue({ exitCode: 1, stdout: "fallback message", stderr: "" });
    const r = await gitCommit("/brain", "subject");
    expect(r.ok).toBe(false);
    expect(r.err).toBe("fallback message");
  });
});

describe("git.ts - stagedFiles", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("splits stdout by newline and drops empty entries", async () => {
    (execa as any).mockResolvedValue({
      exitCode: 0,
      stdout: "wiki/foo.md\nraw/x.md\n\n",
      stderr: "",
    });
    const files = await stagedFiles("/brain");
    expect(files).toEqual(["wiki/foo.md", "raw/x.md"]);
  });

  it("returns an empty array when nothing is staged", async () => {
    (execa as any).mockResolvedValue({ exitCode: 0, stdout: "\n", stderr: "" });
    const files = await stagedFiles("/brain");
    expect(files).toEqual([]);
  });
});
