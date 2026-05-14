import { defineConfig } from 'vitest/config'

/**
 * Vitest config used exclusively by Stryker mutation testing.
 *
 * Key difference from vitest.config.ts:
 * - reporters: ['default'] — prevents Vitest from auto-appending the
 *   github-actions reporter when GITHUB_ACTIONS=true is set in the
 *   environment. Without this, every mutant run (40+) emits a separate
 *   "Vitest Test Report" block in the GitHub Actions job summary.
 * - No coverage config — Stryker handles mutation scoring itself.
 */
export default defineConfig({
  test: {
    reporters: ['default'],
  },
})
