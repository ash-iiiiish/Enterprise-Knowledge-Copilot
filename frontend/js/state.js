// Shared mutable app state + hooks that main.js wires up (avoids circular imports).
export const app = {
  user: null,
  config: { allow_signup: true },
  navigate: (hash) => { location.hash = hash; },
  refreshHeader: () => {},
  refreshNotifications: () => {},
  isStaff: () => !!app.user && (app.user.role === "hr" || app.user.role === "manager"),
};
