/**
 * Jest config — uses Next's preset to share the project's webpack/babel
 * pipeline. Only covers the `src/` tree; everything else (pages, generated
 * types) is ignored.
 */

const nextJest = require('next/jest');

const createJestConfig = nextJest({ dir: './' });

module.exports = createJestConfig({
  testEnvironment: 'jsdom',
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
  },
  testMatch: ['<rootDir>/src/**/*.test.ts', '<rootDir>/src/**/*.test.tsx'],
});
