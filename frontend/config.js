// Settings the browser needs. Both values are safe to be public:
// the client-side Flagsmith key is designed to live in browsers.
window.APP_CONFIG = {
  API_BASE: 'http://localhost:5000',             // your deployed Flask URL in production
  FLAGSMITH_CLIENT_KEY: 'PASTE_CLIENT_SIDE_KEY', // Environment settings > Keys > client-side key
  DEBUG: false,                                  // true prints Flagsmith logs in the console
};
