"""
core/auth.py
Autenticacion y autorizacion para el panel de capacidades.
Usa JWT + bcrypt + SQLite para persistencia.
"""

from __future__ import annotations

import os
import json
import sqlite3
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import APIRouter, Request, HTTPException, Depends

# ─── CONFIG ────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
AUTH_DB_PATH = os.environ.get("AUTH_DB_PATH", os.path.join(BASE_DIR, "data", "auth.db"))
JWT_SECRET = os.environ.get("JWT_SECRET", "chatbotbo-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = int(os.environ.get("JWT_EXPIRY_HOURS", "24"))


def _hash_password(password: str) -> str:
    return hashlib.sha256(f"{JWT_SECRET}:{password}".encode()).hexdigest()


def _verify_password(password: str, hash_value: str) -> bool:
    return _hash_password(password) == hash_value


# ─── DB ────────────────────────────────────────────────────────────────
def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(AUTH_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Crea la tabla de usuarios si no existe."""
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            nombre TEXT NOT NULL DEFAULT '',
            rol TEXT NOT NULL DEFAULT 'operador' CHECK(rol IN ('admin', 'operador')),
            activo INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    # Crear admin por defecto si no existe
    existing = conn.execute("SELECT username FROM usuarios WHERE username = ?", ("admin",)).fetchone()
    if not existing:
        admin_hash = _hash_password("admin123")
        conn.execute(
            "INSERT INTO usuarios (username, password_hash, nombre, rol, activo) VALUES (?, ?, ?, ?, 1)",
            ("admin", admin_hash, "Administrador", "admin")
        )
    conn.commit()
    conn.close()


# ─── USUARIOS CRUD ─────────────────────────────────────────────────────
def listar_usuarios() -> list[dict]:
    conn = _get_db()
    rows = conn.execute("SELECT username, nombre, rol, activo, created_at FROM usuarios ORDER BY username").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def obtener_usuario(username: str) -> dict | None:
    conn = _get_db()
    row = conn.execute(
        "SELECT username, nombre, rol, activo, created_at FROM usuarios WHERE username = ?",
        (username,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def crear_usuario(username: str, password: str, nombre: str, rol: str) -> dict:
    conn = _get_db()
    existing = conn.execute("SELECT username FROM usuarios WHERE username = ?", (username,)).fetchone()
    if existing:
        conn.close()
        raise ValueError("El usuario ya existe")
    pwd_hash = _hash_password(password)
    conn.execute(
        "INSERT INTO usuarios (username, password_hash, nombre, rol, activo) VALUES (?, ?, ?, ?, 1)",
        (username, pwd_hash, nombre, rol)
    )
    conn.commit()
    conn.close()
    return {"username": username, "nombre": nombre, "rol": rol, "activo": True}


def actualizar_usuario(username: str, data: dict) -> dict | None:
    conn = _get_db()
    campos = []
    params = []
    if "password" in data and data["password"]:
        campos.append("password_hash = ?")
        params.append(_hash_password(data["password"]))
    if "nombre" in data:
        campos.append("nombre = ?")
        params.append(data["nombre"])
    if "rol" in data:
        campos.append("rol = ?")
        params.append(data["rol"])
    if "activo" in data:
        campos.append("activo = ?")
        params.append(1 if data["activo"] else 0)
    if not campos:
        conn.close()
        return obtener_usuario(username)
    campos.append("updated_at = datetime('now')")
    params.append(username)
    conn.execute(f"UPDATE usuarios SET {', '.join(campos)} WHERE username = ?", params)
    conn.commit()
    conn.close()
    return obtener_usuario(username)


def eliminar_usuario(username: str) -> bool:
    if username == "admin":
        return False
    conn = _get_db()
    conn.execute("DELETE FROM usuarios WHERE username = ?", (username,))
    deleted = conn.total_changes > 0
    conn.commit()
    conn.close()
    return deleted


# ─── AUTH ──────────────────────────────────────────────────────────────
def autenticar(username: str, password: str) -> dict | None:
    conn = _get_db()
    row = conn.execute(
        "SELECT username, password_hash, nombre, rol, activo FROM usuarios WHERE username = ?",
        (username,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    user = dict(row)
    if not user["activo"]:
        return None
    if not _verify_password(password, user["password_hash"]):
        return None
    return {"username": user["username"], "nombre": user["nombre"], "rol": user["rol"]}


def crear_token(user: dict) -> str:
    payload = {
        "sub": user["username"],
        "nombre": user["nombre"],
        "rol": user["rol"],
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decodificar_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def usuario_actual(request: Request) -> dict | None:
    """Obtiene el usuario autenticado desde el header Authorization o cookie."""
    # Intentar header Authorization
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        payload = decodificar_token(token)
        if payload:
            return payload
    # Intentar cookie
    cookie = request.cookies.get("auth_token")
    if cookie:
        payload = decodificar_token(cookie)
        if payload:
            return payload
    return None


def requiere_auth(request: Request) -> dict:
    user = usuario_actual(request)
    if not user:
        raise HTTPException(status_code=401, detail="No autenticado")
    return user


def requiere_admin(user: dict = Depends(requiere_auth)) -> dict:
    if user.get("rol") != "admin":
        raise HTTPException(status_code=403, detail="Se requiere rol admin")
    return user


router = APIRouter()


@router.post("/auth/login")
async def login(request: Request):
    data = await request.json()
    username = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""
    if not username or not password:
        raise HTTPException(status_code=400, detail="Usuario y contraseña requeridos")
    user = autenticar(username, password)
    if not user:
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")
    token = crear_token(user)
    return {"token": token, "user": user}


@router.get("/auth/me")
async def me(request: Request):
    user = usuario_actual(request)
    if not user:
        raise HTTPException(status_code=401, detail="No autenticado")
    return {"user": user}


@router.post("/auth/logout")
async def logout():
    # El logout se maneja del lado del cliente eliminando el token
    return {"ok": True}


# ─── USUARIOS CRUD (solo admin) ───────────────────────────────────────
@router.get("/users")
async def get_users(_: dict = Depends(requiere_admin)):
    return {"users": listar_usuarios()}


@router.post("/users")
async def create_user(request: Request, _: dict = Depends(requiere_admin)):
    data = await request.json()
    username = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""
    nombre = (data.get("nombre") or "").strip()
    rol = (data.get("rol") or "operador").strip().lower()
    if rol not in ("admin", "operador"):
        raise HTTPException(status_code=400, detail="Rol inválido: debe ser admin u operador")
    if not username or len(username) < 3:
        raise HTTPException(status_code=400, detail="Usuario debe tener al menos 3 caracteres")
    if not password or len(password) < 4:
        raise HTTPException(status_code=400, detail="Contraseña debe tener al menos 4 caracteres")
    try:
        result = crear_usuario(username, password, nombre, rol)
        return result
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.put("/users/{username}")
async def update_user(username: str, request: Request, _: dict = Depends(requiere_admin)):
    data = await request.json()
    allowed = {}
    if "password" in data and data["password"]:
        if len(data["password"]) < 4:
            raise HTTPException(status_code=400, detail="Contraseña debe tener al menos 4 caracteres")
        allowed["password"] = data["password"]
    if "nombre" in data:
        allowed["nombre"] = data["nombre"].strip()
    if "rol" in data:
        r = data["rol"].strip().lower()
        if r not in ("admin", "operador"):
            raise HTTPException(status_code=400, detail="Rol inválido")
        allowed["rol"] = r
    if "activo" in data:
        allowed["activo"] = bool(data["activo"])
    result = actualizar_usuario(username, allowed)
    if not result:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return result


@router.delete("/users/{username}")
async def delete_user(username: str, _: dict = Depends(requiere_admin)):
    if username == "admin":
        raise HTTPException(status_code=400, detail="No se puede eliminar al usuario admin")
    ok = eliminar_usuario(username)
    if not ok:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return {"ok": True}


# ─── Inicializar DB al importar ────────────────────────────────────────
init_db()
