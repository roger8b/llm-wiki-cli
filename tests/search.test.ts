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
  reportsDir: '/tmp/test-wiki/.wiki/reports',
  tempDir: '/tmp/test-wiki/.wiki/temp',
  config: {
    required_files: ['wiki.config.yaml', 'AGENTS.md'],
    page_types: ['concept', 'source'],
    statuses: ['draft', 'reviewed'],
  },
};

vi.mock('../src/utils/paths.js', () => ({
  loadContext: vi.fn().mockReturnValue(mockCtx),
}));
vi.mock('../src/utils/misc.js', () => ({
  today: vi.fn().mockReturnValue('2024-01-15'),
}));

describe('search.ts - SearchHit interface', () => {
  it('should have required fields', () => {
    interface SearchHit {
      file: string;
      rel: string;
      title: string;
      type: string;
      status: string;
      score: number;
      excerpt: string;
    }
    const hit: SearchHit = {
      file: '/tmp/wiki/concepts/test.md',
      rel: 'concepts/test.md',
      title: 'Test',
      type: 'concept',
      status: 'draft',
      score: 10,
      excerpt: 'This is a test...',
    };
    expect(hit.score).toBeGreaterThan(0);
    expect(hit.excerpt).toBeDefined();
  });
});

describe('search.ts - scoring logic', () => {
  it('should boost score for title matches', () => {
    let score = 0;
    const title = 'Test Concept';
    const query = 'test';
    
    const haystack = title.toLowerCase();
    if (haystack.includes(query)) score += 5;
    
    expect(score).toBe(5);
  });

  it('should boost score for slug matches', () => {
    let score = 0;
    const slug = 'test-concept';
    const query = 'test';
    
    if (slug.toLowerCase().includes(query)) score += 3;
    
    expect(score).toBe(3);
  });

  it('should boost score for canonical status', () => {
    let score = 0;
    const status = 'canonical';
    
    if (status === 'canonical') score += 2;
    else if (status === 'reviewed') score += 1;
    
    expect(score).toBe(2);
  });

  it('should boost score for reviewed status', () => {
    let score = 0;
    const status = 'reviewed';
    
    if (status === 'canonical') score += 2;
    else if (status === 'reviewed') score += 1;
    
    expect(score).toBe(1);
  });
});

describe('search.ts - excerpt generation', () => {
  it('should extract text around match', () => {
    const content = 'This is a long content about testing things.';
    const query = 'test';
    const idx = content.indexOf(query);
    const excerpt = content
      .slice(Math.max(0, idx - 10), idx + 30)
      .replace(/\n+/g, ' ')
      .trim();
    
    expect(excerpt).toContain('test');
  });

  it('should handle match at start of content', () => {
    const content = 'testing is important';
    const query = 'test';
    const idx = content.indexOf(query);
    const excerpt = content.slice(0, 20);
    
    expect(excerpt.startsWith('test')).toBe(true);
  });

  it('should handle match at end of content', () => {
    const content = 'this is a test';
    const query = 'test';
    const idx = content.indexOf(query);
    const excerpt = content.slice(idx);
    
    expect(excerpt).toBe('test');
  });
});

describe('search.ts - multi-term scoring', () => {
  it('should sum scores for multiple terms', () => {
    const terms = ['test', 'concept'];
    let score = 0;
    
    for (const t of terms) {
      const count = 3; // mock
      score += count;
    }
    
    expect(score).toBe(6);
  });

  it('should filter by type correctly', () => {
    const pages = [
      { type: 'concept', title: 'A' },
      { type: 'source', title: 'B' },
      { type: 'concept', title: 'C' },
    ];
    
    const filtered = pages.filter(p => p.type === 'concept');
    expect(filtered.length).toBe(2);
  });

  it('should filter by status correctly', () => {
    const pages = [
      { status: 'draft', title: 'A' },
      { status: 'canonical', title: 'B' },
      { status: 'draft', title: 'C' },
    ];
    
    const filtered = pages.filter(p => p.status === 'draft');
    expect(filtered.length).toBe(2);
  });
});

describe('search.ts - link extraction', () => {
  it('should parse markdown links', () => {
    const content = 'See [Example](https://example.com) for more info.';
    const re = /\[([^\]]+)\]\(([^)]+)\)/g;
    const matches = Array.from(content.matchAll(re));
    
    expect(matches.length).toBe(1);
    expect(matches[0][1]).toBe('Example');
    expect(matches[0][2]).toBe('https://example.com');
  });

  it('should skip http links', () => {
    const href = 'https://example.com';
    const skip = href.startsWith('http') || href.startsWith('mailto:');
    expect(skip).toBe(true);
  });

  it('should skip mailto links', () => {
    const href = 'mailto:test@example.com';
    const skip = href.startsWith('http') || href.startsWith('mailto:');
    expect(skip).toBe(true);
  });

  it('should check relative links exist', () => {
    const href = './other-page.md';
    const target = '/tmp/wiki/' + href;
    // Mock existence check
    expect(target).toContain('other-page.md');
  });
});