import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'lcov', 'json-summary'],
      reportsDirectory: './coverage',
      include: [
        'src/utils/**/*.ts',
        'src/commands/**/*.ts',
        'src/index.ts',
      ],
      exclude: [
        'src/**/*.d.ts',
      ],
      thresholds: {
        lines: 80,
        functions: 80,
        statements: 80,
        branches: 70,
      }
    },
  },
})