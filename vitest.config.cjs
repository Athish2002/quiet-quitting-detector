module.exports = {
  resolve: { alias: { '@testing-library/user-event': './frontend/src/__mocks__/user-event.ts' } },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFilesAfterEnv: ['./vitest.setup.ts'],
  },
};
