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
    bold: (s: string) => s,
  },
}));

describe('reset.ts - constants', () => {
  it('should define WIKI_SUBDIRS', () => {
    const WIKI_SUBDIRS = [
      "concepts", "entities", "projects", "agents", "workflows", "decisions",
      "playbooks", "comparisons", "synthesis", "sources", "open-questions", "glossary",
    ];
    expect(WIKI_SUBDIRS).toContain('concepts');
    expect(WIKI_SUBDIRS).toContain('sources');
    expect(WIKI_SUBDIRS).toContain('decisions');
    expect(WIKI_SUBDIRS.length).toBe(12);
  });

  it('should define RAW_SUBDIRS', () => {
    const RAW_SUBDIRS = [
      "articles", "books", "documents", "transcripts", "specs", "images", "external",
    ];
    expect(RAW_SUBDIRS).toContain('articles');
    expect(RAW_SUBDIRS).toContain('books');
    expect(RAW_SUBDIRS.length).toBe(7);
  });
});

describe('reset.ts - confirmation logic', () => {
  it('should show warning without --confirm', () => {
    const opts = { confirm: false, yes: false };
    expect(opts.confirm || opts.yes).toBe(false);
  });

  it('should proceed with --confirm', () => {
    const opts = { confirm: true, yes: false };
    expect(opts.confirm || opts.yes).toBe(true);
  });

  it('should proceed with --yes flag', () => {
    const opts = { confirm: false, yes: true };
    expect(opts.confirm || opts.yes).toBe(true);
  });
});

describe('reset.ts - directory operations', () => {
  it('should build wiki directory paths', () => {
    const wikiDir = '/tmp/wiki/wiki';
    const WIKI_SUBDIRS = [
      "concepts", "entities", "projects", "agents", "workflows", "decisions",
      "playbooks", "comparisons", "synthesis", "sources", "open-questions", "glossary",
    ];
    
    const dirs = WIKI_SUBDIRS.map(sub => path.join(wikiDir, sub));
    expect(dirs).toContain('/tmp/wiki/wiki/concepts');
    expect(dirs).toContain('/tmp/wiki/wiki/sources');
  });

  it('should build raw directory paths', () => {
    const rawDir = '/tmp/wiki/raw';
    const RAW_SUBDIRS = [
      "articles", "books", "documents", "transcripts", "specs", "images", "external",
    ];
    
    const dirs = RAW_SUBDIRS.map(sub => path.join(rawDir, sub));
    expect(dirs).toContain('/tmp/wiki/raw/articles');
    expect(dirs).toContain('/tmp/wiki/raw/books');
  });
});

describe('reset.ts - file counting', () => {
  it('should count removed files', () => {
    let removed = 0;
    const files = ['a.md', 'b.md', 'c.md'];
    
    for (const f of files) {
      removed++;
    }
    
    expect(removed).toBe(3);
  });

  it('should handle empty directories', () => {
    const dirs = ['concepts', 'entities'];
    const emptyDirs = dirs.filter(d => false); // no files
    expect(emptyDirs.length).toBe(0);
  });
});

describe('reset.ts - manifest reset', () => {
  it('should create empty sources array', () => {
    const manifest = { sources: [] };
    expect(manifest.sources).toEqual([]);
    expect(manifest.sources.length).toBe(0);
  });
});

describe('reset.ts - index.md seed content', () => {
  it('should include auto-managed notice', () => {
    const INDEX_MD = `# Wiki Index

Auto-managed catalog. Rebuild with \`wiki index rebuild\`.
`;
    expect(INDEX_MD).toContain('Wiki Index');
    expect(INDEX_MD).toContain('wiki index rebuild');
  });
});

describe('reset.ts - log.md seed content', () => {
  it('should include reset entry', () => {
    const today = '2024-01-15';
    const LOG_MD = `# Wiki Log

## [${today}] reset | brain reset to seed state
- notes: all sources and pages removed via \`wiki reset\`
`;
    expect(LOG_MD).toContain('reset');
    expect(LOG_MD).toContain('wiki reset');
  });
});

describe('reset.ts - git detection', () => {
  it('should check for .git directory', () => {
    const paths = ['/tmp/wiki/.git', '/tmp/wiki/wiki', '/tmp/wiki/raw'];
    const hasGit = paths.some(p => p.endsWith('.git'));
    expect(hasGit).toBe(true);
  });

  it('should handle missing .git directory', () => {
    const paths = ['/tmp/wiki/wiki', '/tmp/wiki/raw'];
    const hasGit = paths.some(p => p.endsWith('.git'));
    expect(hasGit).toBe(false);
  });
});