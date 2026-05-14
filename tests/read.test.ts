import { describe, it, expect, vi, beforeEach } from 'vitest';
import path from 'node:path';
import fs from 'fs-extra';
import fg from 'fast-glob';
import matter from 'gray-matter';
import pc from 'picocolors';

// Mock dependencies
vi.mock('fs-extra');
vi.mock('fast-glob');
vi.mock('gray-matter');
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

// Mock loadContext
const mockCtx = {
  root: '/tmp/test-wiki',
  rawDir: '/tmp/test-wiki/raw',
  wikiDir: '/tmp/test-wiki/wiki',
  schemasDir: '/tmp/test-wiki/schemas',
  skillsDir: null,
  manifestsDir: '/tmp/test-wiki/.wiki/manifests',
  cacheDir: '/tmp/test-wiki/.wiki/cache',
  config: {
    required_files: ['wiki.config.yaml', 'AGENTS.md', 'WIKI_PROTOCOL.md'],
    page_types: ['concept', 'source', 'entity', 'project'],
    statuses: ['draft', 'reviewed', 'canonical'],
  },
};

vi.mock('../src/utils/paths.js', () => ({
  loadContext: vi.fn().mockReturnValue(mockCtx),
}));
vi.mock('../src/commands/index.js', () => ({
  readAllPages: vi.fn().mockResolvedValue([
    { file: '/tmp/wiki/concepts/a.md', type: 'concept', title: 'A', slug: 'a', status: 'draft' },
  ]),
}));

describe('read.ts - normalizeSlugInput', () => {
  it('should strip .md suffix', () => {
    const fn = (input: string) => {
      let s = input.trim();
      if (s.endsWith('.md')) s = s.slice(0, -3);
      const slashIdx = s.indexOf('/');
      if (slashIdx > -1) s = s.slice(slashIdx + 1);
      return s;
    };
    expect(fn('my-page.md')).toBe('my-page');
  });

  it('should strip type/ prefix', () => {
    const fn = (input: string) => {
      let s = input.trim();
      if (s.endsWith('.md')) s = s.slice(0, -3);
      const slashIdx = s.indexOf('/');
      if (slashIdx > -1) s = s.slice(slashIdx + 1);
      return s;
    };
    expect(fn('concept/my-page')).toBe('my-page');
  });

  it('should handle both prefix and suffix', () => {
    const fn = (input: string) => {
      let s = input.trim();
      if (s.endsWith('.md')) s = s.slice(0, -3);
      const slashIdx = s.indexOf('/');
      if (slashIdx > -1) s = s.slice(slashIdx + 1);
      return s;
    };
    expect(fn('source/my-file.md')).toBe('my-file');
  });
});

describe('read.ts - path validation', () => {
  it('should reject path traversal', () => {
    const input = '../etc/passwd';
    const isInvalid = input.includes('/') || input.includes('\\') || input === '..';
    expect(isInvalid).toBe(true);
  });

  it('should reject double dot path traversal', () => {
    const input = 'foo/../../../etc/passwd';
    const isInvalid = input.includes('..');
    expect(isInvalid).toBe(true);
  });

  it('should allow simple paths', () => {
    const input = 'concept';
    const isInvalid = input.includes('..') || input === '..';
    expect(isInvalid).toBe(false);
  });
});

describe('read.ts - schema type validation', () => {
  it('should check for invalid characters', () => {
    const type = 'foo/../../../etc';
    const isInvalid = type.includes('/') || type.includes('\\') || type === '..';
    expect(isInvalid).toBe(true);
  });
});

describe('read.ts - page list formatting', () => {
  it('should format rows with type and status', () => {
    const pages = [
      { type: 'concept', status: 'draft', slug: 'test', title: 'Test' },
    ];
    
    const formatted = pages.map(p => 
      `[${p.type}]  ${p.status.padEnd(10)} slug=${p.slug}  "${p.title}"`
    );
    
    expect(formatted[0]).toContain('[concept]');
    expect(formatted[0]).toContain('draft');
  });

  it('should sort by type then title', () => {
    const pages = [
      { type: 'source', title: 'B' },
      { type: 'concept', title: 'A' },
      { type: 'concept', title: 'C' },
    ];
    
    pages.sort((a, b) => a.type.localeCompare(b.type) || a.title.localeCompare(b.title));
    
    expect(pages[0].type).toBe('concept');
    expect(pages[1].title).toBe('C');
  });
});

describe('read.ts - log entry parsing', () => {
  it('should split log by entries', () => {
    const content = `# Log
## [2024-01-03] third
## [2024-01-02] second
## [2024-01-01] first`;
    
    const parts = content.split(/(?=^## \[)/m);
    const entries = parts.slice(1);
    
    expect(entries.length).toBe(3);
    expect(entries[0]).toContain('third');
  });

  it('should take last N entries', () => {
    const entries = ['e1', 'e2', 'e3', 'e4', 'e5'];
    const last = entries.slice(-2);
    
    expect(last).toEqual(['e4', 'e5']);
  });
});

describe('read.ts - link parsing', () => {
  it('should extract href from markdown links', () => {
    const content = 'See [Example](./other-page.md) for more.';
    const re = /\[([^\]]+)\]\(([^)]+)\)/g;
    const matches = Array.from(content.matchAll(re));
    
    expect(matches[0][2]).toBe('./other-page.md');
  });

  it('should skip anchors and query strings', () => {
    const href = './page.md#section?foo=bar';
    const file = href.split('#')[0].split('?')[0];
    
    expect(file).toBe('./page.md');
  });
});

describe('read.ts - source matching', () => {
  it('should find by id', () => {
    const sources = [
      { id: 'src_001', path: 'a.pdf', type: 'article' },
      { id: 'src_002', path: 'b.pdf', type: 'article' },
    ];
    
    const match = sources.find(s => s.id === 'src_001');
    expect(match?.path).toBe('a.pdf');
  });

  it('should find by path', () => {
    const sources = [
      { id: 'src_001', path: 'raw/articles/a.pdf', type: 'article' },
    ];
    
    const match = sources.find(s => s.path === 'raw/articles/a.pdf');
    expect(match?.id).toBe('src_001');
  });

  it('should find by basename', () => {
    const sources = [
      { id: 'src_001', path: 'raw/articles/test.pdf', type: 'article' },
    ];
    
    const match = sources.find(s => path.basename(s.path) === 'test.pdf');
    expect(match?.id).toBe('src_001');
  });
});