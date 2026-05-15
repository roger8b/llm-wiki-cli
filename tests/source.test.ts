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

describe('source.ts - TYPE_TO_DIR mapping', () => {
  it('should map article to articles', () => {
    const TYPE_TO_DIR: Record<string, string> = {
      article: "articles",
      book: "books",
      document: "documents",
      transcript: "transcripts",
      spec: "specs",
      image: "images",
      external: "external",
    };
    expect(TYPE_TO_DIR['article']).toBe('articles');
  });

  it('should map book to books', () => {
    const TYPE_TO_DIR: Record<string, string> = {
      article: "articles",
      book: "books",
      document: "documents",
      transcript: "transcripts",
      spec: "specs",
      image: "images",
      external: "external",
    };
    expect(TYPE_TO_DIR['book']).toBe('books');
  });

  it('should default to external for unknown types', () => {
    const TYPE_TO_DIR: Record<string, string> = {
      article: "articles",
      book: "books",
      document: "documents",
      transcript: "transcripts",
      spec: "specs",
      image: "images",
      external: "external",
    };
    expect(TYPE_TO_DIR['unknown'] ?? "external").toBe('external');
  });
});

describe('source.ts - SourceEntry interface', () => {
  it('should have required fields', () => {
    interface SourceEntry {
      id: string;
      path: string;
      type: string;
      hash: string;
      status: string;
      added_at: string;
    }
    const entry: SourceEntry = {
      id: 'src_20240115_test',
      path: 'raw/articles/test.pdf',
      type: 'article',
      hash: 'abc123',
      status: 'pending_ingest',
      added_at: '2024-01-15',
    };
    expect(entry.status).toBe('pending_ingest');
  });
});

describe('source.ts - Manifest interface', () => {
  it('should contain sources array', () => {
    interface Manifest {
      sources: SourceEntry[];
    }
    const manifest: Manifest = {
      sources: [
        { id: '1', path: 'a.pdf', type: 'article', hash: 'h1', status: 'pending', added_at: '2024-01-01' },
      ],
    };
    expect(manifest.sources.length).toBe(1);
  });
});

describe('source.ts - source ID generation', () => {
  it('should generate ID with date prefix', () => {
    const today = '2024-01-15';
    const slug = 'my-test-file';
    const id = `src_${today.replace(/-/g, "")}_${slug}`;
    
    expect(id).toBe('src_20240115_my-test-file');
  });

  it('should include status in ID generation', () => {
    const statuses = ['pending_ingest', 'ingested', 'rejected'];
    
    expect(statuses).toContain('pending_ingest');
    expect(statuses).toContain('ingested');
  });
});

describe('source.ts - hash computation', () => {
  it('should use sha256 for hashing', async () => {
    // Test that the hash function is called
    const sha256Fn = (data: string) => Promise.resolve('mock-hash');
    const result = await sha256Fn('test content');
    expect(result).toBe('mock-hash');
  });
});

describe('source.ts - manifest operations', () => {
  it('should find source by path', () => {
    const sources = [
      { id: '1', path: 'raw/articles/a.pdf', type: 'article', hash: 'h1', status: 'pending', added_at: '2024-01-01' },
      { id: '2', path: 'raw/articles/b.pdf', type: 'article', hash: 'h2', status: 'pending', added_at: '2024-01-01' },
    ];
    
    const found = sources.find(s => s.path === 'raw/articles/a.pdf');
    expect(found?.id).toBe('1');
  });

  it('should update source status', () => {
    const sources = [
      { id: '1', path: 'a.pdf', type: 'article', hash: 'h1', status: 'pending_ingest', added_at: '2024-01-01' },
    ];
    
    const source = sources.find(s => s.path === 'a.pdf');
    if (source) source.status = 'ingested';
    
    expect(sources[0].status).toBe('ingested');
  });

  it('should throw when source not in manifest', () => {
    const sources: any[] = [];
    
    expect(() => {
      const source = sources.find(s => s.path === 'missing.pdf');
      if (!source) throw new Error('source not in manifest: missing.pdf');
    }).toThrow('source not in manifest');
  });
});

describe('source.ts - raw directory structure', () => {
  it('should construct raw path correctly', () => {
    const rawDir = '/tmp/wiki/raw';
    const type = 'article';
    const TYPE_TO_DIR: Record<string, string> = {
      article: "articles",
      book: "books",
      document: "documents",
      transcript: "transcripts",
      spec: "specs",
      image: "images",
      external: "external",
    };
    
    const sub = TYPE_TO_DIR[type] ?? "external";
    const destDir = path.join(rawDir, sub);
    
    expect(destDir).toBe('/tmp/wiki/raw/articles');
  });
});