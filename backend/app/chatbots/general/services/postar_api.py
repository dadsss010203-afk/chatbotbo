"""
services/postar_api.py
Integracion con API POSTAR de Correos de Bolivia.
Carga opciones desde data/postar_options_grouped.json.
"""

from __future__ import annotations

import os
import json
import re
import requests
import logging

logger = logging.getLogger("chatbotbo.postar")

# ─── CONFIGURACION ──────────────────────────────────────────────────────
POSTAR_API_URL = os.environ.get("POSTAR_API_URL", "https://postar.correos.gob.bo:8104/api/calcular")
POSTAR_API_TIMEOUT = int(os.environ.get("POSTAR_API_TIMEOUT", "20"))
POSTAR_API_VERIFY_SSL = os.environ.get("POSTAR_API_VERIFY_SSL", "false").lower() in ("1", "true", "yes")
POSTAR_DEFAULT_CERTIFICADO = os.environ.get("POSTAR_DEFAULT_CERTIFICADO", "false").lower() in ("1", "true", "yes")
POSTAR_DEFAULT_ESPRESO = os.environ.get("POSTAR_DEFAULT_ESPRESO", "false").lower() in ("1", "true", "yes")
POSTAR_DEFAULT_RECIBO = os.environ.get("POSTAR_DEFAULT_RECIBO", "false").lower() in ("1", "true", "yes")

# ─── CARGA DE OPCIONES DESDE JSON ───────────────────────────────────────
_JSON_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "postar_options_grouped.json")

_data: dict = {}
_categorias_nac: list = []
_categorias_int: list = []
_destinos_nac: list = []
_destinos_int: list = []
_zonas_int: dict[str, list] = {}  # zona_a → [{value, label}, ...]

def _cargar_json():
    global _data, _categorias_nac, _categorias_int, _destinos_nac, _destinos_int, _zonas_int
    if _data:
        return
    try:
        with open(_JSON_PATH, "r", encoding="utf-8") as f:
            _data = json.load(f)
        
        _categorias_nac = _data["nacional"]["categories"]
        _categorias_int = _data["internacional"]["categories"]
        _destinos_nac = _data["nacional"]["destinations"]
        _destinos_int = _data["internacional"]["destinations"]
        
        # Agrupar destinos internacionales por zona
        for d in _destinos_int:
            val = d.get("value", "")
            # dest_a_xxx → zona a
            m = re.match(r"dest_([a-e])_", val)
            if m:
                zona = m.group(1)
                _zonas_int.setdefault(zona, []).append(d)
        
        logger.info("POSTAR options cargadas: %d cat nac, %d cat int, %d dest nac, %d dest int (%d zonas)",
                    len(_categorias_nac), len(_categorias_int), len(_destinos_nac), len(_destinos_int), len(_zonas_int))
    except Exception as e:
        logger.error("Error cargando postar_options_grouped.json: %s", e)


# ─── MAPEO: SERVICIO (category value) → DESTINOS PERMITIDOS ─────────────
# Los filtros se leen desde destinations_filter en cada categoria del JSON.
# Set vacio = todos los destinos internacionales aplican.
# None = sin filtro (todos los destinos del scope aplican).

def _get_service_destinations(categoria: str) -> set[str] | None:
    """
    Retorna el set de destination values permitidos para una categoria,
    o None si no hay filtro (todos los destinos aplican).
    Lee el filtro desde destinations_filter en postar_options_grouped.json.
    """
    _cargar_json()
    if not categoria:
        return None
    # Buscar en nacional
    for cat in _categorias_nac:
        if cat["value"] == categoria:
            filtro = cat.get("destinations_filter")
            if filtro is None:
                return None  # sin filtro
            return set(filtro) if isinstance(filtro, list) else set()
    # Buscar en internacional
    for cat in _categorias_int:
        if cat["value"] == categoria:
            filtro = cat.get("destinations_filter")
            if filtro is None:
                return set()  # internacional sin filtro = todos aplican
            return set(filtro) if isinstance(filtro, list) else set()
    return None


# ─── PESO ───────────────────────────────────────────────────────────────
def parse_peso(texto: str) -> float | None:
    texto = texto.lower().strip().replace(",", ".")
    m = re.search(r'(\d+\.?\d*)\s*g(?:r(?:amo)?s?)?\b', texto)
    if m:
        g = float(m.group(1))
        return round(g / 1000, 3) if g > 100 else g
    m = re.search(r'(\d+\.?\d*)\s*k(?:g|ilo)?s?\b', texto)
    if m:
        return float(m.group(1))
    m = re.search(r'(\d+\.?\d*)', texto)
    if m:
        val = float(m.group(1))
        if val > 100 and val < 50000:
            return round(val / 1000, 3)
        return val
    return None


# ─── LLAMADA A POSTAR API ───────────────────────────────────────────────
def calcular(categoria: str, destino: str, peso: float) -> dict:
    payload = {"categoria": categoria, "destino": destino, "peso": peso,
               "certificado": POSTAR_DEFAULT_CERTIFICADO, "espreso": POSTAR_DEFAULT_ESPRESO, "recibo": POSTAR_DEFAULT_RECIBO}
    logger.info("POSTAR | cat=%s dest=%s peso=%.3f", categoria, destino, peso)
    try:
        resp = requests.post(POSTAR_API_URL, json=payload, verify=POSTAR_API_VERIFY_SSL, timeout=POSTAR_API_TIMEOUT)
        data = resp.json() if resp.text else {}
        if resp.status_code == 200 and data.get("success"):
            return {"ok": True, "tarifa": data["tarifa"], "raw": data}
        msg = data.get("message", "")
        if "fuera de rango" in msg.lower() or "out of range" in msg.lower():
            return {"ok": False, "error": "peso_fuera_rango", "message": msg}
        return {"ok": False, "error": "api_error", "message": msg or f"HTTP {resp.status_code}"}
    except requests.exceptions.Timeout:
        return {"ok": False, "error": "timeout"}
    except Exception as e:
        return {"ok": False, "error": "exception", "message": str(e)}


