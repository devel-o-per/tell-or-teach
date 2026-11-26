// Settings the browser needs, chosen by where the page runs. All values are safe
// to be public: the client-side Flagsmith key is designed to live in browsers.
(function () {
  const local = ['localhost', '127.0.0.1'].includes(location.hostname);

  window.APP_CONFIG = local
    ? {
      API_BASE: 'http://localhost:5000',
      FLAGSMITH_CLIENT_KEY: 'NsXTSy35PD7weLYVtDek88', // Development environment client-side key
      DEBUG: false,                                  // true prints Flagsmith logs in the console
    }
    : {
      API_BASE: 'https://tell-or-teach.onrender.com',
      FLAGSMITH_CLIENT_KEY: 'a7vkbJ5bbDUXvDMux4GQDy', // Production environment client-side key
      DEBUG: false,
    };
})();
