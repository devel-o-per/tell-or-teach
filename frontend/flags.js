/*
 * Everything the browser asks Flagsmith.
 *
 * The browser only reads the question_set flag and sends events:
 *   question_answered   every scored answer (practice volume)
 *   comeback_scored     1 or 0 on every comeback question (the primary metric)
 * The tutor_style flag is read on the server, which also records the exposure.
 * Both use the same anonymous ID, so Flagsmith joins them per student.
 */
(function () {
  const cfg = window.APP_CONFIG;
  let fs = null;
  let ready = false;

  async function loadSdk() {
    if (window.flagsmith) return window.flagsmith;
    // If the script tag didn't create a global, load the ES module build instead.
    const mod = await import('https://esm.sh/@flagsmith/flagsmith@12.6.0');
    return mod.default || mod;
  }

  async function init(uid, group) {
    try {
      fs = await loadSdk();
      await fs.init({ environmentID: cfg.FLAGSMITH_CLIENT_KEY, enableEvents: true, enableLogs: !!cfg.DEBUG });
      try {
        await fs.identify(uid, { group });
      } catch (e) {
        await fs.identify(uid);
        if (fs.setTrait) await fs.setTrait('group', group);
      }
      ready = true;
    } catch (e) {
      console.warn('Flagsmith could not start; the quiz still works but no events are sent.', e);
    }
    return ready;
  }

  function value(name, fallback) {
    try {
      const v = fs && fs.getValue(name);
      return v === undefined || v === null || v === '' ? fallback : v;
    } catch (e) {
      return fallback;
    }
  }

  function track(name, val) {
    if (!ready) return;
    try {
      if (val === undefined) fs.trackEvent(name);
      else fs.trackEvent(name, { value: val });
    } catch (e) {
      console.warn('Event not sent:', name, e);
    }
  }

  function flush() {
    try {
      if (ready && fs.flushEvents) fs.flushEvents();
    } catch (e) { /* nothing useful to do */ }
  }

  window.Flags = { init, value, track, flush };
})();
