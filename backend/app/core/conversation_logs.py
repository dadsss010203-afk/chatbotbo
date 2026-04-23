"""
core/conversation_logs.py
Log persistente de conversaciones (separado del RAG/LLM).
"""

import os
import sqlite3
from datetime import datetime, timezone


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(BASE_DIR, "data")
CONVERSATIONS_DB = os.environ.get("CONVERSATIONS_DB", os.path.join(DATA_DIR, "conversations.db"))


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(CONVERSATIONS_DB), exist_ok=True)
    conn = sqlite3.connect(CONVERSATIONS_DB, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                session_id TEXT NOT NULL,
                request_id TEXT,
                question TEXT NOT NULL,
                response TEXT NOT NULL,
                lang TEXT,
                skill_id TEXT,
                primary_source_type TEXT,
                cache_hit INTEGER NOT NULL DEFAULT 0,
                latency_ms INTEGER NOT NULL DEFAULT 0,
                rating INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversation_logs_created_at ON conversation_logs(created_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversation_logs_session_id ON conversation_logs(session_id)"
        )
        # Migración simple para bases existentes sin columna rating.
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(conversation_logs)").fetchall()}
        if "rating" not in columns:
            conn.execute("ALTER TABLE conversation_logs ADD COLUMN rating INTEGER NOT NULL DEFAULT 0")
        if "request_id" not in columns:
            conn.execute("ALTER TABLE conversation_logs ADD COLUMN request_id TEXT")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversation_logs_request_id ON conversation_logs(request_id)"
        )
        conn.commit()


def log_conversation(
    *,
    session_id: str,
    request_id: str = "",
    question: str,
    response: str,
    lang: str = "",
    skill_id: str = "",
    primary_source_type: str = "",
    cache_hit: bool = False,
    latency_ms: int = 0,
) -> int | None:
    q = (question or "").strip()
    r = (response or "").strip()
    sid = (session_id or "").strip()
    if not q or not r or not sid:
        return None

    created_at = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO conversation_logs (
                created_at, session_id, request_id, question, response, lang, skill_id,
                primary_source_type, cache_hit, latency_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                created_at,
                sid,
                (request_id or "").strip(),
                q,
                r,
                (lang or "").strip().lower(),
                (skill_id or "").strip(),
                (primary_source_type or "").strip(),
                1 if cache_hit else 0,
                max(int(latency_ms or 0), 0),
            ),
        )
        conn.commit()
        return cur.lastrowid


def list_conversations(limit: int = 300, offset: int = 0, q: str = "") -> dict:
    lim = max(1, min(int(limit or 300), 2000))
    off = max(int(offset or 0), 0)
    query = (q or "").strip()

    where = ""
    params: list = []
    if query:
        where = "WHERE question LIKE ? OR response LIKE ? OR skill_id LIKE ? OR request_id LIKE ?"
        like = f"%{query}%"
        params.extend([like, like, like, like])

    with _connect() as conn:
        total_row = conn.execute(
            f"SELECT COUNT(*) AS total FROM conversation_logs {where}",
            params,
        ).fetchone()
        rows = conn.execute(
            f"""
            SELECT id, created_at, session_id, request_id, question, response, lang, skill_id,
                   primary_source_type, cache_hit, latency_ms, rating
            FROM conversation_logs
            {where}
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, lim, off],
        ).fetchall()

    items = []
    for row in rows:
        items.append(
            {
                "id": int(row["id"]),
                "created_at": row["created_at"],
                "session_id": row["session_id"],
                "request_id": row["request_id"] or "",
                "question": row["question"],
                "response": row["response"],
                "lang": row["lang"] or "",
                "skill_id": row["skill_id"] or "",
                "primary_source_type": row["primary_source_type"] or "",
                "cache_hit": bool(row["cache_hit"]),
                "latency_ms": int(row["latency_ms"] or 0),
                "rating": int(row["rating"] or 0),
            }
        )
    return {"items": items, "total": int(total_row["total"] or 0)}


def delete_conversation(log_id: int) -> bool:
    lid = int(log_id)
    with _connect() as conn:
        cur = conn.execute("DELETE FROM conversation_logs WHERE id = ?", (lid,))
        conn.commit()
        return cur.rowcount > 0


def clear_conversations() -> int:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM conversation_logs")
        conn.commit()
        return int(cur.rowcount or 0)


def set_rating(log_id: int, rating: int) -> bool:
    """rating: 1 (like), -1 (dislike), 0 (sin calificar)."""
    lid = int(log_id)
    value = int(rating)
    if value not in (-1, 0, 1):
        raise ValueError("rating inválido")
    with _connect() as conn:
        cur = conn.execute("UPDATE conversation_logs SET rating = ? WHERE id = ?", (value, lid))
        conn.commit()
        return cur.rowcount > 0


def stats() -> dict:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT
              COUNT(*) AS total,
              SUM(CASE WHEN cache_hit = 1 THEN 1 ELSE 0 END) AS cache_hits,
              SUM(CASE WHEN rating = 1 THEN 1 ELSE 0 END) AS likes,
              SUM(CASE WHEN rating = -1 THEN 1 ELSE 0 END) AS dislikes,
              AVG(latency_ms) AS avg_latency_ms
            FROM conversation_logs
            """
        ).fetchone()
    return {
        "total": int(row["total"] or 0),
        "cache_hits": int(row["cache_hits"] or 0),
        "likes": int(row["likes"] or 0),
        "dislikes": int(row["dislikes"] or 0),
        "avg_latency_ms": round(float(row["avg_latency_ms"] or 0), 1),
    }


# Inicializa esquema al importar módulo.
init_db()
