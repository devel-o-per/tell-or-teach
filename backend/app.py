"""Tell Me or Teach Me: the Flask API.

Routes
  GET  /api/health  is the server awake, and which AI providers are configured
  POST /api/tutor   one tutor reply after a wrong answer
  POST /api/answer  log one answer (original, comeback or retry) for analysis
  GET  /api/stats   how many students practised today, per WhatsApp group
"""
import logging
import os
import re
from pathlib import Path

try:  # load backend/.env when running locally
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).with_name(".env"))
except ImportError:
    pass

from flask import Flask, jsonify, request

import db
import tutor
from questions import QuestionBank

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

app = Flask(__name__)
ALLOWED_ORIGIN = os.getenv("ALLOWED_ORIGIN", "*")
QUESTIONS_DIR = os.getenv("QUESTIONS_DIR", str(Path(__file__).resolve().parent.parent / "frontend" / "questions"))

UID_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")
GROUP_RE = re.compile(r"^[a-z0-9-]{1,24}$")
KINDS = {"original", "comeback", "retry"}
CONFIDENCE = {"sure", "guess"}
MAX_MESSAGE = 400
MAX_HISTORY = 8

bank = QuestionBank(QUESTIONS_DIR)
db.init()


@app.after_request
def add_cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGIN
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp


@app.route("/api/<path:_any>", methods=["OPTIONS"])
def preflight(_any):
    return "", 204


def bad(message, code=400):
    return jsonify({"error": message}), code


def clean_history(raw):
    """Keep only the last few user/assistant turns, each trimmed."""
    if not isinstance(raw, list):
        return []
    history = []
    for item in raw[-MAX_HISTORY:]:
        if isinstance(item, dict) and item.get("role") in ("user", "assistant") and isinstance(item.get("content"), str):
            history.append({"role": item["role"], "content": item["content"][:600]})
    return history


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "providers": tutor.provider_order(), "questions": len(bank.by_id)})


@app.post("/api/tutor")
def tutor_reply():
    data = request.get_json(silent=True) or {}
    uid = data.get("uid", "")
    q = bank.get(data.get("qid", ""))
    chosen, turn = data.get("chosen"), data.get("turn")
    message = (data.get("message") or "").strip()[:MAX_MESSAGE]
    if not UID_RE.match(uid):
        return bad("invalid uid")
    if q is None:
        return bad("unknown question", 404)
    if not isinstance(chosen, int) or not 0 <= chosen < len(q["options"]) or chosen == q["answer"]:
        return bad("chosen must be a wrong option of this question")
    if not isinstance(turn, int) or not 0 <= turn < 10:
        return bad("invalid turn")
    return jsonify(tutor.respond(uid, q, chosen, turn, clean_history(data.get("history")), message))


@app.post("/api/answer")
def answer():
    data = request.get_json(silent=True) or {}
    uid, group = data.get("uid", ""), data.get("group") or "direct"
    q = bank.get(data.get("qid", ""))
    kind, confidence = data.get("kind"), data.get("confidence")
    if not UID_RE.match(uid) or not GROUP_RE.match(group):
        return bad("invalid uid or group")
    if q is None or kind not in KINDS or not isinstance(data.get("correct"), bool):
        return bad("invalid answer")
    if confidence not in CONFIDENCE:
        confidence = None
    position = data.get("position") if isinstance(data.get("position"), int) else None
    db.log_answer(uid, group, q["subject"], q["concept_id"], q["id"], kind, data["correct"], confidence, position)
    return jsonify({"ok": True})


@app.get("/api/stats")
def stats():
    return jsonify({"studentsToday": db.students_today_by_group()})


if __name__ == "__main__":
    app.run(port=int(os.getenv("PORT", "5000")), debug=True)
