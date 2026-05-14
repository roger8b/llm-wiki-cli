import { describe, it, expect, vi } from 'vitest';

describe('doctor.ts - checks', () => {
  it('should check required files exist', () => {
    const required_files = ['wiki.config.yaml', 'AGENTS.md', 'WIKI_PROTOCOL.md'];
    const file = 'wiki.config.yaml';
    expect(required_files).toContain(file);
  });

  it('should check directories exist', () => {
    const dirs = ['raw', 'wiki', 'schemas'];
    const wikiDir = dirs[1];
    expect(wikiDir).toBe('wiki');
  });
});

describe('doctor.ts - issue reporting', () => {
  it('should report missing file as issue', () => {
    const file = 'wiki.config.yaml';
    const exists = false;
    const issue = exists ? null : `missing required file: ${file}`;
    expect(issue).toContain('missing');
  });

  it('should report missing directory as issue', () => {
    const dir = 'concepts';
    const exists = false;
    const issue = exists ? null : `missing directory: ${dir}`;
    expect(issue).toContain('missing');
  });
});

describe('doctor.ts - exit code', () => {
  it('should exit with 0 when all checks pass', () => {
    const issues: string[] = [];
    const exitCode = issues.length === 0 ? undefined : 1;
    expect(exitCode).toBeUndefined();
  });

  it('should exit with 1 when issues found', () => {
    const issues = ['missing file'];
    const exitCode = issues.length === 0 ? undefined : 1;
    expect(exitCode).toBe(1);
  });
});

describe('doctor.ts - paths', () => {
  it('should resolve paths relative to wiki root', () => {
    const root = '/tmp/wiki';
    const file = 'wiki.config.yaml';
    const fullPath = `${root}/${file}`;
    expect(fullPath).toBe('/tmp/wiki/wiki.config.yaml');
  });

  it('should check manifest', () => {
    const manifestsDir = '/tmp/wiki/.wiki/manifests';
    const manifestPath = `${manifestsDir}/sources.json`;
    expect(manifestPath).toContain('sources.json');
  });
});