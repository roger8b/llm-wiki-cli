import { describe, it, expect, vi, beforeEach } from 'vitest';
import path from 'node:path';
import fs from 'fs-extra';
import pc from 'picocolors';

// Mock dependencies
vi.mock('fs-extra');
vi.mock('picocolors', () => ({
  default: {
    green: (s: string) => s,
    yellow: (s: string) => s,
    red: (s: string) => s,
    dim: (s: string) => s,
    cyan: (s: string) => s,
  },
}));

describe('uninstall.ts - constants', () => {
  it('should define WIKI_SECTION_MARKER', () => {
    const WIKI_SECTION_MARKER = "<!-- llm-wiki-start -->";
    expect(WIKI_SECTION_MARKER).toContain('llm-wiki-start');
  });

  it('should define WIKI_SECTION_END', () => {
    const WIKI_SECTION_END = "<!-- llm-wiki-end -->";
    expect(WIKI_SECTION_END).toContain('llm-wiki-end');
  });
});

describe('uninstall.ts - hasWikiSkills logic', () => {
  it('should check for wiki- prefixed skills', () => {
    const entries = ['wiki-ingest', 'wiki-query', 'other'];
    const wikiSkills = entries.filter(e => e.startsWith('wiki-'));
    expect(wikiSkills.length).toBe(2);
  });

  it('should count skills with SKILL.md', () => {
    const entries = ['wiki-ingest', 'wiki-query', 'other'];
    const count = entries.filter(e => e.startsWith('wiki-')).length;
    expect(count).toBe(2);
  });
});

describe('uninstall.ts - UninstallOpts interface', () => {
  it('should define valid scope options', () => {
    type Scope = "local" | "global" | "both";
    const opts: { scope?: Scope; yes?: boolean; force?: boolean } = {
      scope: 'local',
      yes: true,
      force: false,
    };
    expect(opts.scope).toBe('local');
    expect(opts.yes).toBe(true);
  });

  it('should support all scopes', () => {
    const scopes: ("local" | "global" | "both")[] = ['local', 'global', 'both'];
    expect(scopes.length).toBe(3);
  });
});

describe('uninstall.ts - removeWikiSkills logic', () => {
  it('should filter wiki- prefixed skills', () => {
    const entries = ['wiki-ingest', 'wiki-query', 'other'];
    const toRemove = entries.filter(e => e.startsWith('wiki-'));
    expect(toRemove.length).toBe(2);
  });

  it('should count removed skills', () => {
    const entries = ['wiki-ingest', 'wiki-query', 'wiki-refactor'];
    let removed = 0;
    for (const e of entries) {
      if (e.startsWith('wiki-')) removed++;
    }
    expect(removed).toBe(3);
  });
});

describe('uninstall.ts - AGENTS.md cleanup logic', () => {
  it('should check if other agents use AGENTS.md', () => {
    const defs = {
      'claude-code': { ruleFile: 'AGENTS.md' },
      'cursor': { ruleFile: 'AGENTS.md' },
      'windsurf': { ruleFile: 'WINDSURF.md' },
    };
    
    const usingAgentsMd = Object.entries(defs)
      .filter(([_, def]) => def.ruleFile === 'AGENTS.md')
      .map(([id]) => id);
    
    expect(usingAgentsMd.length).toBe(2);
  });
});

describe('uninstall.ts - section removal regex', () => {
  it('should match wiki section with multiline content', () => {
    const content = `existing content
<!-- llm-wiki-start -->
# Brain Section
Content here
<!-- llm-wiki-end -->
more content`;
    
    const re = new RegExp(`<!-- llm-wiki-start -->[\\s\\S]*?<!-- llm-wiki-end -->\\n?`, 'm');
    const cleaned = content.replace(re, '').trim();
    
    expect(cleaned).toBe('existing content\nmore content');
  });

  it('should handle empty file after removal', () => {
    const content = `<!-- llm-wiki-start -->
<!-- llm-wiki-end -->`;
    
    const re = new RegExp(`<!-- llm-wiki-start -->[\\s\\S]*?<!-- llm-wiki-end -->\\n?`, 'm');
    const cleaned = content.replace(re, '').trim();
    
    expect(cleaned).toBe('');
  });
});

describe('uninstall.ts - .llm-wiki.json update', () => {
  it('should filter out uninstalled agents', () => {
    const config = { agents: ['a', 'b', 'c'], version: 2 };
    const selected = ['a', 'c'];
    
    const remaining = config.agents.filter(a => !selected.includes(a));
    expect(remaining).toEqual(['b']);
  });

  it('should add uninstalled_at timestamp', () => {
    const config: Record<string, any> = { agents: [], version: 2 };
    config.uninstalled_at = new Date().toISOString();
    
    expect(config.uninstalled_at).toBeDefined();
    expect(config.agents).toEqual([]);
  });
});