# ─── QUICK REPLIES ──────────────────────────────────────────────────────
def quick_replies_scope():
    return [{"value": "Nacional", "label": "🇧🇴 Nacional"}, {"value": "Internacional", "label": "🌎 Internacional"}]


def quick_replies_services(scope: str):
    _cargar_json()
    cats = _categorias_nac if scope == "nacional" else _categorias_int
    return [{"value": c["label"], "label": c["label"]} for c in cats]


def quick_replies_destino_grupos(scope: str, service_value: str | None = None):
    """
    Retorna destinos filtrados por servicio si se especifica.
    service_value = valor de la categoria (ej: "EMS NAT", "MI ENCOMIENDA").
    Si no hay service_value, retorna todos los destinos del alcance.
    """
    _cargar_json()
    allowed = _get_service_destinations(service_value) if service_value else None
    
    if scope == "nacional":
        items = _destinos_nac
        if allowed is not None:
            items = [d for d in items if d["value"] in allowed]
        return [{"value": d["label"], "label": d["label"]} for d in items]
    
    if allowed is not None and not allowed:
        # Set vacio = todos los internacionales aplican
        return [{"value": n, "label": f"🌎 {n}"} for n in [_zona_nombre(z) for z in _zonas_int]]
    
    # Internacional: filtrar zonas segun destinos permitidos
    zonas_filtradas = set()
    if allowed is not None:
        for d in _destinos_int:
            if d["value"] in allowed:
                m = re.match(r"dest_([a-e])_", d["value"])
                if m:
                    zonas_filtradas.add(m.group(1))
    else:
        zonas_filtradas = set(_zonas_int.keys())
    
    return [{"value": n, "label": f"🌎 {n}"} for n in [_zona_nombre(z) for z in sorted(zonas_filtradas)]]


def quick_replies_destino_zona(zona_label: str, service_value: str | None = None):
    """Dado un label de zona, devuelve paises de esa zona, filtrados por servicio si aplica."""
    _cargar_json()
    m = re.search(r'\b([a-e])\b', zona_label, re.I)
    if not m:
        return []
    zona = m.group(1).lower()
    
    allowed = _get_service_destinations(service_value) if service_value else None
    
    items = _zonas_int.get(zona, [])
    if allowed is not None and allowed:
        items = [d for d in items if d["value"] in allowed]
    
    return [{"value": d["label"], "label": d["label"]} for d in items]


# ─── BUSQUEDA ───────────────────────────────────────────────────────────
def find_category_by_label(label: str, scope: str) -> str | None:
    """Encuentra el value de una categoria desde su label o texto parcial."""
    _cargar_json()
    cats = _categorias_nac if scope == "nacional" else _categorias_int
    label_lower = label.lower().strip()
    for c in cats:
        if label_lower in c["label"].lower() or c["label"].lower() in label_lower:
            return c["value"]
    # fallback: buscar palabras clave
    for c in cats:
        if any(w in label_lower for w in c["label"].lower().split()):
            return c["value"]
    return None


def find_destination_by_label(label: str, scope: str) -> str | None:
    """Encuentra el value de un destino desde su label."""
    _cargar_json()
    dests = _destinos_nac if scope == "nacional" else _destinos_int
    label_lower = label.lower().strip()
    for d in dests:
        if label_lower in d["label"].lower() or d["label"].lower() in label_lower:
            return d["value"]
    # Busqueda por mapeo de nombres comunes
    if scope == "nacional":
        mapping = {"beni": "nacional_beni", "chuquisaca": "nacional_chuquisaca",
                   "cochabamba": "nacional_cochabamba", "la paz": "nacional_la_paz",
                   "oruro": "nacional_oruro", "pando": "nacional_pando",
                   "potosi": "nacional_potosi", "santa cruz": "nacional_santa_cruz",
                   "tarija": "nacional_tarija"}
        for key, val in mapping.items():
            if key in label_lower:
                return val
    return None


def find_zona_by_label(label: str) -> str | None:
    m = re.search(r'\b([a-e])\b', label, re.I)
    return m.group(1).lower() if m else None


def get_category_label(value: str) -> str | None:
    """Obtiene el label de una categoria dado su value."""
    _cargar_json()
    for c in _categorias_nac + _categorias_int:
        if c["value"] == value:
            return c["label"]
    return None


def get_destination_label(value: str) -> str | None:
    """Obtiene el label de un destino dado su value."""
    _cargar_json()
    for d in _destinos_nac + _destinos_int:
        if d["value"] == value:
            return d["label"]
    return None


# ─── FLUJO ──────────────────────────────────────────────────────────────
def estado_requiere(flow: dict) -> str | None:
    if not flow.get("scope"): return "scope"
    if not flow.get("service"): return "service"
    if not flow.get("destination"): return "destination"
    if flow.get("weight") is None: return "weight"
    return None


def _zona_nombre(z: str) -> str:
    names = {"a": "America del Sur (zona A)", "b": "America Central y Caribe (zona B)",
             "c": "America del Norte (zona C)", "d": "Europa y Medio Oriente (zona D)",
             "e": "Africa, Asia y Oceania (zona E)"}
    return names.get(z, z.upper())
