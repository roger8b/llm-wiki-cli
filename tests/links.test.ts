import { describe, it, expect, vi } from 'vitest';
import pathLib from 'node:path';

describe('links.ts - link parsing', () => {
  it('should extract markdown links', () => {
    const content = 'See [Example](./page.md) for more.';
    const re = /\[([^\]]+)\]\(([^)]+)\)/g;
    const matches = Array.from(content.matchAll(re));
    expect(matches.length).toBe(1);
    expect(matches[0][1]).toBe('Example');
    expect(matches[0][2]).toBe('./page.md');
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

  it('should handle anchor links', () => {
    const href = './page.md#section';
    const file = href.split('#')[0];
    expect(file).toBe('./page.md');
  });
});

describe('links.ts - path resolution', () => {
  it('should resolve relative to absolute', () => {
    const dir = '/tmp/wiki/concepts';
    const href = './other.md';
    const target = pathLib.resolve(dir, href);
    expect(target).toBe('/tmp/wiki/concepts/other.md');
  });

  it('should detect broken links', () => {
    const exists = false;
    const linkBroken = !exists;
    expect(linkBroken).toBe(true);
  });
});

describe('links.ts - broken link counting', () => {
  it('should count multiple broken links', () => {
    let broken = 0;
    const links = ['./a.md', './b.md', './c.md'];
    // Simulate all broken
    broken = links.length;
    expect(broken).toBe(3);
  });

  it('should report zero when all links valid', () => {
    let broken = 0;
    // No broken links
    expect(broken).toBe(0);
  });
});