import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { 
  type AgentId,
  type AgentConfig,
  AGENTS,
  detectInstalledAgents,
  isUniversalAgent,
  getAgent
} from "../src/utils/agents";
import fs from "fs-extra";
import path from "node:path";
import os from "node:os";

// Mock fs-extra
vi.mock("fs-extra", () => ({
  default: {
    existsSync: vi.fn(),
  },
}));

// Store original values for restoration
const originalHomedir = os.homedir;
const originalCwd = process.cwd;

describe("agents utils", () => {
  const mockHome = "/mock/home";
  const mockConfigHome = "/mock/config";
  const mockCwd = "/mock/project";

  beforeEach(() => {
    vi.clearAllMocks();
    // Mock os.homedir() for consistent path handling
    vi.spyOn(os, "homedir").mockReturnValue(mockHome);
    // Mock process.cwd() for agents that check it
    vi.spyOn(process, "cwd").mockReturnValue(mockCwd);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Unit Tests: AGENTS constant structure
  // ─────────────────────────────────────────────────────────────────────────

  describe("AGENTS constant", () => {
    it("should have a non-empty AGENTS object", () => {
      expect(Object.keys(AGENTS).length).toBeGreaterThan(0);
    });

    it("should contain well-known agents like claude-code, cursor, windsurf", () => {
      expect(AGENTS["claude-code"]).toBeDefined();
      expect(AGENTS["cursor"]).toBeDefined();
      expect(AGENTS["windsurf"]).toBeDefined();
    });

    it("should have all required AgentConfig properties for every agent", () => {
      for (const [id, config] of Object.entries(AGENTS)) {
        expect(config).toHaveProperty("name", id);
        expect(config).toHaveProperty("displayName");
        expect(config).toHaveProperty("skillsDir");
        expect(config).toHaveProperty("globalSkillsDir");
        expect(config).toHaveProperty("ruleFile");
        expect(config).toHaveProperty("ruleFormat");
        expect(config).toHaveProperty("appendOk");
        expect(config).toHaveProperty("detectInstalled");
        expect(typeof config.detectInstalled).toBe("function");
      }
    });

    it("should have valid ruleFormat values (boilerplate or cursor)", () => {
      for (const config of Object.values(AGENTS)) {
        expect(["boilerplate", "cursor"]).toContain(config.ruleFormat);
      }
    });

    it("should have skillsDir as a relative path (starts with '.' or is 'skills')", () => {
      for (const config of Object.values(AGENTS)) {
        // Valid: starts with '.' or is exactly 'skills'
        const isValid = config.skillsDir.startsWith(".") || config.skillsDir === "skills";
        expect(isValid).toBe(true);
      }
    });

    it("should have appendOk as boolean for all agents", () => {
      for (const config of Object.values(AGENTS)) {
        expect(typeof config.appendOk).toBe("boolean");
      }
    });

    it("appendOk should be true for boilerplate agents, false for cursor-format agents", () => {
      // Kills BooleanLiteral mutations that flip appendOk: true → false (or vice-versa).
      // ruleFormat is a StringLiteral (excluded from mutation) so it's safe to branch on.
      for (const [id, config] of Object.entries(AGENTS)) {
        if (config.ruleFormat === "cursor") {
          expect(config.appendOk, `${id}: cursor-format agent must have appendOk false`).toBe(false);
        } else {
          expect(config.appendOk, `${id}: boilerplate agent must have appendOk true`).toBe(true);
        }
      }
    });

    it("should mark some agents with showInUniversalList: false", () => {
      const replit = AGENTS["replit"];
      expect(replit).toBeDefined();
      expect(replit.showInUniversalList).toBe(false);
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Unit Tests: getAgent()
  // ─────────────────────────────────────────────────────────────────────────

  describe("getAgent()", () => {
    it("should return agent config for valid agent IDs", () => {
      const agent = getAgent("claude-code");
      expect(agent).toBeDefined();
      expect(agent?.name).toBe("claude-code");
      expect(agent?.displayName).toBe("Claude Code");
    });

    it("should return undefined for unknown agent IDs", () => {
      expect(getAgent("unknown-agent-xyz")).toBeUndefined();
    });

    it("should return undefined for empty string", () => {
      expect(getAgent("")).toBeUndefined();
    });

    it("should return the same AgentConfig instance for the same ID", () => {
      const agent1 = getAgent("cursor");
      const agent2 = getAgent("cursor");
      expect(agent1).toBe(agent2);
    });

    it("should have detectInstalled as a function on returned config", () => {
      const agent = getAgent("claude-code");
      expect(agent?.detectInstalled).toBeDefined();
      expect(typeof agent?.detectInstalled).toBe("function");
    });

    it("should handle agent IDs with hyphens correctly", () => {
      expect(getAgent("github-copilot")).toBeDefined();
      expect(getAgent("gemini-cli")).toBeDefined();
      expect(getAgent("tabnine-cli")).toBeDefined();
    });

    it("should return undefined for agent IDs with special characters", () => {
      expect(getAgent("agent@with#chars")).toBeUndefined();
      expect(getAgent("agent/with/slash")).toBeUndefined();
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Unit Tests: isUniversalAgent()
  // ─────────────────────────────────────────────────────────────────────────

  describe("isUniversalAgent()", () => {
    it("should return true for agents with .agents/skills as skillsDir", () => {
      // These agents use the universal .agents/skills directory
      expect(isUniversalAgent("amp")).toBe(true);
      expect(isUniversalAgent("antigravity")).toBe(true);
      expect(isUniversalAgent("cline")).toBe(true);
      expect(isUniversalAgent("codex")).toBe(true);
      expect(isUniversalAgent("cursor")).toBe(true);
      expect(isUniversalAgent("deepagents")).toBe(true);
      expect(isUniversalAgent("dexto")).toBe(true);
      expect(isUniversalAgent("firebender")).toBe(true);
      expect(isUniversalAgent("gemini-cli")).toBe(true);
      expect(isUniversalAgent("github-copilot")).toBe(true);
      expect(isUniversalAgent("warp")).toBe(true);
    });

    it("should return false for agents with custom skillsDir", () => {
      // These agents use their own specific skills directories
      expect(isUniversalAgent("aider-desk")).toBe(false);
      expect(isUniversalAgent("openclaw")).toBe(false);
      expect(isUniversalAgent("windsurf")).toBe(false);
      expect(isUniversalAgent("openhands")).toBe(false);
      expect(isUniversalAgent("pi")).toBe(false);
      expect(isUniversalAgent("roo")).toBe(false);
      expect(isUniversalAgent("devin")).toBe(false);
      expect(isUniversalAgent("kode")).toBe(false);
    });

    it("should return false for unknown agent IDs", () => {
      expect(isUniversalAgent("unknown-agent")).toBe(false);
    });

    it("should return false for empty string", () => {
      expect(isUniversalAgent("")).toBe(false);
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Integration Tests: detectInstalledAgents() with mocked filesystem
  // ─────────────────────────────────────────────────────────────────────────

  describe("detectInstalledAgents()", () => {
    beforeEach(() => {
      vi.clearAllMocks();
    });

    it("should return empty array when no agents are installed", () => {
      // Mock fs.existsSync to return false for all agent checks
      vi.mocked(fs.existsSync).mockReturnValue(false);

      const detected = detectInstalledAgents();
      expect(detected).toEqual([]);
    });

    it("should return installed agents when their directories exist", () => {
      // Mock specific agents as installed
      vi.mocked(fs.existsSync).mockImplementation((p: unknown) => {
        const pathStr = String(p);
        // claude-code checks claudeHome
        if (pathStr.includes(".claude")) return true;
        // cursor checks home + .cursor
        if (pathStr.includes(".cursor")) return true;
        // windsurf checks home + .codeium/windsurf
        if (pathStr.includes(".codeium/windsurf")) return true;
        return false;
      });

      const detected = detectInstalledAgents();
      
      expect(detected).toContain("claude-code");
      expect(detected).toContain("cursor");
      expect(detected).toContain("windsurf");
    });

    it("should handle agents that check process.cwd()", () => {
      // codebuddy and continue check both home and cwd
      vi.mocked(fs.existsSync).mockImplementation((p: unknown) => {
        const pathStr = String(p);
        if (pathStr.includes(".codebuddy")) return true;
        if (pathStr.includes(".continue")) return true;
        return false;
      });

      const detected = detectInstalledAgents();
      
      expect(detected).toContain("codebuddy");
      expect(detected).toContain("continue");
    });

    it("should handle openclaw with multiple possible paths", () => {
      // openclaw can be .openclaw, .clawdbot, or .moltbot
      vi.mocked(fs.existsSync).mockImplementation((p: unknown) => {
        const pathStr = String(p);
        if (pathStr.includes(".openclaw") || 
            pathStr.includes(".clawdbot") || 
            pathStr.includes(".moltbot")) return true;
        return false;
      });

      const detected = detectInstalledAgents();
      expect(detected).toContain("openclaw");
    });

    it("should handle errors in detectInstalled function gracefully", () => {
      // Mock one agent's detectInstalled to throw
      vi.mocked(fs.existsSync).mockImplementation((p: unknown) => {
        const pathStr = String(p);
        // First call throws (simulating error), subsequent calls return false
        if (pathStr.includes(".aider-desk")) {
          throw new Error("Simulated filesystem error");
        }
        return false;
      });

      // Should not throw, should return empty or partial results
      expect(() => detectInstalledAgents()).not.toThrow();
    });

    it("should return all installed agents in a single call", () => {
      // Simulate multiple agents installed
      vi.mocked(fs.existsSync).mockImplementation((p: unknown) => {
        const pathStr = String(p);
        if (pathStr.includes(".claude")) return true; // claude-code
        if (pathStr.includes(".cursor")) return true; // cursor
        if (pathStr.includes(".gemini")) return true; // gemini-cli, antigravity
        if (pathStr.includes(".pi/agent")) return true; // pi
        return false;
      });

      const detected = detectInstalledAgents();
      
      expect(detected.length).toBeGreaterThanOrEqual(4);
      expect(detected).toContain("claude-code");
      expect(detected).toContain("cursor");
      expect(detected).toContain("gemini-cli");
      expect(detected).toContain("pi");
    });

    it("should handle configHome env variable for XDG compliance", () => {
      // Agents like amp, devin, goose, opencode use configHome
      vi.mocked(fs.existsSync).mockImplementation((p: unknown) => {
        const pathStr = String(p);
        if (pathStr.includes("/amp")) return true;
        if (pathStr.includes("/devin")) return true;
        return false;
      });

      const detected = detectInstalledAgents();
      
      expect(detected).toContain("amp");
      expect(detected).toContain("devin");
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Mutation Tests: Verify detectInstalled behavior under edge cases
  // ─────────────────────────────────────────────────────────────────────────

  describe("detectInstalledAgents() edge cases", () => {
    it("should handle empty filesystem results consistently", () => {
      vi.mocked(fs.existsSync).mockReturnValue(false);
      
      const detected = detectInstalledAgents();
      expect(Array.isArray(detected)).toBe(true);
      expect(detected.length).toBe(0);
    });

    it("should handle partial filesystem results", () => {
      let callCount = 0;
      vi.mocked(fs.existsSync).mockImplementation(() => {
        callCount++;
        return callCount % 2 === 0; // Alternate between true/false
      });

      const detected = detectInstalledAgents();
      expect(Array.isArray(detected)).toBe(true);
      // Some agents might be detected, some not
    });

    it("should handle path with special characters in agent detection", () => {
      vi.mocked(fs.existsSync).mockImplementation((p: unknown) => {
        const pathStr = String(p);
        // Simulate paths with spaces and special chars
        if (pathStr.includes(" ")) return true;
        return false;
      });

      expect(() => detectInstalledAgents()).not.toThrow();
    });

    it("should return unique agent IDs only (no duplicates)", () => {
      vi.mocked(fs.existsSync).mockReturnValue(true);

      const detected = detectInstalledAgents();
      const uniqueSet = new Set(detected);

      expect(uniqueSet.size).toBe(detected.length);
    });

    it("should detect EVERY agent when all filesystem paths exist", () => {
      // mockReturnValue(true) means every fs.existsSync call returns true.
      // Any detectInstalled mutated to () => undefined would NOT call existsSync,
      // so those agents would be missing — this test kills all ArrowFunction mutants.
      vi.mocked(fs.existsSync).mockReturnValue(true);

      const detected = detectInstalledAgents();
      for (const id of Object.keys(AGENTS)) {
        expect(detected, `agent "${id}" should be detected`).toContain(id);
      }
    });

    it("should EXCLUDE an agent whose detectInstalled throws", () => {
      // Kills: BooleanLiteral(true) mutation on `return false` in the catch block,
      // which would cause throwing agents to be erroneously included.
      vi.mocked(fs.existsSync).mockImplementation((p: unknown) => {
        if (String(p).includes(".aider-desk")) throw new Error("permission denied");
        return false;
      });
      const detected = detectInstalledAgents();
      expect(detected).not.toContain("aider-desk");
    });

    it("should handle agent with showInUniversalList: false still being detected", () => {
      // replit has showInUniversalList: false, but should still be detected
      vi.mocked(fs.existsSync).mockImplementation((p: unknown) => {
        const pathStr = String(p);
        if (pathStr.includes(".replit")) return true;
        return false;
      });

      const detected = detectInstalledAgents();
      // replit should be detected as installed even though it won't show in universal list
      expect(detected).toContain("replit");
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Mutation killers: logical-operator branches for multi-path detections
  // Each test exercises ONE path at a time, forcing the OR operand to be
  // the sole reason the agent is detected. This kills:
  //   - ConditionalExpression(false) mutations on individual conditions
  //   - LogicalOperator(||→&&) mutations
  // ─────────────────────────────────────────────────────────────────────────

  describe("detectInstalled() logical operator coverage", () => {
    // openclaw: () => A || B || C  (three paths)
    it("openclaw: detected when ONLY .openclaw exists", () => {
      vi.mocked(fs.existsSync).mockImplementation((p: unknown) => {
        const s = String(p);
        return s.endsWith("/.openclaw");
      });
      expect(detectInstalledAgents()).toContain("openclaw");
    });

    it("openclaw: detected when ONLY .clawdbot exists", () => {
      vi.mocked(fs.existsSync).mockImplementation((p: unknown) => {
        const s = String(p);
        return s.endsWith("/.clawdbot");
      });
      expect(detectInstalledAgents()).toContain("openclaw");
    });

    it("openclaw: detected when ONLY .moltbot exists", () => {
      vi.mocked(fs.existsSync).mockImplementation((p: unknown) => {
        const s = String(p);
        return s.endsWith("/.moltbot");
      });
      expect(detectInstalledAgents()).toContain("openclaw");
    });

    it("openclaw: NOT detected when none of the three paths exist", () => {
      vi.mocked(fs.existsSync).mockImplementation((p: unknown) => {
        const s = String(p);
        return !s.includes(".openclaw") && !s.includes(".clawdbot") && !s.includes(".moltbot");
      });
      vi.mocked(fs.existsSync).mockReturnValue(false);
      expect(detectInstalledAgents()).not.toContain("openclaw");
    });

    // codebuddy: () => CWD_check || HOME_check
    it("codebuddy: detected when ONLY project-local .codebuddy exists", () => {
      vi.mocked(fs.existsSync).mockImplementation((p: unknown) => {
        const s = String(p);
        return s.startsWith(mockCwd) && s.endsWith("/.codebuddy");
      });
      expect(detectInstalledAgents()).toContain("codebuddy");
    });

    it("codebuddy: detected when ONLY home .codebuddy exists", () => {
      vi.mocked(fs.existsSync).mockImplementation((p: unknown) => {
        const s = String(p);
        return s.includes("/.codebuddy") && !s.startsWith(mockCwd);
      });
      expect(detectInstalledAgents()).toContain("codebuddy");
    });

    // codex: () => existsSync(codexHome) || existsSync("/etc/codex")
    it("codex: detected when ONLY /etc/codex exists", () => {
      vi.mocked(fs.existsSync).mockImplementation((p: unknown) => {
        return String(p) === "/etc/codex";
      });
      expect(detectInstalledAgents()).toContain("codex");
    });

    // continue: () => CWD_check || HOME_check
    it("continue: detected when ONLY project-local .continue exists", () => {
      vi.mocked(fs.existsSync).mockImplementation((p: unknown) => {
        const s = String(p);
        return s.startsWith(mockCwd) && s.endsWith("/.continue");
      });
      expect(detectInstalledAgents()).toContain("continue");
    });

    it("continue: detected when ONLY home .continue exists", () => {
      vi.mocked(fs.existsSync).mockImplementation((p: unknown) => {
        const s = String(p);
        return s.includes("/.continue") && !s.startsWith(mockCwd);
      });
      expect(detectInstalledAgents()).toContain("continue");
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Integration: Combined usage scenarios
  // ─────────────────────────────────────────────────────────────────────────

  describe("Combined usage scenarios", () => {
    it("should allow filtering agents by universal status", () => {
      vi.mocked(fs.existsSync).mockReturnValue(false);

      const allAgents = Object.keys(AGENTS);
      const universalAgents = allAgents.filter(isUniversalAgent);
      
      expect(universalAgents.length).toBeGreaterThan(0);
      
      for (const id of universalAgents) {
        expect(AGENTS[id].skillsDir).toBe(".agents/skills");
      }
    });

    it("should allow getting installed universal agents", () => {
      vi.mocked(fs.existsSync).mockImplementation((p: unknown) => {
        const pathStr = String(p);
        return pathStr.includes(".claude") || pathStr.includes(".cursor");
      });

      const installed = detectInstalledAgents();
      const universalInstalled = installed.filter(isUniversalAgent);
      
      // claude-code and cursor are both universal agents
      expect(universalInstalled.some(id => getAgent(id)?.skillsDir === ".agents/skills")).toBe(true);
    });

    it("should provide complete agent config for detected agents", () => {
      vi.mocked(fs.existsSync).mockImplementation((p: unknown) => {
        const pathStr = String(p);
        if (pathStr.includes(".pi/agent")) return true;
        return false;
      });

      const detected = detectInstalledAgents();
      
      if (detected.includes("pi")) {
        const pi = getAgent("pi");
        expect(pi).toBeDefined();
        expect(pi?.ruleFile).toBe("AGENTS.md");
        expect(pi?.ruleFormat).toBe("boilerplate");
        expect(pi?.appendOk).toBe(true);
      }
    });

    it("should handle mixed installed/uninstalled agents", () => {
      // Simulate: pi installed, others not
      vi.mocked(fs.existsSync).mockImplementation((p: unknown) => {
        const pathStr = String(p);
        if (pathStr.includes(".pi/agent")) return true;
        return false;
      });

      const detected = detectInstalledAgents();
      
      expect(detected).toContain("pi");
      expect(detected).not.toContain("claude-code");
      expect(detected).not.toContain("cursor");
    });
  });
});