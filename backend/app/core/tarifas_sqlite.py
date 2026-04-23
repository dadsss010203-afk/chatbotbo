"""
core/tarifas_sqlite.py
Motor SQLite para tarifas postales (catálogo + cálculo + gestión CRUD).
"""

from __future__ import annotations

import importlib.util
import os
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DEFAULT_DB_PATH = Path(os.environ.get("TARIFFS_DB", str(DATA_DIR / "tarifas.db")))

_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    target = Path(db_path or DEFAULT_DB_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target), timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str | Path | None = None) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tariff_rate (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope TEXT NOT NULL,
                column_code TEXT NOT NULL,
                min_g REAL NOT NULL,
                max_g REAL NOT NULL,
                price_bs REAL NOT NULL,
                row_order INTEGER NOT NULL DEFAULT 0,
                service_label TEXT,
                source_sheet TEXT,
                source_file TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_tariff_lookup
            ON tariff_rate(scope, column_code, active, max_g, row_order)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_tariff_scope_col
            ON tariff_rate(scope, column_code)
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tariff_meta (
                meta_key TEXT PRIMARY KEY,
                meta_value TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def parse_peso_to_grams(texto: str) -> float:
    if texto is None:
        raise ValueError("Peso vacío")
    t = str(texto).strip().lower().replace(" ", "").replace(",", ".")
    t = t.replace(".kg", "kg").replace(".gr", "gr").replace(".g", "g")
    m = re.match(r"^([0-9]*\.?[0-9]+)(kg|k|g|gr|gramo|gramos|kilo|kilos|kilogramo|kilogramos)$", t)
    if not m:
        raise ValueError(f"Formato de peso inválido: {texto}")
    value = float(m.group(1))
    unit = m.group(2)
    if value <= 0:
        raise ValueError(f"Peso inválido (debe ser > 0): {texto}")
    return value * 1000.0 if unit.startswith("k") else value


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except Exception:
        return None


def _runtime_path_from_wrapper(wrapper_path: str) -> Path:
    p = str(wrapper_path).replace("\\", "/")
    p = p.replace("/tools/", "/runtime/").replace("_json.sh", "_runtime.py")
    return Path(p)


def _load_runtime_module(runtime_path: Path):
    if not runtime_path.exists():
        raise FileNotFoundError(f"Runtime no encontrado: {runtime_path}")
    module_name = f"tariff_runtime_{runtime_path.parent.parent.name}_{runtime_path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, str(runtime_path))
    if not spec or not spec.loader:
        raise RuntimeError(f"No se pudo cargar spec de runtime: {runtime_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


def _normalize_service_label(columnas: dict, col: str) -> str:
    value = columnas.get(col)
    if isinstance(value, list) and value:
        return str(value[0]).strip()
    return str(value or col).strip()


def _extract_records_from_runtime(scope: str, runtime_module, xlsx_path: str) -> list[dict]:
    rows = runtime_module.load_table_rows(str(xlsx_path))
    columnas: dict = dict(getattr(runtime_module, "COLUMNAS", {}))
    sheet_name = str(getattr(runtime_module, "SHEET_NAME", "")).strip()

    records: list[dict] = []
    for row in rows:
        row_order = int(row.get("row_idx") or 0)
        prices = row.get("precios") or {}

        if "min_g" in row and "max_g" in row:
            min_g = _to_float(row.get("min_g"))
            max_g = _to_float(row.get("max_g"))
        elif "w_g" in row:
            w = _to_float(row.get("w_g"))
            min_g = w
            max_g = w
        else:
            continue

        if min_g is None or max_g is None:
            continue

        for col, raw_price in prices.items():
            col_code = str(col or "").strip().upper()
            price = _to_float(raw_price)
            if not col_code or price is None:
                continue

            records.append(
                {
                    "scope": scope,
                    "column_code": col_code,
                    "min_g": float(min_g),
                    "max_g": float(max_g),
                    "price_bs": float(price),
                    "row_order": row_order,
                    "service_label": _normalize_service_label(columnas, col_code),
                    "source_sheet": sheet_name,
                }
            )
    return records


def rebuild_catalog_from_xlsx(skill_config: dict, db_path: str | Path | None = None) -> dict:
    init_db(db_path)
    inserted = 0
    skipped_scopes: list[str] = []
    errors: list[str] = []

    with _LOCK:
        with _connect(db_path) as conn:
            conn.execute("DELETE FROM tariff_rate")

            for scope, cfg in skill_config.items():
                wrapper = cfg.get("wrapper")
                if not wrapper:
                    skipped_scopes.append(scope)
                    continue

                try:
                    runtime_path = _runtime_path_from_wrapper(wrapper)
                    runtime_module = _load_runtime_module(runtime_path)
                    xlsx_path = getattr(runtime_module, "DEFAULT_XLSX", None)
                    if xlsx_path is None or not Path(xlsx_path).exists():
                        raise FileNotFoundError(f"XLSX no encontrado para {scope}: {xlsx_path}")

                    records = _extract_records_from_runtime(scope, runtime_module, str(xlsx_path))
                    if not records:
                        skipped_scopes.append(scope)
                        continue

                    now = _now_iso()
                    for rec in records:
                        conn.execute(
                            """
                            INSERT INTO tariff_rate (
                                scope, column_code, min_g, max_g, price_bs, row_order,
                                service_label, source_sheet, source_file, active,
                                created_at, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                            """,
                            (
                                rec["scope"],
                                rec["column_code"],
                                rec["min_g"],
                                rec["max_g"],
                                rec["price_bs"],
                                rec["row_order"],
                                rec["service_label"],
                                rec["source_sheet"],
                                str(xlsx_path),
                                now,
                                now,
                            ),
                        )
                        inserted += 1
                except Exception as exc:
                    errors.append(f"{scope}: {exc}")

            conn.execute(
                """
                INSERT INTO tariff_meta(meta_key, meta_value, updated_at)
                VALUES('last_rebuild_status', ?, ?)
                ON CONFLICT(meta_key) DO UPDATE SET
                  meta_value = excluded.meta_value,
                  updated_at = excluded.updated_at
                """,
                ("ok" if not errors else "partial", _now_iso()),
            )
            conn.execute(
                """
                INSERT INTO tariff_meta(meta_key, meta_value, updated_at)
                VALUES('last_rebuild_rows', ?, ?)
                ON CONFLICT(meta_key) DO UPDATE SET
                  meta_value = excluded.meta_value,
                  updated_at = excluded.updated_at
                """,
                (str(inserted), _now_iso()),
            )
            conn.commit()

    return {
        "ok": True,
        "inserted": inserted,
        "skipped_scopes": skipped_scopes,
        "errors": errors,
        "partial": bool(errors),
    }


def _count_rates(db_path: str | Path | None = None) -> int:
    init_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) AS total FROM tariff_rate WHERE active = 1").fetchone()
        return int(row["total"] if row else 0)


def ensure_catalog(skill_config: dict, db_path: str | Path | None = None) -> dict:
    init_db(db_path)
    with _connect(db_path) as conn:
        total_row = conn.execute("SELECT COUNT(*) AS total FROM tariff_rate WHERE active = 1").fetchone()
        present_rows = conn.execute("SELECT DISTINCT scope FROM tariff_rate WHERE active = 1").fetchall()
    total = int(total_row["total"] if total_row else 0)
    present_scopes = {str(row["scope"] or "").strip().lower() for row in present_rows}
    expected_scopes = {str(scope).strip().lower() for scope in skill_config.keys()}

    if total > 0 and expected_scopes.issubset(present_scopes):
        return {"ok": True, "loaded": True, "inserted": 0}
    return rebuild_catalog_from_xlsx(skill_config=skill_config, db_path=db_path)


def calculate_tariff(
    *,
    scope: str,
    peso: str,
    columna: str,
    skill_config: dict,
    db_path: str | Path | None = None,
    auto_seed: bool = True,
) -> dict:
    sc = (scope or "").strip().lower()
    col = (columna or "").strip().upper()
    raw_peso = (peso or "").strip().lower()

    if not sc or sc not in skill_config:
        return {"ok": False, "error": f"Scope de tarifa no soportado: {scope}"}
    if not raw_peso:
        return {"ok": False, "error": "Falta peso"}
    if col not in set(skill_config[sc].get("columns") or set()):
        return {"ok": False, "error": f"Columna inválida para scope {sc}: {col}"}

    try:
        peso_g = parse_peso_to_grams(raw_peso)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    if auto_seed:
        seeded = ensure_catalog(skill_config=skill_config, db_path=db_path)
        if seeded.get("partial") and seeded.get("inserted", 0) <= 0:
            return {"ok": False, "error": "No se pudo inicializar el catálogo tarifario SQLite", "detail": seeded}

    init_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT id, scope, column_code, min_g, max_g, price_bs, row_order, service_label, source_sheet
            FROM tariff_rate
            WHERE scope = ?
              AND column_code = ?
              AND active = 1
              AND max_g >= ?
            ORDER BY max_g ASC, row_order ASC
            LIMIT 1
            """,
            (sc, col, float(peso_g)),
        ).fetchone()

    if not row:
        return {
            "ok": False,
            "error": "Peso fuera de rango para este tarifario",
            "error_code": "out_of_range",
            "scope": sc,
        }

    return {
        "ok": True,
        "precio": float(row["price_bs"]),
        "columna": row["column_code"],
        "servicio": row["service_label"] or row["column_code"],
        "fila": int(row["row_order"] or 0),
        "rango": {
            "min_g": float(row["min_g"]),
            "max_g": float(row["max_g"]),
        },
        "peso_g": float(peso_g),
        "scope": sc,
        "source_sheet": row["source_sheet"] or "",
    }


def list_rates(
    *,
    scope: str = "",
    column_code: str = "",
    limit: int = 500,
    offset: int = 0,
    db_path: str | Path | None = None,
) -> dict:
    init_db(db_path)
    lim = max(1, min(int(limit or 500), 5000))
    off = max(int(offset or 0), 0)

    where = ["active = 1"]
    params: list[Any] = []

    sc = (scope or "").strip().lower()
    if sc:
        where.append("scope = ?")
        params.append(sc)

    col = (column_code or "").strip().upper()
    if col:
        where.append("column_code = ?")
        params.append(col)

    where_sql = " AND ".join(where)

    with _connect(db_path) as conn:
        total_row = conn.execute(
            f"SELECT COUNT(*) AS total FROM tariff_rate WHERE {where_sql}",
            params,
        ).fetchone()
        rows = conn.execute(
            f"""
            SELECT id, scope, column_code, min_g, max_g, price_bs, row_order,
                   service_label, source_sheet, source_file, created_at, updated_at
            FROM tariff_rate
            WHERE {where_sql}
            ORDER BY scope ASC, column_code ASC, max_g ASC, row_order ASC
            LIMIT ? OFFSET ?
            """,
            [*params, lim, off],
        ).fetchall()

    items = [
        {
            "id": int(r["id"]),
            "scope": r["scope"],
            "column_code": r["column_code"],
            "min_g": float(r["min_g"]),
            "max_g": float(r["max_g"]),
            "price_bs": float(r["price_bs"]),
            "row_order": int(r["row_order"] or 0),
            "service_label": r["service_label"] or "",
            "source_sheet": r["source_sheet"] or "",
            "source_file": r["source_file"] or "",
            "created_at": r["created_at"] or "",
            "updated_at": r["updated_at"] or "",
        }
        for r in rows
    ]

    return {"items": items, "total": int(total_row["total"] if total_row else 0)}


def create_rate(payload: dict, db_path: str | Path | None = None) -> dict:
    init_db(db_path)
    now = _now_iso()

    scope = str(payload.get("scope") or "").strip().lower()
    column_code = str(payload.get("column_code") or "").strip().upper()
    min_g = _to_float(payload.get("min_g"))
    max_g = _to_float(payload.get("max_g"))
    price_bs = _to_float(payload.get("price_bs"))
    row_order = int(_to_float(payload.get("row_order")) or 0)
    service_label = str(payload.get("service_label") or "").strip()
    source_sheet = str(payload.get("source_sheet") or "manual").strip()
    source_file = str(payload.get("source_file") or "").strip()

    if not scope:
        raise ValueError("scope es obligatorio")
    if not column_code:
        raise ValueError("column_code es obligatorio")
    if min_g is None or max_g is None:
        raise ValueError("min_g y max_g son obligatorios")
    if price_bs is None:
        raise ValueError("price_bs es obligatorio")
    if min_g > max_g:
        raise ValueError("min_g no puede ser mayor que max_g")

    with _connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO tariff_rate (
                scope, column_code, min_g, max_g, price_bs, row_order,
                service_label, source_sheet, source_file, active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                scope,
                column_code,
                float(min_g),
                float(max_g),
                float(price_bs),
                row_order,
                service_label,
                source_sheet,
                source_file,
                now,
                now,
            ),
        )
        conn.commit()
        return {"ok": True, "id": int(cur.lastrowid)}


def update_rate(rate_id: int, payload: dict, db_path: str | Path | None = None) -> dict:
    init_db(db_path)
    rid = int(rate_id)
    with _connect(db_path) as conn:
        current = conn.execute(
            """
            SELECT id, scope, column_code, min_g, max_g, price_bs, row_order,
                   service_label, source_sheet, source_file, active
            FROM tariff_rate
            WHERE id = ?
            """,
            (rid,),
        ).fetchone()
    if not current:
        return {"ok": False, "error": "Tarifa no encontrada"}

    fields = []
    params: list[Any] = []

    mapping = {
        "scope": (lambda v: str(v).strip().lower()),
        "column_code": (lambda v: str(v).strip().upper()),
        "min_g": (lambda v: float(v)),
        "max_g": (lambda v: float(v)),
        "price_bs": (lambda v: float(v)),
        "row_order": (lambda v: int(v)),
        "service_label": (lambda v: str(v).strip()),
        "source_sheet": (lambda v: str(v).strip()),
        "source_file": (lambda v: str(v).strip()),
        "active": (lambda v: 1 if bool(v) else 0),
    }

    for key, caster in mapping.items():
        if key in payload:
            value = payload.get(key)
            if key in {"min_g", "max_g", "price_bs"}:
                value = _to_float(value)
                if value is None:
                    raise ValueError(f"{key} inválido")
            fields.append(f"{key} = ?")
            params.append(caster(value))

    new_min_g = _to_float(payload.get("min_g")) if "min_g" in payload else float(current["min_g"])
    new_max_g = _to_float(payload.get("max_g")) if "max_g" in payload else float(current["max_g"])
    if new_min_g is None or new_max_g is None:
        raise ValueError("min_g y max_g inválidos")
    if float(new_min_g) > float(new_max_g):
        raise ValueError("min_g no puede ser mayor que max_g")

    if not fields:
        raise ValueError("No hay campos para actualizar")

    fields.append("updated_at = ?")
    params.append(_now_iso())
    params.append(rid)

    with _connect(db_path) as conn:
        cur = conn.execute(
            f"UPDATE tariff_rate SET {', '.join(fields)} WHERE id = ?",
            params,
        )
        conn.commit()
        if cur.rowcount <= 0:
            return {"ok": False, "error": "Tarifa no encontrada"}
    return {"ok": True, "id": rid}


def delete_rate(rate_id: int, db_path: str | Path | None = None) -> bool:
    init_db(db_path)
    rid = int(rate_id)
    with _connect(db_path) as conn:
        cur = conn.execute("DELETE FROM tariff_rate WHERE id = ?", (rid,))
        conn.commit()
        return cur.rowcount > 0


def stats(skill_config: dict, db_path: str | Path | None = None) -> dict:
    init_db(db_path)
    with _connect(db_path) as conn:
        total_row = conn.execute("SELECT COUNT(*) AS total FROM tariff_rate WHERE active = 1").fetchone()
        scopes_rows = conn.execute(
            "SELECT scope, COUNT(*) AS total FROM tariff_rate WHERE active = 1 GROUP BY scope ORDER BY scope"
        ).fetchall()
        updated_row = conn.execute("SELECT MAX(updated_at) AS last_updated FROM tariff_rate WHERE active = 1").fetchone()
        meta_rows = conn.execute("SELECT meta_key, meta_value, updated_at FROM tariff_meta").fetchall()

    return {
        "available": True,
        "db_path": str(Path(db_path or DEFAULT_DB_PATH)),
        "total_rates": int(total_row["total"] if total_row else 0),
        "scopes": [
            {"scope": row["scope"], "total": int(row["total"])}
            for row in scopes_rows
        ],
        "supported_scopes": [
            {
                "scope": scope,
                "label": (cfg.get("label") or scope),
                "columns": sorted(list(cfg.get("columns") or [])),
                "skill_id": cfg.get("skill_id") or "",
            }
            for scope, cfg in sorted(skill_config.items())
        ],
        "last_updated": (updated_row["last_updated"] if updated_row else "") or "",
        "meta": [
            {
                "key": row["meta_key"],
                "value": row["meta_value"] or "",
                "updated_at": row["updated_at"] or "",
            }
            for row in meta_rows
        ],
    }
