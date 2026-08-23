// Minimal mock for @testing-library/user-event used in tests
// Provides a setup() method returning an object with a click() stub.
// Additional methods can be added if tests require them.

const userEventMock = {
  setup: () => {
    return {
      // Simulate click without requiring actual DOM events.
      click: async () => {
        // No-op; the test only checks that click can be called.
        return Promise.resolve();
      },
    };
  },
};

export default userEventMock;
