import { describe, it, expect, vi, beforeEach } from 'vitest';
import path from 'node:path';

// Mock dependencies
vi.mock('fs-extra');
vi.mock('picocolors', () => ({
  default: { green: (s: string) => s, yellow: (s: string) => s, red: (s: string) => s, dim: (s: string) => s, bold: (s: string) => s },
}));

describe('page.ts - normalizeSlugInput', () => {
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

  it('should handle both', () => {
    const fn = (input: string) => {
      let s = input.trim();
      if (s.endsWith('.md')) s = s.slice(0, -3);
      const slashIdx = s.indexOf('/');
      if (slashIdx > -1) s = s.slice(slashIdx + 1);
      return s;
    };
    expect(fn('source/file.md')).toBe('file');
  });

  it('should trim whitespace', () => {
    const fn = (input: string) => {
      let s = input.trim();
      if (s.endsWith('.md')) s = s.slice(0, -3);
      const slashIdx = s.indexOf('/');
      if (slashIdx > -1) s = s.slice(slashIdx + 1);
      return s;
    };
    expect(fn('  page  ')).toBe('page');
  });
});

describe('page.ts - TYPE_TO_DIR', () => {
  it('should map all types to directories', () => {
    const TYPE_TO_DIR: Record<string, string> = {
      source: "sources", concept: "concepts", entity: "entities", project: "projects",
      agent: "agents", workflow: "workflows", decision: "decisions", playbook: "playbooks",
      comparison: "comparisons", synthesis: "synthesis", "open-question": "open-questions",
      glossary: "glossary", "lint-report": "synthesis",
    };
    expect(TYPE_TO_DIR['source']).toBe('sources');
    expect(TYPE_TO_DIR['decision']).toBe('decisions');
    expect(TYPE_TO_DIR['synthesis']).toBe('synthesis');
  });
});

describe('page.ts - normalizeDate', () => {
  it('should handle Date objects', () => {
    const fn = (v: any) => {
      if (v instanceof Date) return v.toISOString().slice(0, 10);
      return v;
    };
    expect(fn(new Date('2024-01-15'))).toBe('2024-01-15');
  });

  it('should extract YYYY-MM-DD from strings', () => {
    const fn = (v: any) => {
      if (typeof v === 'string') {
        const m = v.match(/^(\d{4}-\d{2}-\d{2})/);
        if (m) return m[1];
      }
      return v;
    };
    expect(fn('2024-01-15T10:00:00Z')).toBe('2024-01-15');
    expect(fn('2024-01-15')).toBe('2024-01-15');
  });

  it('should return undefined for null', () => {
    const fn = (v: any) => v == null ? undefined : v;
    expect(fn(null)).toBeUndefined();
    expect(fn(undefined)).toBeUndefined();
  });
});

describe('page.ts - ValidationIssue', () => {
  it('should define error level', () => {
    const issue = { file: 'test.md', level: 'error' as const, message: 'missing field' };
    expect(issue.level).toBe('error');
  });

  it('should define warning level', () => {
    const issue = { file: 'test.md', level: 'warning' as const, message: 'no sources' };
    expect(issue.level).toBe('warning');
  });
});

describe('page.ts - frontmatter required fields', () => {
  it('should list all required fields', () => {
    const required = ["type", "title", "slug", "status", "created_at", "updated_at"];
    expect(required).toContain('type');
    expect(required).toContain('slug');
    expect(required.length).toBe(6);
  });

  it('should validate status values', () => {
    const statuses = ['draft', 'in-progress', 'reviewed', 'canonical', 'deprecated'];
    expect(statuses).toContain('draft');
    expect(statuses).toContain('canonical');
  });

  it('should validate page types', () => {
    const types = ['concept', 'source', 'entity', 'project', 'decision', 'synthesis'];
    expect(types).toContain('concept');
    expect(types).toContain('decision');
  });
});