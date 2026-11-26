"""Everything the server asks Flagsmith.

Four flags live in Flagsmith:
  tutor_style       multivariate: "tell" (control) or "teach" (treatment), the experiment
  ai_tutor_enabled  on/off kill switch for the live AI
  tutor_limits      JSON, e.g. {"max_turns": 3, "daily_cap": 40}
  question_set      read by the browser, e.g. "mlt,viva"
"""
import json
import logging
import os
import threading

log = logging.getLogger(__name__)

DEFAULT_LIMITS = {"max_turns": 3, "daily_cap": 40}
_client = None
_client_lock = threading.Lock()


def client():
    """Create the Flagsmith client once per process, with events turned on.

    The lock stops two request threads from each building a client (and its
    background event thread) at the same moment under gunicorn --threads.
    """
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                key = os.getenv("FLAGSMITH_SERVER_KEY")
                if not key:
                    log.warning("FLAGSMITH_SERVER_KEY is not set: every student gets the written Tell content")
                    return None
                from flagsmith import Flagsmith

                kwargs = {"environment_key": key, "enable_events": True}
                if os.getenv("FLAGSMITH_API_URL"):  # only for self-hosted Flagsmith
                    kwargs["api_url"] = os.environ["FLAGSMITH_API_URL"]
                _client = Flagsmith(**kwargs)
    return _client


def for_identity(uid):
    """The student's flags, or None if Flagsmith can't be reached."""
    c = client()
    if c is None:
        return None
    try:
        return c.get_identity_flags(identifier=uid)
    except Exception:  # network trouble must never break the tutor
        log.exception("Could not fetch flags for %s", uid)
        return None


def style_of(flags):
    """Return (style, in_experiment, flag) for the tutor_style flag."""
    flag = flags.get_flag("tutor_style")
    style = flag.value if flag.value in ("tell", "teach") else "tell"
    experiment = getattr(flag, "experiment", None)
    in_experiment = bool(experiment and getattr(experiment, "in_experiment", False))
    return style, in_experiment, flag


def track_exposure(uid, flag):
    """Tell Flagsmith this student has now actually seen their tutor style."""
    try:
        client().track_exposure_event("tutor_style", identifier=uid, value=flag.variant)
    except Exception:
        log.exception("Could not record exposure for %s", uid)


def ai_enabled(flags):
    try:
        return flags.is_feature_enabled("ai_tutor_enabled")
    except Exception:
        return False


def limits(flags):
    """Read tutor_limits, falling back to safe defaults for anything missing or broken."""
    result = dict(DEFAULT_LIMITS)
    try:
        raw = flags.get_feature_value("tutor_limits")
        data = raw if isinstance(raw, dict) else json.loads(raw or "{}")
        for key in result:
            if isinstance(data.get(key), int) and data[key] >= 0:
                result[key] = data[key]
    except Exception:
        log.warning("tutor_limits is missing or not valid JSON; using defaults")
    return result
