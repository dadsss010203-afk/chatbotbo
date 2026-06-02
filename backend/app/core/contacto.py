"""
core/contacto.py
Datos institucionales centralizados.
Lee data/institucion.json — fuente unica de verdad.
Si no existe, usa defaults minimos.
"""

import json
import os
import logging

logger = logging.getLogger("chatbotbo.contacto")

_BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_INSTITUCION_FILE = os.environ.get(
    "INSTITUCION_FILE",
    os.path.join(_BASE_DIR, "data", "institucion.json"),
)

_DEFAULTS = {
    "nombre": "Correos de Bolivia",
    "telefono": "+591 22152423",
    "telefono_corto": "22152423",
    "email": "agbc@correos.gob.bo",
    "web": "correos.gob.bo",
    "web_url": "https://correos.gob.bo",
    "tracking_url": "https://trackingbo.correos.gob.bo:8100",
    "tracking_api_url": "https://trackingbo.correos.gob.bo:8100/api/public/tracking/eventos",
    "tracking_ejemplo_codigo": "C0028A03441BO",
    "horario_semana": "Lunes a viernes 8:30 a 16:30",
    "horario_sabado": "Sabados 9:00 a 13:00",
    "horario_domingo": "Domingos cerrado",
    "decreto_creacion": "3495",
    "anio_creacion": "2018",
    "anio_nombre_actual": "2026",
}

_cache: dict | None = None


def _cargar() -> dict:
    global _cache
    if _cache is not None:
        return _cache

    data = dict(_DEFAULTS)

    if os.path.exists(_INSTITUCION_FILE):
        try:
            with open(_INSTITUCION_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)

            c = raw.get("contacto", {})
            if c:
                data["telefono"] = c.get("telefono", data["telefono"])
                data["telefono_corto"] = c.get("telefono_corto", data["telefono_corto"])
                data["email"] = c.get("email", data["email"])
                data["web"] = c.get("web", data["web"])
                data["web_url"] = c.get("web_url", data["web_url"])

            i = raw.get("institucion", {})
            if i:
                data["nombre"] = i.get("nombre", data["nombre"])
                data["decreto_creacion"] = str(i.get("decreto_creacion", data["decreto_creacion"]))
                data["anio_creacion"] = str(i.get("anio_creacion", data["anio_creacion"]))
                data["anio_nombre_actual"] = str(i.get("anio_nombre_actual", data["anio_nombre_actual"]))

            h = raw.get("horario", {})
            if h:
                data["horario_semana"] = h.get("semana", data["horario_semana"])
                data["horario_sabado"] = h.get("sabado", data["horario_sabado"])
                data["horario_domingo"] = h.get("domingo", data["horario_domingo"])

            t = raw.get("tracking", {})
            if t:
                data["tracking_url"] = t.get("url", data["tracking_url"])
                data["tracking_api_url"] = t.get("api_url", data["tracking_api_url"])
                data["tracking_ejemplo_codigo"] = t.get("ejemplo_codigo", data["tracking_ejemplo_codigo"])

            logger.info("Institucion cargada desde %s", _INSTITUCION_FILE)
        except Exception as exc:
            logger.warning("Error leyendo institucion.json: %s", exc)

    _cache = data
    return _cache


def reload() -> dict:
    global _cache
    _cache = None
    return _cargar()


def get(campo: str, default: str = "") -> str:
    return str(_cargar().get(campo, default) or default)


def todos() -> dict:
    return dict(_cargar())


# ── Accesores directos ──────────────────────
def telefono() -> str: return get("telefono")
def telefono_corto() -> str: return get("telefono_corto")
def web() -> str: return get("web")
def web_url() -> str: return get("web_url")
def email() -> str: return get("email")
def nombre() -> str: return get("nombre")
def tracking_url() -> str: return get("tracking_url")
def tracking_api_url() -> str: return get("tracking_api_url")
def tracking_ejemplo_codigo() -> str: return get("tracking_ejemplo_codigo")
def horario_semana() -> str: return get("horario_semana")
def horario_sabado() -> str: return get("horario_sabado")
def horario_domingo() -> str: return get("horario_domingo")
def horario_resumen() -> str: return f"{horario_semana()} | {horario_sabado()} | {horario_domingo()}"
def decreto_creacion() -> str: return get("decreto_creacion")
def anio_creacion() -> str: return get("anio_creacion")

def datos_conocidos_numericos() -> set:
    d = _cargar()
    return {
        d.get("telefono_corto", ""), d.get("telefono", ""), "+591",
        d.get("decreto_creacion", ""), d.get("anio_creacion", ""),
        d.get("anio_nombre_actual", ""),
        "8:30", "16:30", "9:00", "13:00",
        "1825", "1886", "1990",
        "2019", "2020", "2021", "2022", "2023", "2024", "2025",
        "20", "192", "40", "24", "48", "72",
    }
