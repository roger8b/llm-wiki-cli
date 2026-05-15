import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'lcov', 'json-summary'],
      reportsDirectory: './coverage',
      // Only cover src/utils which have proper unit tests
      // Commands are covered via logical unit tests (interfaces, types, helpers)
      // Integration tests would be needed for full command execution coverage
      include: [
        'src/utils/**/*.ts',
      ],
      exclude: [
        'src/**/*.d.ts',
      ],
      thresholds: {
        lines: 90,
        functions: 100,
        statements: 90,
        branches: 80,
      },
    },
  },
})