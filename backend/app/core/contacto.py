"""
core/contacto.py
Datos institucionales de contacto centralizados.
Lee data/contacto_institucional.json — si el teléfono, horario o URL cambia,
solo hay que editar ese archivo. Ningún otro módulo debe hardcodear estos datos.
"""

import json
import os
import logging

logger = logging.getLogger("chatbotbo.contacto")

_BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_CONTACTO_FILE = os.environ.get(
    "CONTACTO_FILE",
    os.path.join(_BASE_DIR, "data", "contacto_institucional.json"),
)

# Valores por defecto — solo se usan si el archivo no existe
_DEFAULTS = {
    "nombre": "Correos de Bolivia",
    "nombre_anterior": "AGBC - Agencia Boliviana de Correos",
    "telefono": "+591 22152423",
    "telefono_corto": "22152423",
    "email": "agbc@correos.gob.bo",
    "web": "correos.gob.bo",
    "web_url": "https://correos.gob.bo",
    "tracking_url": "https://trackingbo.correos.gob.bo:8100",
    "tracking_api_url": "https://trackingbo.correos.gob.bo:8100/api/public/tracking/eventos",
    "horario_semana": "Lunes a viernes 8:30 a 16:30",
    "horario_sabado": "Sábados 9:00 a 13:00",
    "horario_domingo": "Domingos cerrado",
    "horario_apertura_semana": "8:30",
    "horario_cierre_semana": "16:30",
    "horario_apertura_sabado": "9:00",
    "horario_cierre_sabado": "13:00",
    "decreto_creacion": "3495",
    "anio_creacion": "2018",
    "anio_nombre_actual": "2026",
}

_cache: dict | None = None


def _cargar() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    if os.path.exists(_CONTACTO_FILE):
        try:
            with open(_CONTACTO_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                # Mezclar con defaults para que campos nuevos siempre existan
                merged = dict(_DEFAULTS)
                merged.update(data)
                _cache = merged
                logger.info("Contacto institucional cargado", extra={"file": _CONTACTO_FILE})
                return _cache
        except Exception as exc:
            logger.warning("Error leyendo contacto_institucional.json, usando defaults", extra={"error": str(exc)})
    _cache = dict(_DEFAULTS)
    return _cache


def reload() -> dict:
    """Fuerza recarga del archivo (útil tras edición en caliente)."""
    global _cache
    _cache = None
    return _cargar()


def get(campo: str, default: str = "") -> str:
    """Devuelve un campo del contacto institucional."""
    return str(_cargar().get(campo, default) or default)


def todos() -> dict:
    """Devuelve todos los datos institucionales."""
    return dict(_cargar())


# ── Accesores directos (los más usados) ─────────────────────────────────────

def telefono() -> str:
    return get("telefono")

def telefono_corto() -> str:
    return get("telefono_corto")

def web() -> str:
    return get("web")

def web_url() -> str:
    return get("web_url")

def email() -> str:
    return get("email")

def nombre() -> str:
    return get("nombre")

def tracking_url() -> str:
    return get("tracking_url")

def tracking_api_url() -> str:
    return get("tracking_api_url")

def horario_semana() -> str:
    return get("horario_semana")

def horario_sabado() -> str:
    return get("horario_sabado")

def horario_resumen() -> str:
    """Horario completo en una línea."""
    return f"{horario_semana()} | {horario_sabado()}"

def datos_conocidos_numericos() -> set:
    """
    Devuelve el conjunto de datos numéricos institucionales conocidos.
    Usado por intents.datos_inventados() para no marcar estos valores como inventados.
    """
    d = _cargar()
    return {
        d.get("telefono_corto", "22152423"),
        d.get("telefono", "+591 22152423"),
        "+591",
        d.get("decreto_creacion", "3495"),
        d.get("anio_creacion", "2018"),
        d.get("anio_nombre_actual", "2026"),
        # Horarios
        d.get("horario_apertura_semana", "8:30"),
        d.get("horario_cierre_semana", "16:30"),
        d.get("horario_apertura_sabado", "9:00"),
        d.get("horario_cierre_sabado", "13:00"),
        # Años históricos siempre válidos
        "1825", "1886", "1990",
        "2019", "2020", "2021", "2022", "2023", "2024", "2025",
        # Datos operativos de servicios postales
        "20", "192", "40", "24", "48", "72",
    }
