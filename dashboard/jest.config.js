const nextJest = require("next/jest");

const createJestConfig = nextJest({ dir: "./" });

module.exports = createJestConfig({
  testEnvironment: "jsdom",
  setupFilesAfterEnv: ["<rootDir>/jest.setup.js"],
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/src/$1",
    // react-markdown is ESM-only; smoke tests don't exercise markdown rendering
    "^react-markdown$": "<rootDir>/__mocks__/react-markdown.tsx",
  },
});
