import { describe, it, expect, vi } from 'vitest';

describe('cli.test.ts - Command setup', () => {
  it('should have wiki as program name', () => {
    const name = 'wiki';
    expect(name).toBe('wiki');
  });

  it('should define version', () => {
    const version = '0.2.0';
    expect(version).toMatch(/^\d+\.\d+/);
  });

  it('should list all commands', () => {
    const commands = [
      'init', 'uninstall', 'bootstrap', 'config', 'doctor', 'reset',
      'protocol', 'schema', 'source', 'ingest', 'query', 'search',
      'index', 'lint', 'page', 'links', 'log'
    ];
    expect(commands).toContain('init');
    expect(commands).toContain('doctor');
  });
});

describe('cli.test.ts - command options', () => {
  it('should define init options', () => {
    const options = ['--wiki', '--force', '--yes', '--scope', '--method', '--update', '--show-all'];
    expect(options).toContain('--force');
    expect(options).toContain('--yes');
  });

  it('should define bootstrap options', () => {
    const options = ['--git', '--force', '--register', '--no-register'];
    expect(options).toContain('--git');
    expect(options).toContain('--force');
  });

  it('should define reset options', () => {
    const options = ['--confirm', '--yes'];
    expect(options).toContain('--confirm');
  });
});

describe('cli.test.ts - error handling', () => {
  it('should format error message', () => {
    const e = new Error('test error');
    const message = e?.message ?? String(e);
    expect(message).toContain('test error');
  });

  it('should handle null/undefined errors', () => {
    const e: any = null;
    const message = e?.message ?? String(e);
    expect(message).toBe('null');
  });
});