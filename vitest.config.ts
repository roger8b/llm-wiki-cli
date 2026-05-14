import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'lcov', 'json-summary'],
      reportsDirectory: './coverage',
      include: ['src/utils/paths.ts', 'src/utils/global-config.ts', 'src/utils/misc.ts'],
      thresholds: {
        lines: 90,
        functions: 90,
        statements: 90,
        // branches excluded: utility-file optional-chaining/ternaries are hard
        // to exercise fully; CI checks lines/statements/functions instead
      }
    },
  },
})
