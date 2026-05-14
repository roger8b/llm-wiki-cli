import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'lcov'],
      reportsDirectory: './coverage',
      include: ['src/utils/paths.ts', 'src/utils/global-config.ts', 'src/utils/misc.ts'],
      thresholds: {
        lines: 90,
        functions: 90,
        branches: 90,
        statements: 90,
      }
    },
  },
})
