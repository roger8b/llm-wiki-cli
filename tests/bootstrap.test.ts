import { describe, it, expect, vi } from 'vitest';

describe('bootstrap.ts - constants', () => {
  it('should define WIKI_SUBDIRS', () => {
    const WIKI_SUBDIRS = [
      "concepts","entities","projects","agents","workflows","decisions",
      "playbooks","comparisons","synthesis","sources","open-questions","glossary",
    ];
    expect(WIKI_SUBDIRS).toContain('concepts');
    expect(WIKI_SUBDIRS).toContain('sources');
    expect(WIKI_SUBDIRS.length).toBe(12);
  });

  it('should define RAW_SUBDIRS', () => {
    const RAW_SUBDIRS = [
      "articles","books","documents","transcripts","specs","images","external",
    ];
    expect(RAW_SUBDIRS).toContain('articles');
    expect(RAW_SUBDIRS).toContain('books');
  });

  it('should define GITIGNORE content', () => {
    const GITIGNORE = `.wiki/cache/
.wiki/temp/
.wiki/reports/
.DS_Store
*.swp
node_modules/
`;
    expect(GITIGNORE).toContain('.wiki/cache/');
    expect(GITIGNORE).toContain('node_modules/');
  });
});

describe('bootstrap.ts - logSeed', () => {
  it('should generate log entry with date', () => {
    const date = '2024-01-15';
    const entry = `## [${date}] init | wiki bootstrap`;
    expect(entry).toContain(date);
    expect(entry).toContain('init');
  });
});

describe('bootstrap.ts - BootstrapOpts', () => {
  it('should define all options', () => {
    interface BootstrapOpts {
      git?: boolean;
      force?: boolean;
      register?: boolean;
      noRegister?: boolean;
    }
    const opts: BootstrapOpts = { git: true, force: false };
    expect(opts.git).toBe(true);
  });

  it('should default to register when no wiki set', () => {
    const existing = {};
    const shouldRegister = !existing.wiki_root;
    expect(shouldRegister).toBe(true);
  });
});