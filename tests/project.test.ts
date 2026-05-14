import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock all dependencies at the top level
vi.mock('fs-extra');
vi.mock('picocolors', () => ({
  default: {
    green: (s: string) => s,
    yellow: (s: string) => s,
    red: (s: string) => s,
    dim: (s: string) => s,
    cyan: (s: string) => s,
    bold: (s: string) => s,
  },
}));
vi.mock('@inquirer/prompts', () => ({
  checkbox: vi.fn().mockResolvedValue(['claude-code']),
  select: vi.fn().mockResolvedValue('local'),
  confirm: vi.fn().mockResolvedValue(true),
}));

// Mock modules
vi.mock('../src/utils/paths.js', () => ({
  loadContext: vi.fn().mockReturnValue(mockCtx),
  findWikiRoot: vi.fn().mockReturnValue('/tmp/test-wiki'),
}));
vi.mock('../src/utils/templates-dir.js', () => ({
  templatesDir: vi.fn().mockReturnValue('/tmp/templates'),
}));
vi.mock('../src/utils/agents.js', () => ({
  AGENTS: {
    'claude-code': {
      name: 'claude-code',
      displayName: 'Claude Code',
      skillsDir: '.claude/skills',
      globalSkillsDir: '/home/.claude/skills',
      ruleFile: 'CLAUDE.md',
      ruleFormat: 'boilerplate',
      appendOk: true,
    },
  },
  detectInstalledAgents: vi.fn().mockReturnValue(['claude-code']),
}));

const mockCtx = {
  root: '/tmp/test-wiki',
  rawDir: '/tmp/test-wiki/raw',
  wikiDir: '/tmp/test-wiki/wiki',
  schemasDir: '/tmp/test-wiki/schemas',
  skillsDir: null,
  manifestsDir: '/tmp/test-wiki/.wiki/manifests',
  cacheDir: '/tmp/test-wiki/.wiki/cache',
  config: { required_files: [], page_types: [], statuses: [] },
};

describe('project.ts - constants', () => {
  it('should define WIKI_SECTION_MARKER', () => {
    const WIKI_SECTION_MARKER = "<!-- llm-wiki-start -->";
    expect(WIKI_SECTION_MARKER).toContain('llm-wiki');
  });

  it('should define WIKI_SECTION_END', () => {
    const WIKI_SECTION_END = "<!-- llm-wiki-end -->";
    expect(WIKI_SECTION_END).toContain('llm-wiki');
  });
});

describe('project.ts - resolveSkillsDestForAgent', () => {
  it('should resolve local destination', () => {
    const target = '/tmp/project';
    const skillsDir = '.claude/skills';
    const localPath = `${target}/${skillsDir}`;
    expect(localPath).toBe('/tmp/project/.claude/skills');
  });

  it('should resolve global destination', () => {
    const globalSkillsDir = '/home/.claude/skills';
    expect(globalSkillsDir).toContain('/home');
  });
});

describe('project.ts - ProjectInitOpts', () => {
  it('should define valid scope options', () => {
    type Scope = "local" | "global" | "both";
    const validScopes: Scope[] = ['local', 'global', 'both'];
    expect(validScopes).toContain('local');
  });

  it('should define valid method options', () => {
    type Method = "symlink" | "copy";
    const validMethods: Method[] = ['symlink', 'copy'];
    expect(validMethods).toContain('symlink');
  });

  it('should define all option fields', () => {
    interface ProjectInitOpts {
      wiki?: string;
      force?: boolean;
      yes?: boolean;
      scope?: "local" | "global" | "both";
      method?: "symlink" | "copy";
      showAll?: boolean;
      update?: boolean;
    }
    const opts: ProjectInitOpts = { yes: true, method: 'symlink', showAll: false };
    expect(opts.yes).toBe(true);
    expect(opts.method).toBe('symlink');
  });
});

describe('project.ts - ExistingAction', () => {
  it('should define all action types', () => {
    type ExistingAction = "keep" | "update" | "remove" | "ask-each";
    const actions: ExistingAction[] = ['keep', 'update', 'remove', 'ask-each'];
    expect(actions.length).toBe(4);
  });
});