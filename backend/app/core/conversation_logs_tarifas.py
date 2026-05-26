"""
core/conversation_logs_tarifas.py
Log persistente separado para flujos determinísticos de tarifas.
Cada fila representa un flujo completo (inicio -> resolución/cancelación).
"""

import json
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
            CREATE TABLE IF NOT EXISTS conversation_logs_tarifas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                session_id TEXT NOT NULL,
                status TEXT NOT NULL,
                flow_text TEXT NOT NULL,
                flow_json TEXT NOT NULL,
                turns INTEGER NOT NULL DEFAULT 0,
                scope TEXT,
                peso TEXT,
                columna TEXT,
                servicio TEXT,
                precio TEXT,
                moneda TEXT,
                latency_ms INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_conv_tarifas_created_at ON conversation_logs_tarifas(created_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_conv_tarifas_session_id ON conversation_logs_tarifas(session_id)"
        )
        conn.commit()


def _build_flow_text(messages: list[dict]) -> str:
    lines: list[str] = []
    for msg in messages or []:
        role = "Usuario" if (msg.get("role") or "") == "user" else "Bot"
        content = (msg.get("content") or "").strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines).strip()


def log_tarifa_flow(
    *,
    session_id: str,
    status: str,
    flow_messages: list[dict],
    scope: str = "",
    peso: str = "",
    columna: str = "",
    servicio: str = "",
    precio: str = "",
    moneda: str = "Bs",
    latency_ms: int = 0,
) -> int | None:
    sid = (session_id or "").strip()
    normalized_status = (status or "").strip().lower() or "completed"
    messages = [m for m in (flow_messages or []) if isinstance(m, dict)]
    flow_text = _build_flow_text(messages)
    if not sid or not flow_text:
        return None

    created_at = datetime.now(timezone.utc).isoformat()
    flow_json = json.dumps(messages, ensure_ascii=False)
    turns = sum(1 for msg in messages if (msg.get("role") or "") == "user")

    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO conversation_logs_tarifas (
                created_at, session_id, status, flow_text, flow_json, turns,
                scope, peso, columna, servicio, precio, moneda, latency_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                created_at,
                sid,
                normalized_status,
                flow_text,
                flow_json,
                max(int(turns), 0),
                (scope or "").strip(),
                (peso or "").strip(),
                (columna or "").strip().upper(),
                (servicio or "").strip(),
                (precio or "").strip(),
                (moneda or "").strip() or "Bs",
                max(int(latency_ms or 0), 0),
            ),
        )
        conn.commit()
        return cur.lastrowid


def list_tarifa_conversations(limit: int = 300, offset: int = 0, q: str = "") -> dict:
    lim = max(1, min(int(limit or 300), 2000))
    off = max(int(offset or 0), 0)
    query = (q or "").strip()

    where = ""
    params: list = []
    if query:
        where = "WHERE flow_text LIKE ? OR status LIKE ? OR scope LIKE ? OR servicio LIKE ?"
        like = f"%{query}%"
        params.extend([like, like, like, like])

    with _connect() as conn:
        total_row = conn.execute(
            f"SELECT COUNT(*) AS total FROM conversation_logs_tarifas {where}",
            params,
        ).fetchone()
        rows = conn.execute(
            f"""
            SELECT id, created_at, session_id, status, flow_text, turns,
                   scope, peso, columna, servicio, precio, moneda, latency_ms
            FROM conversation_logs_tarifas
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
                "status": row["status"] or "",
                "flow_text": row["flow_text"] or "",
                "turns": int(row["turns"] or 0),
                "scope": row["scope"] or "",
                "peso": row["peso"] or "",
                "columna": row["columna"] or "",
                "servicio": row["servicio"] or "",
                "precio": row["precio"] or "",
                "moneda": row["moneda"] or "Bs",
                "latency_ms": int(row["latency_ms"] or 0),
            }
        )
    return {"items": items, "total": int(total_row["total"] or 0)}


def delete_tarifa_conversation(log_id: int) -> bool:
    lid = int(log_id)
    with _connect() as conn:
        cur = conn.execute("DELETE FROM conversation_logs_tarifas WHERE id = ?", (lid,))
        conn.commit()
        return cur.rowcount > 0


def clear_tarifa_conversations() -> int:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM conversation_logs_tarifas")
        conn.commit()
        return int(cur.rowcount or 0)


def stats() -> dict:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT
              COUNT(*) AS total,
              SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed,
              SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) AS cancelled,
              SUM(CASE WHEN status = 'reset' THEN 1 ELSE 0 END) AS reset,
              AVG(latency_ms) AS avg_latency_ms
            FROM conversation_logs_tarifas
            """
        ).fetchone()
    return {
        "total": int(row["total"] or 0),
        "completed": int(row["completed"] or 0),
        "cancelled": int(row["cancelled"] or 0),
        "reset": int(row["reset"] or 0),
        "avg_latency_ms": round(float(row["avg_latency_ms"] or 0), 1),
    }


init_db()
