"""
core/session.py
Manejo de historial de conversaciones por sesión y hora de Bolivia.
Compartido por todos los chatbots.
"""

import os
import uuid
from datetime import datetime, timezone, timedelta
from flask import session

# ─────────────────────────────────────────────
#  CONFIGURACIÓN
# ─────────────────────────────────────────────
MAX_HISTORIAL = int(os.environ.get("MAX_HISTORIAL", "6"))

# ─────────────────────────────────────────────
#  ALMACÉN EN MEMORIA
# ─────────────────────────────────────────────
# { session_id: [ {"role": "user/assistant", "content": "..."}, ... ] }
historiales: dict = {}


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
    return session["session_id"]


def get_historial(sid: str) -> list:
    """
    Devuelve el historial de conversación de una sesión.
    Si no existe, lo crea vacío.
    """
    if sid not in historiales:
        historiales[sid] = []
    return historiales[sid]


def agregar_turno(sid: str, pregunta: str, respuesta: str) -> None:
    """
    Agrega un par (pregunta, respuesta) al historial.
    Limita automáticamente a MAX_HISTORIAL * 2 mensajes.
    """
    hist = get_historial(sid)
    hist.extend([
        {"role": "user",      "content": pregunta},
        {"role": "assistant", "content": respuesta},
    ])
    max_msgs = MAX_HISTORIAL * 2
    if len(hist) > max_msgs:
        historiales[sid] = hist[-max_msgs:]


def limpiar_historial(sid: str) -> None:
    """Elimina el historial de una sesión (usado en /api/reset)."""
    historiales.pop(sid, None)


def historial_reciente(sid: str) -> list:
    """
    Devuelve los últimos MAX_HISTORIAL mensajes del historial.
    Listo para incluir en el prompt de Ollama.
    """
    hist = get_historial(sid)
    return hist[-MAX_HISTORIAL:]


def total_sesiones() -> int:
    """Devuelve la cantidad de sesiones activas en memoria."""
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
