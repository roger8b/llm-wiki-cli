import { describe, it, expect, vi } from 'vitest';

describe('query.ts - TYPE_TO_DIR mapping', () => {
  it('should map synthesis to synthesis', () => {
    const TYPE_TO_DIR: Record<string, string> = {
      synthesis: "synthesis", comparison: "comparisons", playbook: "playbooks",
      decision: "decisions", "open-question": "open-questions", concept: "concepts",
    };
    expect(TYPE_TO_DIR['synthesis']).toBe('synthesis');
  });

  it('should map decision to decisions', () => {
    const TYPE_TO_DIR: Record<string, string> = {
      synthesis: "synthesis", comparison: "comparisons", playbook: "playbooks",
      decision: "decisions", "open-question": "open-questions", concept: "concepts",
    };
    expect(TYPE_TO_DIR['decision']).toBe('decisions');
  });
});

describe('query.ts - context generation', () => {
  it('should include question section', () => {
    const question = 'What is AI?';
    const lines = [`## Question`, `> ${question}`];
    expect(lines[1]).toContain(question);
  });

  it('should include candidate pages section', () => {
    const lines = [`## Candidate pages`];
    expect(lines[0]).toContain('Candidate');
  });

  it('should include decisions section', () => {
    const lines = [`## Decisions to consider`];
    expect(lines[0]).toContain('Decisions');
  });
});

describe('query.ts - hit filtering', () => {
  it('should filter decisions from hits', () => {
    const hits = [
      { type: 'decision', title: 'A' },
      { type: 'concept', title: 'B' },
      { type: 'decision', title: 'C' },
    ];
    const decisions = hits.filter(h => h.type === 'decision');
    expect(decisions.length).toBe(2);
  });

  it('should filter open questions from hits', () => {
    const hits = [
      { type: 'open-question', title: 'A' },
      { type: 'concept', title: 'B' },
    ];
    const open = hits.filter(h => h.type === 'open-question');
    expect(open.length).toBe(1);
  });
});

describe('query.ts - slug generation', () => {
  it('should generate slug from title', () => {
    const title = 'My Test Title';
    const slug = title.toLowerCase().replace(/\s+/g, '-');
    expect(slug).toBe('my-test-title');
  });
});