"""
core/location.py
Carga de sucursales desde JSON generado por el scraper,
geocodificación con Nominatim y generación de URLs de Google Maps.
Compartido por todos los chatbots.
"""

import os
import re
import json
import requests

# ─────────────────────────────────────────────
#  CONFIGURACIÓN
# ─────────────────────────────────────────────
SUCURSALES_FILE = os.environ.get("SUCURSALES_FILE", "data/sucursales_contacto.json")

# Cache en memoria para no repetir llamadas a Nominatim
_coords_cache: dict = {}


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────

def limpiar_campo(valor: str) -> str:
    """
    Elimina prefijos redundantes de los campos del scraper.
    Ejemplo: "Dirección: Av. Camacho 1372" → "Av. Camacho 1372"
    """
    if not valor:
        return ""
    return re.sub(
        r"^(direcci[oó]n|contacto|tel[eé]fono|email|horario)\s*:\s*",
        "", valor, flags=re.I,
    ).strip()


def generar_maps_url(lat: float, lng: float) -> str:
    """Genera URL de Google Maps para unas coordenadas."""
    return f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"


# ─────────────────────────────────────────────
#  GEOCODIFICACIÓN CON NOMINATIM
# ─────────────────────────────────────────────

def _nominatim_fallback(direccion: str, ciudad: str) -> dict | None:
    """
    Obtiene coordenadas desde Nominatim (OpenStreetMap).
    Valida que estén dentro de Bolivia (-23 < lat < -9, -70 < lng < -57).
    Usa cache en memoria para no repetir llamadas.
    """
    for query in [f"{direccion}, {ciudad}, Bolivia", f"{ciudad}, Bolivia"]:
        if query in _coords_cache:
            return _coords_cache[query]
        try:
            resp = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params  = {"q": query, "format": "json", "limit": 1},
                headers = {"User-Agent": "CorreosBoliviaBot/1.0 agbc@correos.gob.bo"},
                timeout = 8,
            )
            data = resp.json()
            if data:
                coords = {
                    "lat": float(data[0]["lat"]),
                    "lng": float(data[0]["lon"]),
                }
                # Validar que esté dentro de Bolivia
                if -23 < coords["lat"] < -9 and -70 < coords["lng"] < -57:
                    _coords_cache[query] = coords
                    return coords
        except Exception:
            pass
    return None


# ─────────────────────────────────────────────
#  CARGA DE SUCURSALES
# ─────────────────────────────────────────────

def cargar_sucursales(filepath: str = None) -> list:
    """
    Carga el archivo JSON de sucursales generado por el scraper,
    limpia los campos y geocodifica las que no tienen coordenadas.

    Args:
        filepath : ruta al JSON (por defecto SUCURSALES_FILE del .env)

    Returns:
        Lista de dicts con los datos de cada sucursal.
    """
    ruta = filepath or SUCURSALES_FILE

    if not os.path.exists(ruta):
        print(f"   No se encontró {ruta}")
        print("   Ejecuta primero: python scraper/runner.py")
        return []

    with open(ruta, "r", encoding="utf-8") as f:
        sucursales = json.load(f)

    # Limpiar campos que vienen con prefijos del scraper
    for s in sucursales:
        s["direccion"] = limpiar_campo(s.get("direccion", ""))
        s["telefono"]  = limpiar_campo(s.get("telefono",  ""))
        s["email"]     = limpiar_campo(s.get("email",     ""))
        s["horario"]   = limpiar_campo(s.get("horario",   ""))

    # Geocodificar las que no tienen coordenadas
    sin_coords = [s for s in sucursales if not s.get("lat") or not s.get("lng")]
    if sin_coords:
        print(f" {len(sin_coords)} sucursales sin coordenadas → usando Nominatim...")
        for s in sin_coords:
            ciudad = re.sub(
                r"^(regional|oficina\s+central)\s*:\s*",
                "", s.get("nombre", "").lower(),
            ).strip()
            coords = _nominatim_fallback(s.get("direccion", ""), ciudad)
            if coords:
                s["lat"] = coords["lat"]
                s["lng"] = coords["lng"]
                print(f"     {ciudad}: {coords}")
            else:
                print(f"      Sin coords: {ciudad}")

    con_coords = sum(1 for s in sucursales if s.get("lat") and s.get("lng"))
    print(f" {len(sucursales)} sucursales cargadas | {con_coords} con coordenadas")
    return sucursales


# ─────────────────────────────────────────────
#  CONVERSIÓN
# ─────────────────────────────────────────────

def sucursal_a_texto(s: dict) -> str:
    """
    Convierte una sucursal a texto plano para indexar en ChromaDB.
    """
    partes = [f"Sucursal: {s.get('nombre', '')}"]
    if s.get("direccion"): partes.append(f"Dirección: {s['direccion']}")
    if s.get("telefono"):  partes.append(f"Teléfono: {s['telefono']}")
    if s.get("email"):     partes.append(f"Email: {s['email']}")
    if s.get("horario"):   partes.append(f"Horario: {s['horario']}")
    return "\n".join(partes)


def sucursal_a_dict(s: dict) -> dict:
    """
    Prepara una sucursal para devolver como JSON en la API.
    Incluye la URL de Google Maps.
    """
    lat = s.get("lat")
    lng = s.get("lng")
    return {
        "nombre"   : s.get("nombre",    ""),
        "direccion": s.get("direccion", ""),
        "telefono" : s.get("telefono",  ""),
        "email"    : s.get("email",     ""),
        "horario"  : s.get("horario",   ""),
        "lat"      : lat,
        "lng"      : lng,
        "maps_url" : generar_maps_url(lat, lng) if lat and lng else None,
    }


def cargar_secciones(filepath: str = "data/secciones_home.json") -> tuple[list, list]:
    """
    Carga las secciones del home generadas por el scraper
    y las convierte en chunks para indexar en ChromaDB.

    Returns:
        (chunks, chunk_ids)
    """
    chunks = []
    ids    = []

    if not os.path.exists(filepath):
        print(f"   No se encontró {filepath}")
        return [], []

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            secciones = json.load(f)

        for nombre_sec, items in secciones.items():
            if items:
                texto = f"## {nombre_sec}\n\n" + "\n".join(f"- {it}" for it in items)
                chunks.append(texto)
                ids.append(f"sec_{nombre_sec.replace(' ', '_')}")
        print(f"📋 {len(chunks)} secciones cargadas de '{filepath}'")
    except Exception as e:
        print(f"   Error cargando secciones: {e}")

    return chunks, ids
