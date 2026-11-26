"""The tutor: two teaching styles, one chain of AI providers, one leak guard.

Fairness rules (keep these true, they are what makes the experiment valid):
  * Both styles use the same provider chain, in the same order, with the same token cap.
  * When the AI is unavailable, each style falls back to its own written version,
    so a student's teaching style never changes, only who writes the words.
  * Every reply is logged with the provider that wrote it, so the README can show
    both groups got a similar mix.
"""
import logging
import os
import re
import time

import requests

import db
import flags
from questions import LETTERS

log = logging.getLogger(__name__)

MAX_TOKENS = int(os.getenv("TUTOR_MAX_TOKENS", "300"))
PROVIDER_TIMEOUT = float(os.getenv("PROVIDER_TIMEOUT_S", "7"))
CHAIN_BUDGET = float(os.getenv("CHAIN_BUDGET_S", "12"))

# Model IDs change: copy the exact ID from each provider's console into your .env.
PROVIDERS = {
    "groq": {
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "key_env": "GROQ_API_KEY",
        "model_env": "GROQ_MODEL",
        "default_model": "llama-3.3-70b-versatile",
    },
    "nvidia": {
        "url": "https://integrate.api.nvidia.com/v1/chat/completions",
        "key_env": "NVIDIA_API_KEY",
        "model_env": "NVIDIA_MODEL",
        "default_model": "nvidia/nvidia-nemotron-nano-9b-v2",
    },
    "gemini": {
        "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "key_env": "GEMINI_API_KEY",
        "model_env": "GEMINI_MODEL",
        "default_model": "gemini-2.5-flash",
    },
}

TELL_PROMPT = """You are a friendly tutor for university students.
The student just answered a multiple-choice question incorrectly.
Explain clearly why the correct answer is right and why the student's choice is wrong.
Use plain language, under 120 words, no headings.
If the student asks a follow-up question, answer it directly in under 80 words."""

TEACH_PROMPT = """You are a Socratic tutor for university students.
The student just answered a multiple-choice question incorrectly. Help them find the answer themselves.
Rules you must never break:
- Never state the correct option letter or the correct option's text.
- Never say which option is right or which options are wrong.
- Ask exactly one short guiding question per reply, under 60 words.
- Build on what the student just said. Do not lecture."""

STRICT_NOTE = """Your previous draft revealed the answer. Rewrite it.
Do not mention any option letter or any option's wording at all. Ask one guiding question only."""

WRITTEN_RETRY = "Have another go: pick an option again."


# ---------- the leak guard ----------

def _norm(text):
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def leaks_answer(text, q):
    """True if a Teach reply gives away the correct option."""
    letter = LETTERS[q["answer"]]
    answer = _norm(q["options"][q["answer"]])
    # "option B", "the answer is B", "answer: (B)", "(B)", "B)"
    letter_patterns = [
        rf"(?i:\b(?:option|answer|choice))\s*(?i:is)?\s*:?\s*\(?{letter}\)?(?![A-Za-z0-9])",
        rf"\({letter}\)",
        rf"(?<![A-Za-z0-9]){letter}\)",
    ]
    if any(re.search(p, text or "") for p in letter_patterns):
        return True
    reply = _norm(text)
    if len(answer) >= 12:
        return answer in reply
    # Short answers like "0" or "true" only count when stated as the answer.
    return bool(re.search(
        rf"(?:answer|correct|right)\W+(?:\w+\W+){{0,6}}{re.escape(answer)}(?!\w)", reply))


# ---------- talking to the AI providers ----------

def provider_order():
    names = os.getenv("PROVIDER_ORDER", "groq,nvidia,gemini").split(",")
    return [n.strip() for n in names if n.strip() in PROVIDERS and os.getenv(PROVIDERS[n.strip()]["key_env"])]


def _strip_thinking(text):
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    return text.strip()


