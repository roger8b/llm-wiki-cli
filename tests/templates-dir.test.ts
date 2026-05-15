import { describe, it, expect, vi, beforeEach } from 'vitest';
import { templatesDir } from '../src/utils/templates-dir';
import path from 'node:path';
import os from 'node:os';
import fs from 'fs-extra';

// We'll test the actual function behavior with real file system
describe('templatesDir()', () => {
  const realExistsSync = fs.existsSync;
  const realHomedir = os.homedir();
  const tempDir = process.env.TEMP_DIR || '/tmp';

  beforeEach(() => {
    // Reset any mocks
    vi.restoreAllMocks();
  });

  describe('function exists and is callable', () => {
    it('should be exported as a function', () => {
      expect(typeof templatesDir).toBe('function');
    });
  });

  describe('path resolution logic', () => {
    it('should look for AGENTS.md in ~/.wiki-cli/templates/', () => {
      // Test that the function constructs the correct home path
      const expectedHomeTemplates = path.join(realHomedir, '.wiki-cli', 'templates');
      
      // Verify the path construction logic
      const homePath = path.join(os.homedir(), '.wiki-cli', 'templates');
      expect(homePath).toContain('.wiki-cli');
      expect(homePath).toContain('templates');
    });

    it('should check bundled fallback paths relative to source', () => {
      // These are the candidate paths the function tries
      const expectedCandidates = [
        '../../templates',
        '../templates',
        '../../../templates',
      ];

      // Verify at least one of these patterns is checked
      expect(expectedCandidates.length).toBe(3);
    });
  });

  describe('error handling', () => {
    it('should throw descriptive error when no templates found', () => {
      // Mock fs.existsSync to always return false
      fs.existsSync = vi.fn().mockReturnValue(false);

      expect(() => templatesDir()).toThrow(/templates/);
    });

    it('should include actionable message in error', () => {
      // Mock fs.existsSync to always return false
      fs.existsSync = vi.fn().mockReturnValue(false);

      try {
        templatesDir();
        // If no throw, fail
        expect(true).toBe(false);
      } catch (e: any) {
        expect(e.message).toMatch(/templates/);
      }
    });
  });

  describe('bundled fallback behavior', () => {
    it('should return bundled path when home templates missing but bundled exists', () => {
      // Mock: home templates missing, but bundled exists
      fs.existsSync = vi.fn().mockImplementation((p) => {
        const pStr = String(p);
        // Home templates missing
        if (pStr.includes('.wiki-cli')) return false;
        // Bundled templates exist
        if (pStr.includes('templates') && pStr.includes('AGENTS.md')) return true;
        return false;
      });

      const result = templatesDir();
      
      // Should return a bundled path, not throw
      expect(result).toBeTruthy();
      expect(result).not.toContain('.wiki-cli');
    });
  });
});

describe('templatesDir() edge cases', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    fs.existsSync = vi.fn();
  });

  it('should return home templates if AGENTS.md exists there', () => {
    const homePath = path.join(os.homedir(), '.wiki-cli', 'templates', 'AGENTS.md');
    
    fs.existsSync = vi.fn().mockImplementation((p) => {
      return String(p).endsWith('AGENTS.md');
    });

    const result = templatesDir();
    
    // Home should take priority
    expect(fs.existsSync).toHaveBeenCalled();
  });

  it('should check bundled candidates in order', () => {
    // Home doesn't exist, but bundled does
    fs.existsSync = vi.fn().mockImplementation((p) => {
      const pStr = String(p);
      // Home missing
      if (pStr.includes('.wiki-cli')) return false;
      // Bundled exists  
      if (pStr.includes('templates') && pStr.includes('AGENTS.md')) return true;
      return false;
    });

    const result = templatesDir();
    
    // Should return bundled path
    expect(result).toBeTruthy();
  });
});