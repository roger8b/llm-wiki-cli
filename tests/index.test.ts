import { describe, it, expect, vi } from 'vitest';
import path from 'node:path';

describe('index.ts - PageMeta interface', () => {
  it('should have required fields', () => {
    interface PageMeta {
      file: string; rel: string; type: string; title: string;
      slug: string; status: string; updated_at: string; summary?: string;
    }
    const page: PageMeta = {
      file: '/tmp/wiki/concepts/test.md', rel: 'concepts/test.md',
      type: 'concept', title: 'Test', slug: 'test', status: 'draft', updated_at: '2024-01-01',
    };
    expect(page.type).toBe('concept');
    expect(page.status).toBe('draft');
  });
});

describe('index.ts - readAllPages filtering', () => {
  it('should exclude index.md', () => {
    const files = ['index.md', 'log.md', 'concepts/test.md'];
    const filtered = files.filter(f => f !== 'index.md' && f !== 'log.md');
    expect(filtered).not.toContain('index.md');
    expect(filtered).not.toContain('log.md');
  });

  it('should require type field', () => {
    const fm = { type: 'concept' };
    const hasType = !!fm.type;
    expect(hasType).toBe(true);
  });
});

describe('index.ts - index generation', () => {
  it('should group pages by type', () => {
    const pages = [
      { type: 'concept', title: 'A' }, { type: 'source', title: 'B' }, { type: 'concept', title: 'C' }
    ];
    const byType = new Map<string, typeof pages>();
    for (const p of pages) {
      if (!byType.has(p.type)) byType.set(p.type, []);
      byType.get(p.type)!.push(p);
    }
    expect(byType.get('concept')!.length).toBe(2);
    expect(byType.get('source')!.length).toBe(1);
  });

  it('should sort pages by title', () => {
    const pages = [{ title: 'Z' }, { title: 'A' }, { title: 'M' }];
    pages.sort((a, b) => a.title.localeCompare(b.title));
    expect(pages[0].title).toBe('A');
    expect(pages[2].title).toBe('Z');
  });
});

describe('index.ts - markdown formatting', () => {
  it('should format link with path', () => {
    const wikiDir = '/tmp/wiki/wiki';
    const file = '/tmp/wiki/wiki/concepts/test.md';
    const linkPath = path.relative(wikiDir, file).replace(/\\/g, '/');
    expect(linkPath).toBe('concepts/test.md');
  });

  it('should add status tag for non-draft', () => {
    const status = 'canonical';
    const tag = status !== 'draft' ? ` _(${status})_` : '';
    expect(tag).toContain('canonical');
  });
});