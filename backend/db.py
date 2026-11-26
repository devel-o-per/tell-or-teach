"""A tiny storage layer: SQLite on your laptop, Postgres when deployed.

Set DATABASE_URL to a Postgres URL (Neon or Supabase) in production.
Leave it unset to use a local SQLite file.

Flagsmith stores the experiment events. This database keeps the extra
detail Flagsmith doesn't: confidence taps, groups, which AI answered,
tokens used, and every tutor turn.
"""
import os
import sqlite3
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

URL = os.getenv("DATABASE_URL") or "sqlite:///local.db"
IST = ZoneInfo("Asia/Kolkata")
IS_PG = URL.startswith(("postgres://", "postgresql://"))

ID_COL = "BIGSERIAL PRIMARY KEY" if IS_PG else "INTEGER PRIMARY KEY AUTOINCREMENT"

SCHEMA = [
    f"""CREATE TABLE IF NOT EXISTS answers (
        id {ID_COL},
        ts TEXT NOT NULL,
        day TEXT NOT NULL,
        uid TEXT NOT NULL,
        grp TEXT,
        subject TEXT,
        concept_id TEXT,
        qid TEXT,
        kind TEXT,
        correct INTEGER,
        confidence TEXT,
        position INTEGER
    )""",
    f"""CREATE TABLE IF NOT EXISTS tutor_turns (
        id {ID_COL},
        ts TEXT NOT NULL,
        day TEXT NOT NULL,
        uid TEXT NOT NULL,
        qid TEXT,
        turn INTEGER,
        style TEXT,
        in_experiment INTEGER,
        source TEXT,
        model TEXT,
        tokens INTEGER,
        latency_ms INTEGER,
        leak_retry INTEGER,
        fallback_reason TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS answers_day_grp ON answers (day, grp)",
    "CREATE INDEX IF NOT EXISTS turns_uid_day ON tutor_turns (uid, day)",
]


def _connect():
    if IS_PG:
        import psycopg  # installed from requirements.txt

        return psycopg.connect(URL, autocommit=True)
    return sqlite3.connect(URL.replace("sqlite:///", "", 1))


def _run(sql, params=(), fetch=False):
    if IS_PG:
        sql = sql.replace("?", "%s")
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall() if fetch else None
        if not IS_PG:
            conn.commit()
        return rows
    finally:
        conn.close()


def _now():
    now = datetime.now(timezone.utc)
    return now.isoformat(), now.astimezone(IST).date().isoformat()


def init():
    for statement in SCHEMA:
        _run(statement)


def log_answer(uid, grp, subject, concept_id, qid, kind, correct, confidence, position):
    ts, day = _now()
    _run(
        "INSERT INTO answers (ts, day, uid, grp, subject, concept_id, qid, kind, correct, confidence, position)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (ts, day, uid, grp, subject, concept_id, qid, kind, int(correct), confidence, position),
    )


def log_turn(uid, qid, turn, style, in_experiment, source, model, tokens, latency_ms, leak_retry, fallback_reason):
    ts, day = _now()
    _run(
        "INSERT INTO tutor_turns (ts, day, uid, qid, turn, style, in_experiment, source, model, tokens,"
        " latency_ms, leak_retry, fallback_reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (ts, day, uid, qid, turn, style, int(in_experiment), source, model, tokens, latency_ms,
         int(leak_retry), fallback_reason),
    )


def ai_turns_today(uid):
    _, day = _now()
    rows = _run(
        "SELECT COUNT(*) FROM tutor_turns WHERE uid = ? AND day = ? AND source <> 'written'",
        (uid, day),
        fetch=True,
    )
    return rows[0][0] if rows else 0


def students_today_by_group():
    _, day = _now()
    rows = _run(
        "SELECT grp, COUNT(DISTINCT uid) FROM answers WHERE day = ? GROUP BY grp",
        (day,),
        fetch=True,
    )
    return {grp or "direct": count for grp, count in rows}
