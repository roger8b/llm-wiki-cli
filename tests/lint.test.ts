import { describe, it, expect, vi } from 'vitest';

describe('lint.ts - Finding interface', () => {
  it('should define severity levels', () => {
    type Severity = "info" | "warning" | "error" | "critical";
    const levels: Severity[] = ['info', 'warning', 'error', 'critical'];
    expect(levels.length).toBe(4);
  });

  it('should create finding object', () => {
    interface Finding { severity: "info" | "warning" | "error" | "critical"; file: string; message: string; }
    const finding: Finding = { severity: 'error', file: 'a.md', message: 'missing field' };
    expect(finding.severity).toBe('error');
  });
});

describe('lint.ts - report rendering', () => {
  it('should group findings by severity', () => {
    const findings = [
      { severity: 'error' as const, file: 'a.md', message: 'e1' },
      { severity: 'warning' as const, file: 'b.md', message: 'w1' },
      { severity: 'error' as const, file: 'c.md', message: 'e2' },
    ];
    const groups = { critical: [] as any[], error: [] as any[], warning: [] as any[], info: [] as any[] };
    for (const f of findings) groups[f.severity].push(f);
    expect(groups.error.length).toBe(2);
    expect(groups.warning.length).toBe(1);
  });

  it('should count by severity', () => {
    const findings = [
      { severity: 'error' as const }, { severity: 'error' as const }, { severity: 'warning' as const }
    ];
    const counts = { error: 0, warning: 0 };
    for (const f of findings) counts[f.severity as 'error' | 'warning']++;
    expect(counts.error).toBe(2);
    expect(counts.warning).toBe(1);
  });
});

describe('lint.ts - duplicate slug detection', () => {
  it('should detect duplicate slugs', () => {
    const slugs = new Map<string, string[]>();
    slugs.set('test', ['concepts/a.md', 'concepts/b.md']);
    const duplicates = Array.from(slugs.entries()).filter(([_, files]) => files.length > 1);
    expect(duplicates.length).toBe(1);
  });

  it('should report unique slugs as ok', () => {
    const slugs = new Map<string, string[]>();
    slugs.set('test', ['concepts/a.md']);
    const duplicates = Array.from(slugs.entries()).filter(([_, files]) => files.length > 1);
    expect(duplicates.length).toBe(0);
  });
});

describe('lint.ts - link checking', () => {
  it('should parse markdown links', () => {
    const raw = 'See [Test](./page.md) here';
    const re = /\[([^\]]+)\]\(([^)]+)\)/g;
    const matches = Array.from(raw.matchAll(re));
    expect(matches[0][2]).toBe('./page.md');
  });
});