def _call(name, messages):
    p = PROVIDERS[name]
    model = os.getenv(p["model_env"], p["default_model"])
    if "nemotron" in model.lower():  # Nemotron thinks out loud unless told not to
        messages = [{"role": "system", "content": "/no_think\n" + messages[0]["content"]}] + messages[1:]
    payload = {"model": model, "messages": messages, "max_tokens": MAX_TOKENS, "temperature": 0.3}
    if "gpt-oss" in model:  # Groq's gpt-oss models reason first: keep it short and hidden
        payload.update(reasoning_effort="low", include_reasoning=False, max_tokens=MAX_TOKENS + 500)
    started = time.monotonic()
    resp = requests.post(
        p["url"],
        headers={"Authorization": f"Bearer {os.environ[p['key_env']]}"},
        json=payload,
        timeout=PROVIDER_TIMEOUT,
    )
    resp.raise_for_status()
    body = resp.json()
    text = _strip_thinking(body["choices"][0]["message"].get("content"))
    if not text:
        raise ValueError("empty reply")
    tokens = (body.get("usage") or {}).get("total_tokens") or 0
    return {"text": text, "source": name, "model": model, "tokens": tokens,
            "latency_ms": int((time.monotonic() - started) * 1000)}


def call_chain(messages):
    """Try each provider in order until one answers, within the time budget."""
    started = time.monotonic()
    for name in provider_order():
        if time.monotonic() - started > CHAIN_BUDGET:
            break
        try:
            return _call(name, messages)
        except Exception as exc:
            log.warning("Provider %s failed: %s", name, exc)
    return None


def build_messages(style, q, chosen, history, message, strict=False):
    options = "\n".join(f"{LETTERS[i]}) {opt}" for i, opt in enumerate(q["options"]))
    context = (
        f"Question: {q['question']}\nOptions:\n{options}\n"
        f"Correct answer (for your reference only): {LETTERS[q['answer']]}) {q['options'][q['answer']]}\n"
        f"Reference explanation: {q['explanation']}\n"
        f"The student chose: {LETTERS[chosen]}) {q['options'][chosen]}"
    )
    system = TELL_PROMPT if style == "tell" else TEACH_PROMPT
    if strict:
        system += "\n\n" + STRICT_NOTE
    messages = [{"role": "system", "content": system}, {"role": "user", "content": context}]
    messages += history
    if message:
        messages.append({"role": "user", "content": message})
    elif history:
        messages.append({"role": "user", "content": "Please continue."})
    return messages


# ---------- written fallbacks, one per style ----------

def written(style, q, turn):
    if style == "teach":
        return q["hints"][turn] if turn < len(q["hints"]) else WRITTEN_RETRY
    if turn == 0:
        return q["explanation"]
    return "The AI tutor is resting right now, so here's the explanation again: " + q["explanation"]


# ---------- one tutor reply ----------

def respond(uid, q, chosen, turn, history, message):
    student_flags = flags.for_identity(uid)
    if student_flags is None:
        # Without Flagsmith we can't know the student's group, so no exposure is recorded.
        style, in_experiment, limits = "tell", False, dict(flags.DEFAULT_LIMITS)
        reason = "flagsmith_unreachable"
    else:
        style, in_experiment, style_flag = flags.style_of(student_flags)
        limits = flags.limits(student_flags)
        if turn == 0 and in_experiment:
            flags.track_exposure(uid, style_flag)
        if turn >= limits["max_turns"]:
            reason = "max_turns"
        elif not flags.ai_enabled(student_flags):
            reason = "kill_switch"
        elif db.ai_turns_today(uid) >= limits["daily_cap"]:
            reason = "daily_cap"
        else:
            reason = None

    turns_left = max(limits["max_turns"] - turn - 1, 0)
    result, leak_retry = None, False
    if reason is None:
        result = call_chain(build_messages(style, q, chosen, history, message))
        if result and style == "teach" and leaks_answer(result["text"], q):
            leak_retry = True
            result = call_chain(build_messages(style, q, chosen, history, message, strict=True))
            if result and leaks_answer(result["text"], q):
                result, reason = None, "leak"
        if result is None and reason is None:
            reason = "providers_failed"

    if result is None:
        result = {"text": written(style, q, turn), "source": "written", "model": None,
                  "tokens": 0, "latency_ms": 0}

    logged_style = "unknown" if reason == "flagsmith_unreachable" else style
    db.log_turn(uid, q["id"], turn, logged_style, in_experiment, result["source"], result["model"],
                result["tokens"], result["latency_ms"], leak_retry, reason)
    return {"style": style, "reply": result["text"], "source": result["source"], "turnsLeft": turns_left}
