"""
core/session.py
Manejo de historial de conversaciones por sesión y hora de Bolivia.
Compartido por todos los chatbots.
"""

import os
import threading
import time
import uuid
from datetime import datetime, timezone, timedelta
from flask import session

# ─────────────────────────────────────────────
#  CONFIGURACIÓN
# ─────────────────────────────────────────────
MAX_HISTORIAL = int(os.environ.get("MAX_HISTORIAL", "6"))
SESSION_TTL_MINUTES = int(os.environ.get("SESSION_TTL_MINUTES", "180"))
MAX_SESIONES_MEMORIA = int(os.environ.get("MAX_SESIONES_MEMORIA", "2000"))

# ─────────────────────────────────────────────
#  ALMACÉN EN MEMORIA
# ─────────────────────────────────────────────
# { session_id: [ {"role": "user/assistant", "content": "..."}, ... ] }
historiales: dict = {}
_ultimo_acceso: dict = {}
_pendiente_tarifa: dict = {}
_lock = threading.Lock()


def _ahora_ts() -> float:
    return time.time()


def _eliminar_sid(sid: str) -> None:
    historiales.pop(sid, None)
    _ultimo_acceso.pop(sid, None)
    _pendiente_tarifa.pop(sid, None)


def _purgar_sesiones_expiradas() -> None:
    if SESSION_TTL_MINUTES <= 0:
        return
    ttl_segundos = SESSION_TTL_MINUTES * 60
    limite = _ahora_ts() - ttl_segundos
    expiradas = [sid for sid, ts in _ultimo_acceso.items() if ts < limite]
    for sid in expiradas:
        _eliminar_sid(sid)


def _enforce_max_sesiones() -> None:
    if MAX_SESIONES_MEMORIA <= 0:
        return
    exceso = len(historiales) - MAX_SESIONES_MEMORIA
    if exceso <= 0:
        return
    # Evita crecimiento no acotado: elimina primero las sesiones más antiguas.
    antiguos = sorted(_ultimo_acceso.items(), key=lambda item: item[1])[:exceso]
    for sid, _ in antiguos:
        _eliminar_sid(sid)


# ─────────────────────────────────────────────
#  SESIÓN
# ─────────────────────────────────────────────

def get_sid() -> str:
    """
    Obtiene o crea el session_id del usuario actual.
    Requiere contexto de Flask activo.
    """
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())
    sid = session["session_id"]
    with _lock:
        _purgar_sesiones_expiradas()
        _ultimo_acceso[sid] = _ahora_ts()
        historiales.setdefault(sid, [])
        _enforce_max_sesiones()
    return sid


def get_historial(sid: str) -> list:
    """
    Devuelve el historial de conversación de una sesión.
    Si no existe, lo crea vacío.
    """
    with _lock:
        _purgar_sesiones_expiradas()
        if sid not in historiales:
            historiales[sid] = []
        _ultimo_acceso[sid] = _ahora_ts()
        _enforce_max_sesiones()
        return historiales[sid]


def agregar_turno(sid: str, pregunta: str, respuesta: str) -> None:
    """
    Agrega un par (pregunta, respuesta) al historial.
    Limita automáticamente a MAX_HISTORIAL * 2 mensajes.
    """
    with _lock:
        _purgar_sesiones_expiradas()
        hist = historiales.setdefault(sid, [])
        hist.extend([
            {"role": "user", "content": pregunta},
            {"role": "assistant", "content": respuesta},
        ])
        max_msgs = MAX_HISTORIAL * 2
        if len(hist) > max_msgs:
            historiales[sid] = hist[-max_msgs:]
        _ultimo_acceso[sid] = _ahora_ts()
        _enforce_max_sesiones()


def limpiar_historial(sid: str) -> None:
    """Elimina el historial de una sesión (usado en /api/reset)."""
    with _lock:
        _eliminar_sid(sid)


def set_pendiente_tarifa(sid: str, data: dict) -> None:
    """Guarda estado temporal para completar consultas de tarifa en varios turnos."""
    with _lock:
        _purgar_sesiones_expiradas()
        _pendiente_tarifa[sid] = data or {}
        _ultimo_acceso[sid] = _ahora_ts()
        _enforce_max_sesiones()


def get_pendiente_tarifa(sid: str) -> dict | None:
    """Obtiene el estado temporal de tarifa de la sesión."""
    with _lock:
        _purgar_sesiones_expiradas()
        _ultimo_acceso[sid] = _ahora_ts()
        _enforce_max_sesiones()
        data = _pendiente_tarifa.get(sid)
        if not isinstance(data, dict):
            return None
        return dict(data)


def clear_pendiente_tarifa(sid: str) -> None:
    """Limpia el estado temporal de tarifa de la sesión."""
    with _lock:
        _pendiente_tarifa.pop(sid, None)
        _ultimo_acceso[sid] = _ahora_ts()
        _enforce_max_sesiones()


def historial_reciente(sid: str) -> list:
    """
    Devuelve los últimos MAX_HISTORIAL mensajes del historial.
    Listo para incluir en el prompt de Ollama.
    """
    with _lock:
        _purgar_sesiones_expiradas()
        hist = historiales.setdefault(sid, [])
        _ultimo_acceso[sid] = _ahora_ts()
        _enforce_max_sesiones()
        return hist[-MAX_HISTORIAL:]


def total_sesiones() -> int:
    """Devuelve la cantidad de sesiones activas en memoria."""
    with _lock:
        _purgar_sesiones_expiradas()
        return len(historiales)


# ─────────────────────────────────────────────
#  HORA BOLIVIA
# ─────────────────────────────────────────────

DIAS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def get_hora_bolivia() -> dict:
    """
    Devuelve la hora actual en Bolivia (UTC-4) con estado de apertura
    de las oficinas de Correos.

    Returns:
        dict con:
            fecha   : "07/03/2026"
            hora    : "14:30"
            dia     : "viernes"
            abierto : True/False
            horario : descripción del horario
            estado  : "ABIERTO  " o "CERRADO  "
    """
    bolivia    = timezone(timedelta(hours=-4))
    ahora      = datetime.now(bolivia)
    hora_float = ahora.hour + ahora.minute / 60

    if ahora.weekday() < 5:           # Lunes a Viernes
        abierto = 8.5 <= hora_float < 18.5
        horario = "lunes a viernes de 8:30 a 18:30"
    elif ahora.weekday() == 5:        # Sábado
        abierto = 9.0 <= hora_float < 13.0
        horario = "sábados de 9:00 a 13:00"
    else:                             # Domingo
        abierto = False
        horario = "cerrado los domingos"

    return {
        "fecha"  : ahora.strftime("%d/%m/%Y"),
        "hora"   : ahora.strftime("%H:%M"),
        "dia"    : DIAS_ES[ahora.weekday()],
        "abierto": abierto,
        "horario": horario,
        "estado" : "ABIERTO  " if abierto else "CERRADO  ",
    }
