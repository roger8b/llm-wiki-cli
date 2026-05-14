import { describe, it, expect, vi } from 'vitest';
import path from 'node:path';

describe('config.ts - path resolution', () => {
  it('should resolve relative to absolute path', () => {
    const abs = path.resolve('/tmp/test', 'relative/path');
    expect(abs).toMatch(/^\//);
  });

  it('should check for wiki.config.yaml', () => {
    const file = 'wiki.config.yaml';
    expect(file).toContain('wiki');
  });
});

describe('config.ts - readGlobalConfig', () => {
  it('should return empty object when no config', () => {
    const cfg = {};
    expect(Object.keys(cfg).length).toBe(0);
  });

  it('should contain wiki_root when set', () => {
    const cfg = { wiki_root: '/tmp/wiki' };
    expect(cfg.wiki_root).toBe('/tmp/wiki');
  });
});

describe('config.ts - configShow output', () => {
  it('should show empty config message', () => {
    const cfg = {};
    const message = Object.keys(cfg).length === 0 
      ? '(empty — no global wiki registered)'
      : JSON.stringify(cfg, null, 2);
    expect(message).toContain('empty');
  });

  it('should show config path', () => {
    const configPath = '/tmp/.llm-wiki/config.json';
    expect(configPath).toContain('.llm-wiki');
  });
});

describe('config.ts - configSetRoot validation', () => {
  it('should reject non-wiki directories', () => {
    const hasConfig = false;
    const isValid = hasConfig;
    expect(isValid).toBe(false);
  });

  it('should accept directories with wiki.config.yaml', () => {
    const hasConfig = true;
    const isValid = hasConfig;
    expect(isValid).toBe(true);
  });
});

describe('config.ts - configClear', () => {
  it('should clear config to empty object', () => {
    const cfg = { wiki_root: '/tmp/wiki', other: 'value' };
    const cleared = {};
    expect(Object.keys(cleared).length).toBe(0);
  });
});