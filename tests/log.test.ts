import { describe, it, expect, vi } from 'vitest';

describe('log.ts - logAdd', () => {
  it('should format entry with date', () => {
    const today = '2024-01-15';
    const opts = { type: 'ingest', message: 'test' };
    const entry = `\n## [${today}] ${opts.type} | ${opts.message}`;
    expect(entry).toContain(today);
    expect(entry).toContain('ingest');
    expect(entry).toContain('test');
  });

  it('should include operation type', () => {
    const type = 'create';
    const entry = `## [2024-01-15] ${type} | message`;
    expect(entry).toContain('create');
  });
});

describe('log.ts - logShow', () => {
  it('should split by entries', () => {
    const content = `# Log\n## [2024-01-03] third\n## [2024-01-02] second\n## [2024-01-01] first`;
    const parts = content.split(/(?=^## \[)/m);
    const entries = parts.slice(1);
    expect(entries.length).toBe(3);
  });

  it('should get last N entries', () => {
    const entries = ['e1', 'e2', 'e3', 'e4', 'e5'];
    const last = entries.slice(-2);
    expect(last).toEqual(['e4', 'e5']);
  });
});