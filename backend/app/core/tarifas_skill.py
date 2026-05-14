"""
core/tarifas_skill.py
Router robusto para skills de tarifas:
- skill1: EMS Nacional (Hoja 1)
- skill2: EMS Internacional (Hoja 2)
- skill3: Mi Encomienda Prioritario Nacional (Hoja 3)
- skill4: Encomiendas Postales Internacional (Hoja 4)
"""

from __future__ import annotations

import difflib
import json
import os
import re
import unicodedata
import requests
from dataclasses import dataclass
from core.cache import get_tariff, set_tariff


BASE_APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Compatibilidad:
# - Nuevo: TARIFF_SKILLS_ROOT=/app/skills
# - Antiguo: TARIFF_SKILL_ROOT=/app/skills/skill1
_LEGACY_SKILL_ROOT = os.environ.get("TARIFF_SKILL_ROOT", "").strip()
_DEFAULT_SKILLS_ROOT = os.path.abspath(os.path.join(BASE_APP_DIR, "skills"))
SKILLS_ROOT = os.environ.get("TARIFF_SKILLS_ROOT") or (os.path.dirname(_LEGACY_SKILL_ROOT) if _LEGACY_SKILL_ROOT else _DEFAULT_SKILLS_ROOT)

SKILL_CONFIG = {
    "nacional": {
        "skill_id": "tarifa_ems_nacional",
        "wrapper": os.path.join(SKILLS_ROOT, "skill1", "tools", "calcular_hoja1_json.sh"),
        "columns": {"C", "D", "E", "F", "G", "H", "I", "J"},
        "label": "Express Mail Service (EMS) Nacional",
    },
    "internacional": {
        "skill_id": "tarifa_ems_internacional",
        "wrapper": os.path.join(SKILLS_ROOT, "skill2", "tools", "calcular_hoja2_json.sh"),
        "columns": {"C", "D", "E", "F", "G"},
        "label": "Express Mail Service (EMS) Internacional",
    },
    "encomienda_nacional": {
        "skill_id": "tarifa_encomienda_prioritario_nacional",
        "wrapper": os.path.join(SKILLS_ROOT, "skill3", "tools", "calcular_hoja3_json.sh"),
        "columns": {"C", "D", "E", "F"},
        "label": "Mi Encomienda Prioritario Nacional",
    },
    "encomienda_internacional": {
        "skill_id": "tarifa_encomiendas_postales_internacional",
        "wrapper": os.path.join(SKILLS_ROOT, "skill4", "tools", "calcular_hoja4_json.sh"),
        "columns": {"C", "D", "E", "F", "G"},
        "label": "Encomiendas Postales Internacional",
    },
    "ems_hoja5_nacional": {
        "skill_id": "tarifa_ems_hoja5_nacional",
        "wrapper": os.path.join(SKILLS_ROOT, "skill5", "tools", "calcular_hoja5_json.sh"),
        "columns": {"C", "D", "E", "F", "G", "H"},
        "label": "Correo Prioritario LC/AO Nacional",
    },
    "ems_hoja6_internacional": {
        "skill_id": "tarifa_ems_hoja6_internacional",
        "wrapper": os.path.join(SKILLS_ROOT, "skill6", "tools", "calcular_hoja6_json.sh"),
        "columns": {"C", "D", "E", "F", "G"},
        "label": "Correo Prioritario LC/AO Internacional",
    },
    "eca_nacional": {
        "skill_id": "tarifa_eca_nacional",
        "wrapper": os.path.join(SKILLS_ROOT, "skill7", "tools", "calcular_hoja7_json.sh"),
        "columns": {"C", "D", "E", "F", "G", "H"},
        "label": "Correspondencia Agrupada (ECA) Nacional",
    },
    "eca_internacional": {
        "skill_id": "tarifa_eca_internacional",
        "wrapper": os.path.join(SKILLS_ROOT, "skill8", "tools", "calcular_hoja8_json.sh"),
        "columns": {"C", "D", "E", "F", "G"},
        "label": "Correspondencia Agrupada (ECA) Internacional",
    },
    "pliegos_nacional": {
        "skill_id": "tarifa_pliegos_nacional",
        "wrapper": os.path.join(SKILLS_ROOT, "skill9", "tools", "calcular_hoja9_json.sh"),
        "columns": {"C", "D", "E", "F"},
        "label": "Pliegos Oficiales Nacional",
    },
    "pliegos_internacional": {
        "skill_id": "tarifa_pliegos_internacional",
        "wrapper": os.path.join(SKILLS_ROOT, "skill10", "tools", "calcular_hoja10_json.sh"),
        "columns": {"C", "D", "E", "F", "G"},
        "label": "Pliegos Oficiales Internacional",
    },
    "sacas_m_nacional": {
        "skill_id": "tarifa_sacas_m_nacional",
        "wrapper": os.path.join(SKILLS_ROOT, "skill11", "tools", "calcular_hoja11_json.sh"),
        "columns": {"C", "D"},
        "label": "Sacas M Nacional",
    },
    "sacas_m_internacional": {
        "skill_id": "tarifa_sacas_m_internacional",
        "wrapper": os.path.join(SKILLS_ROOT, "skill12", "tools", "calcular_hoja12_json.sh"),
        "columns": {"C", "D", "E", "F", "G"},
        "label": "Sacas M Internacional",
    },
    "ems_contratos_nacional": {
        "skill_id": "tarifa_ems_contratos_nacional",
        "wrapper": os.path.join(SKILLS_ROOT, "skill13", "tools", "calcular_hoja13_json.sh"),
        "columns": {"C", "D", "E"},
        "label": "EMS Contratos Nacional",
    },
    "super_express_nacional": {
        "skill_id": "tarifa_super_express_nacional",
        "wrapper": os.path.join(SKILLS_ROOT, "skill14", "tools", "calcular_hoja14_json.sh"),
        "columns": {"C"},
        "label": "Super Express Nacional",
    },
    "super_express_documentos_internacional": {
        "skill_id": "tarifa_super_express_documentos_internacional",
        "wrapper": os.path.join(SKILLS_ROOT, "skill15", "tools", "calcular_hoja15_json.sh"),
        "columns": {"B", "C", "D", "E", "F", "G", "H"},
        "label": "Super Express Documentos Internacional",
    },
    "super_express_paquetes_internacional": {
        "skill_id": "tarifa_super_express_paquetes_internacional",
        "wrapper": os.path.join(SKILLS_ROOT, "skill16", "tools", "calcular_hoja16_json.sh"),
        "columns": {"B", "C", "D", "E", "F", "G", "H"},
        "label": "Super Express Paquetes Internacional",
    },
}

POSTAR_API_URL = os.environ.get("POSTAR_API_URL", "https://postar.correos.gob.bo:8104/api/calcular").strip()
POSTAR_API_TIMEOUT = int(os.environ.get("POSTAR_API_TIMEOUT", "20"))
POSTAR_API_VERIFY_SSL = os.environ.get("POSTAR_API_VERIFY_SSL", "false").strip().lower() in ("1", "true", "yes")
POSTAR_DEFAULT_CERTIFICADO = os.environ.get("POSTAR_DEFAULT_CERTIFICADO", "false").strip().lower() in ("1", "true", "yes")
POSTAR_DEFAULT_ESPRESO = os.environ.get("POSTAR_DEFAULT_ESPRESO", "false").strip().lower() in ("1", "true", "yes")
POSTAR_DEFAULT_RECIBO = os.environ.get("POSTAR_DEFAULT_RECIBO", "false").strip().lower() in ("1", "true", "yes")
POSTAR_OPTIONS_FILE = os.path.join(BASE_APP_DIR, "data", "postar_options_grouped.json")
POSTAR_DEST_TOKEN_PREFIX = "DEST::"
POSTAR_DEST_GROUP_TOKEN_PREFIX = "DEST_GROUP::"
POSTAR_UNSUPPORTED_SCOPES = {
    "ems_contratos_nacional": "EMS Contratos Nacional",
    "super_express_documentos_internacional": "Super Express Documentos Internacional",
    "super_express_paquetes_internacional": "Super Express Paquetes Internacional",
}

POSTAR_SCOPE_TO_CATEGORY = {
    "nacional": "EMS NAT",
    "internacional": "EMS INT",
    "encomienda_nacional": "MI ENCOMIENDA",
    "encomienda_internacional": "ENCOMIENDA",
    "ems_hoja5_nacional": "LC/AO NAT",
    "ems_hoja6_internacional": "LC/AO INT",
    "eca_nacional": "ECA NAT",
    "eca_internacional": "ECA INT",
    "pliegos_nacional": "PLIEGOS NAT",
    "pliegos_internacional": "PLIEGOS INT",
    "sacas_m_nacional": "SACAS M NAT",
    "sacas_m_internacional": "SACAS M INT",
    "super_express_nacional": "SUPER NAT",
}

POSTAR_INT_DEST_GROUPS = (
    {"prefix": "dest_a_", "label_es": "América del Sur", "label_en": "South America"},
    {"prefix": "dest_b_", "label_es": "América Central y Caribe", "label_en": "Central America and Caribbean"},
    {"prefix": "dest_c_", "label_es": "América del Norte", "label_en": "North America"},
    {"prefix": "dest_d_", "label_es": "Europa y Medio Oriente", "label_en": "Europe and Middle East"},
    {"prefix": "dest_e_", "label_es": "África, Asia y Oceanía", "label_en": "Africa, Asia and Oceania"},
)

_POSTAR_INT_DESTINOS = {
    "C": ("dest_a_argentina", "Argentina (zona A)"),
    "D": ("dest_b_belice", "Belice (zona B)"),
    "E": ("dest_c_eeuu", "Estados Unidos (zona C)"),
    "F": ("dest_d_espana", "España (zona D)"),
    "G": ("dest_e_argelia", "Argelia (zona E)"),
}

POSTAR_SCOPE_DESTINATION_BY_COLUMN = {
    "nacional": {
        "C": ("local_1", "Area Urbana (Hasta 2.5 Km)"),
        "D": ("local_2", "Area Urbana (Hasta 5 Km)"),
        "E": ("local_3", "Area Urbana (Hasta 7.5 Km)"),
        "F": ("local_4", "Area Urbana (Hasta 10 Km)"),
        "G": ("nacional_la_paz", "La Paz"),
        "H": ("nacional_oruro", "Oruro"),
        "I": ("nacional_pando", "Pando"),
        "J": ("nacional_beni", "Beni"),
    },
    "internacional": dict(_POSTAR_INT_DESTINOS),
    "encomienda_nacional": {
        "C": ("cui_cap_la_paz", "Ciudad Capital (La Paz)"),
        "D": ("cui1", "Trinidad / Cobija"),
        "E": ("pro_dentro", "Provincia Dentro Departamento"),
        "F": ("pro_otro", "Provincia en Otro Departamento"),
    },
    "encomienda_internacional": dict(_POSTAR_INT_DESTINOS),
    "ems_hoja5_nacional": {
        "C": ("local_1", "Area Urbana (Hasta 2.5 Km)"),
        "D": ("nacional_la_paz", "La Paz"),
        "E": ("pro_dentro", "Provincia Dentro Departamento"),
        "F": ("pro_otro", "Provincia en Otro Departamento"),
        "G": ("cui1", "Trinidad / Cobija"),
        "H": ("cui2", "Riberalta / Guayaramerin"),
    },
    "ems_hoja6_internacional": dict(_POSTAR_INT_DESTINOS),
    "eca_nacional": {
        "C": ("local_1", "Area Urbana (Hasta 2.5 Km)"),
        "D": ("nacional_la_paz", "La Paz"),
        "E": ("pro_dentro", "Provincia Dentro Departamento"),
        "F": ("pro_otro", "Provincia en Otro Departamento"),
        "G": ("cui1", "Trinidad / Cobija"),
        "H": ("cui2", "Riberalta / Guayaramerin"),
    },
    "eca_internacional": dict(_POSTAR_INT_DESTINOS),
    "pliegos_nacional": {
        "C": ("local_1", "Area Urbana (Hasta 2.5 Km)"),
        "D": ("nacional_la_paz", "La Paz"),
        "E": ("pro_dentro", "Provincia Dentro Departamento"),
        "F": ("pro_otro", "Provincia en Otro Departamento"),
    },
    "pliegos_internacional": dict(_POSTAR_INT_DESTINOS),
    "sacas_m_nacional": {
        "C": ("nacional_la_paz", "La Paz"),
        "D": ("pro_dentro", "Provincia Dentro Departamento"),
    },
    "sacas_m_internacional": dict(_POSTAR_INT_DESTINOS),
    "super_express_nacional": {
        "C": ("nacional_la_paz", "La Paz"),
    },
}

DESTINO_NACIONAL = {
    "cobija": "I",
    "trinidad": "I",
    "beni": "I",
    "riberalta": "J",
    "rieral": "J",
    "guayaramerin": "J",
    "guayarameri": "J",
    "guayara": "J",
    "ciudades intermedias": "H",
    "intermedias": "H",
}

SERVICIO_NACIONAL = {
    "ems nacional": "G",
    "cobertura 1": "C",
    "cobertura 2": "D",
    "cobertura 3": "E",
    "cobertura 4": "F",
}

SERVICIO_INTERNACIONAL = {
    "america del sur": "C",
    "america sur": "C",
    "sudamerica": "C",
    "destinos a": "C",
    "america central": "D",
    "caribe": "D",
    "destinos b": "D",
    "america del norte": "E",
    "norteamerica": "E",
    "destinos c": "E",
    "europa": "F",
    "medio oriente": "F",
    "destinos d": "F",
    "africa": "G",
    "asia": "G",
    "oceania": "G",
    "destinos e": "G",
}

SERVICIO_ENCOMIENDA_NACIONAL = {
    "ciudades capitales": "C",
    "destinos especiales": "D",
    "trinidad": "D",
    "cobija": "D",
    "trinidad cobija": "D",
    "trinidad -cobija": "D",
    "prov dentro depto": "E",
    "provincia dentro depto": "E",
    "prov en otro depto": "F",
    "provincia en otro depto": "F",
}

SERVICIO_ENCOMIENDA_INTERNACIONAL = {
    "america del sur": "C",
    "america sur": "C",
    "sudamerica": "C",
    "destinos a": "C",
    "america central": "D",
    "caribe": "D",
    "destinos b": "D",
    "america del norte": "E",
    "norteamerica": "E",
    "destinos c": "E",
    "europa": "F",
    "medio oriente": "F",
    "destinos d": "F",
    "africa": "G",
    "asia": "G",
    "oceania": "G",
    "destinos e": "G",
}

SERVICIO_EMS_HOJA5_NACIONAL = {
    "local": "C",
    "nacional": "D",
    "depto": "E",
    "departamental": "E",
    "prov": "F",
    "provincial": "F",
    "destino especial trinidad cobija": "G",
    "trinidad cobija": "G",
    "destino especial riberalta guayaramerin": "H",
    "riberalta guayaramerin": "H",
}

SERVICIO_EMS_HOJA6_INTERNACIONAL = {
    "america del sur": "C",
    "america sur": "C",
    "destino a": "C",
    "america central y el caribe": "D",
    "america central caribe": "D",
    "destino b": "D",
    "america del norte": "E",
    "destino c": "E",
    "europa y medio oriente": "F",
    "destino d": "F",
    "africa asia y oceania": "G",
    "destino e": "G",
}

SERVICIO_ECA_NACIONAL = {
    "local": "C",
    "nacional": "D",
    "prov dentro depto": "E",
    "provincia dentro depto": "E",
    "prov depto prov": "F",
    "provincia depto prov": "F",
    "depto prov": "F",
    "trinidad cobija": "G",
    "riberalta guayaramerin": "H",
}

SERVICIO_ECA_INTERNACIONAL = {
    "america del sur": "C",
    "america sur": "C",
    "sudamerica": "C",
    "destino a": "C",
    "america central y el caribe": "D",
    "america central caribe": "D",
    "destino b": "D",
    "america del norte": "E",
    "destino c": "E",
    "europa y medio oriente": "F",
    "destino d": "F",
    "africa asia y oceania": "G",
    "destino e": "G",
}

SERVICIO_PLIEGOS_NACIONAL = {
    "local": "C",
    "prov dentro depto": "E",
    "provincia dentro depto": "E",
    "prov depto prov": "F",
    "provincia depto prov": "F",
    "depto prov": "F",
    "nacional": "D",
}

SERVICIO_PLIEGOS_INTERNACIONAL = {
    "america del sur": "C",
    "america sur": "C",
    "sudamerica": "C",
    "destino a": "C",
    "america central y el caribe": "D",
    "america central caribe": "D",
    "destino b": "D",
    "america del norte": "E",
    "destino c": "E",
    "europa y medio oriente": "F",
    "destino d": "F",
    "africa asia y oceania": "G",
    "destino e": "G",
}

SERVICIO_SACAS_M_NACIONAL = {
    "provincial": "D",
    "provincia": "D",
    "nacional": "C",
}

SERVICIO_SACAS_M_INTERNACIONAL = {
    "america del sur": "C",
    "america sur": "C",
    "sudamerica": "C",
    "destino a": "C",
    "america central y el caribe": "D",
    "america central caribe": "D",
    "destino b": "D",
    "america del norte": "E",
    "destino c": "E",
    "europa y medio oriente": "F",
    "destino d": "F",
    "africa asia y oceania": "G",
    "destino e": "G",
}

SERVICIO_EMS_CONTRATOS_NACIONAL = {
    "ems nacional": "C",
    "ciudades intermedias": "D",
    "trinidad cobija": "E",
}

SERVICIO_SUPER_EXPRESS_NACIONAL = {
    "super express nacional": "C",
    "nacional": "C",
    "precio final": "C",
}

SERVICIO_SUPER_EXPRESS_DOCUMENTOS_INTERNACIONAL = {
    "sud america": "B",
    "sudamerica": "B",
    "tarifa 1": "B",
    "centro america": "C",
    "florida": "C",
    "tarifa 2": "C",
    "resto de eeuu": "D",
    "resto de ee uu": "D",
    "resto eeuu": "D",
    "tarifa 3": "D",
    "caribe": "E",
    "tarifa 4": "E",
    "europa": "F",
    "tarifa 5": "F",
    "medio oriente": "G",
    "tarifa 6": "G",
    "africa y asia": "H",
    "africa asia": "H",
    "tarifa 7": "H",
}

SERVICIO_SUPER_EXPRESS_PAQUETES_INTERNACIONAL = {
    "sud america": "B",
    "sudamerica": "B",
    "tarifa 1": "B",
    "centro america": "C",
    "florida": "C",
    "tarifa 2": "C",
    "resto de eeuu": "D",
    "resto de ee uu": "D",
    "resto eeuu": "D",
    "tarifa 3": "D",
    "caribe": "E",
    "tarifa 4": "E",
    "europa": "F",
    "tarifa 5": "F",
    "medio oriente": "G",
    "tarifa 6": "G",
    "africa y asia": "H",
    "africa asia": "H",
    "tarifa 7": "H",
}

SCOPE_HINTS = {
    "nacional": (
        "ems nacional", "tarifa nacional", "ems", "bolivia", "cobija", "trinidad", "riberalta", "guayaramerin", "intermedias"
    ),
    "internacional": (
        "ems internacional", "tarifa internacional", "internacional", "ems", "exterior", "fuera del pais", "america", "europa", "asia", "africa", "oceania", "caribe"
    ),
    "encomienda_nacional": (
        "mi encomienda", "prioritario", "prioritario nacional", "encomienda nacional",
        "ciudades capitales", "destinos especiales", "prov dentro depto", "prov en otro depto",
    ),
    "encomienda_internacional": (
        "encomiendas postales internacional", "encomienda internacional", "encomiendas internacional",
        "postal internacional", "america", "europa", "asia", "africa", "oceania", "caribe",
    ),
    "ems_hoja5_nacional": (
        "hoja 5", "ems hoja 5", "correo prioritario lc/ao nacional", "lc/ao nacional",
    ),
    "ems_hoja6_internacional": (
        "hoja 6", "ems hoja 6", "destino a", "destino b", "destino c", "destino d", "destino e",
    ),
    "eca_nacional": (
        "eca nacional", "correspondencia agrupada nacional", "hoja 7", "eca hoja 7",
    ),
    "eca_internacional": (
        "eca internacional", "correspondencia agrupada internacional", "hoja 8", "eca hoja 8",
    ),
    "pliegos_nacional": (
        "pliegos oficiales nacional", "hoja 9", "pliegos hoja 9",
    ),
    "pliegos_internacional": (
        "pliegos oficiales internacional", "hoja 10", "pliegos hoja 10",
    ),
    "sacas_m_nacional": (
        "sacas m nacional", "hoja 11", "sacas hoja 11",
    ),
    "sacas_m_internacional": (
        "sacas m internacional", "hoja 12", "sacas hoja 12",
    ),
    "ems_contratos_nacional": (
        "ems contratos nacional", "hoja 13", "contratos hoja 13",
    ),
    "super_express_nacional": (
        "super express nacional", "hoja 14", "super express hoja 14",
    ),
    "super_express_documentos_internacional": (
        "super express documentos internacional", "hoja 15", "super express hoja 15",
    ),
    "super_express_paquetes_internacional": (
        "super express paquetes internacional", "hoja 16", "super express hoja 16",
    ),
}

FAMILY_HINTS = {
    "ems": ("ems", "express mail"),
    "encomienda": ("encomienda", "encomiendas", "prioritario", "postal"),
    "ems_hoja5": ("hoja 5", "ems hoja 5", "correo prioritario lc/ao nacional", "lc/ao nacional", "lc ao nacional"),
    "ems_hoja6": ("hoja 6", "ems hoja 6", "correo prioritario lc/ao internacional", "lc/ao internacional", "lc ao internacional"),
    "eca": ("eca", "correspondencia agrupada"),
    "pliegos": ("pliegos oficiales", "pliegos"),
    "sacas_m": ("sacas m", "saca m"),
    "ems_contratos": ("ems contratos", "contratos ems"),
    "super_express": ("super express nacional", "super express"),
    "super_express_documentos": ("super express documentos", "documentos internacional"),
    "super_express_paquetes": ("super express paquetes", "paquetes internacional"),
}

TARIFA_KEYWORDS = (
    "tarifa", "precio", "cuanto cuesta", "cuánto cuesta", "costo", "costaria", "costaría",
    "sale", "vale", "cotiza", "cotizacion", "cotización", "presupuesto", "tarifario",
    "enviar", "envio", "envío", "paquete", "kilo", "gramo", "ems",
    "encomienda", "encomiendas", "prioritario", "postal",
)

TRACKING_HINTS = (
    "rastreo", "seguimiento", "tracking", "guia", "guía", "codigo", "código", "estado", "track"
)

EMS_INFO_HINTS = (
    "que es ems",
    "que significa ems",
    "que quiere decir ems",
    "explica ems",
    "definicion de ems",
    "definicion ems",
)

PESO_RE = re.compile(r"(\d+(?:[\.,]\d+)?)\s*(kg|k|kilo|kilos|kilogramo|kilogramos|g|gr|gramo|gramos)\b", re.IGNORECASE)
COLUMNA_RE = re.compile(r"\bcolumna\s*([B-J])\b", re.IGNORECASE)


@dataclass
class TarifaRequest:
    is_tarifa: bool
    scope: str | None
    family: str | None
    peso: str | None
    columna: str | None
    missing: list[str]
    ambiguous_scope: bool


@dataclass
class TarifaFragment:
    scope: str | None
    family: str | None
    peso: str | None
    columna: str | None
    columna_scope: str | None


def _normalize_text(texto: str) -> str:
    base = " ".join((texto or "").strip().lower().split())
    return "".join(ch for ch in unicodedata.normalize("NFKD", base) if not unicodedata.combining(ch))


def _tokenize(texto: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", _normalize_text(texto)) if t]


def _contains_term(text: str, term: str) -> bool:
    text = _normalize_text(text)
    term = _normalize_text(term)
    if not text or not term:
        return False
    pattern = r"\b" + re.escape(term).replace(r"\ ", r"\s+") + r"\b"
    return re.search(pattern, text) is not None


def _load_postar_dest_catalog() -> tuple[dict[str, str], list[str]]:
    label_by_code: dict[str, str] = {}
    ordered_codes: list[str] = []
    try:
        if not os.path.exists(POSTAR_OPTIONS_FILE):
            return label_by_code, ordered_codes
        with open(POSTAR_OPTIONS_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        for section in ("nacional", "internacional"):
            block = data.get(section) or {}
            for item in block.get("destinations") or []:
                code = str(item.get("value") or "").strip().lower()
                label = str(item.get("label") or "").strip()
                if not code:
                    continue
                label_by_code[code] = label or code
                if code not in ordered_codes:
                    ordered_codes.append(code)
    except Exception:
        return {}, []
    return label_by_code, ordered_codes


POSTAR_LABEL_BY_CODE, POSTAR_DEST_CODES_ORDER = _load_postar_dest_catalog()


def _postar_is_international_code(code: str) -> bool:
    c = (code or "").strip().lower()
    return c.startswith(("dest_a_", "dest_b_", "dest_c_", "dest_d_", "dest_e_"))


def _postar_scope_is_international(scope: str | None) -> bool:
    sc = (scope or "").strip().lower()
    return sc in {
        "internacional",
        "encomienda_internacional",
        "ems_hoja6_internacional",
        "eca_internacional",
        "pliegos_internacional",
        "sacas_m_internacional",
        "super_express_documentos_internacional",
        "super_express_paquetes_internacional",
    }


def _postar_scope_allows_code(scope: str | None, code: str | None) -> bool:
    sc = (scope or "").strip().lower()
    c = (code or "").strip().lower()
    if not sc or not c:
        return False

    if sc == "nacional":
        return c in {"local_1", "local_2", "local_3", "local_4"} or c.startswith("nacional_")
    if sc == "internacional":
        return _postar_is_international_code(c)
    if sc == "encomienda_nacional":
        return c.startswith("cui_cap_") or c in {"cui1", "pro_dentro", "pro_otro"}
    if sc == "encomienda_internacional":
        return _postar_is_international_code(c)
    if sc in {"ems_hoja5_nacional", "eca_nacional"}:
        return c in {"local_1", "pro_dentro", "pro_otro", "cui1", "cui2"} or c.startswith("nacional_")
    if sc in {"ems_hoja6_internacional", "eca_internacional", "pliegos_internacional", "sacas_m_internacional"}:
        return _postar_is_international_code(c)
    if sc == "pliegos_nacional":
        return c in {"local_1", "pro_dentro", "pro_otro"} or c.startswith("nacional_")
    if sc == "sacas_m_nacional":
        return c == "pro_dentro" or c.startswith("nacional_")
    if sc == "super_express_nacional":
        return c.startswith("nacional_")
    return False


def _encode_postar_destination(code: str) -> str:
    return f"{POSTAR_DEST_TOKEN_PREFIX}{(code or '').strip().lower()}"


def _encode_postar_destination_group(prefix: str) -> str:
    return f"{POSTAR_DEST_GROUP_TOKEN_PREFIX}{(prefix or '').strip().lower()}"


def _decode_postar_destination(value: str | None) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None
    low = raw.lower()
    prefix = POSTAR_DEST_TOKEN_PREFIX.lower()
    if not low.startswith(prefix):
        return None
    code = raw[len(POSTAR_DEST_TOKEN_PREFIX):].strip().lower()
    return code or None


def _decode_postar_destination_group(value: str | None) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None
    low = raw.lower()
    prefix = POSTAR_DEST_GROUP_TOKEN_PREFIX.lower()
    if not low.startswith(prefix):
        return None
    group_prefix = raw[len(POSTAR_DEST_GROUP_TOKEN_PREFIX):].strip().lower()
    if group_prefix in {"dest_a_", "dest_b_", "dest_c_", "dest_d_", "dest_e_"}:
        return group_prefix
    return None


def postar_destination_codes_for_scope(scope: str | None) -> list[str]:
    sc = (scope or "").strip().lower()
    if not sc:
        return []
    return [code for code in POSTAR_DEST_CODES_ORDER if _postar_scope_allows_code(sc, code)]


def resolve_postar_destination_group(value: str | None, scope: str | None) -> str | None:
    if not _postar_scope_is_international(scope):
        return None
    raw = (value or "").strip()
    if not raw:
        return None

    token_group = _decode_postar_destination_group(raw)
    if token_group:
        return token_group

    raw_norm = _normalize_text(raw)
    for group in POSTAR_INT_DEST_GROUPS:
        if raw_norm == _normalize_text(group["label_es"]) or raw_norm == _normalize_text(group["label_en"]):
            return group["prefix"]
    return None


def resolve_postar_destination_code(value: str | None, scope: str | None) -> str | None:
    sc = (scope or "").strip().lower()
    raw = (value or "").strip()
    if not sc or not raw:
        return None

    token_code = _decode_postar_destination(raw)
    if token_code and _postar_scope_allows_code(sc, token_code):
        return token_code

    code_candidate = raw.lower()
    if _postar_scope_allows_code(sc, code_candidate):
        return code_candidate

    value_norm = _normalize_text(raw)
    for code in postar_destination_codes_for_scope(sc):
        label_norm = _normalize_text(POSTAR_LABEL_BY_CODE.get(code, code))
        if value_norm == label_norm:
            return code
    return None


def postar_scope_requires_destination_group(scope: str | None) -> bool:
    return _postar_scope_is_international(scope)


def postar_destination_group_quick_replies(scope: str | None, lang: str = "es") -> list[dict]:
    if not _postar_scope_is_international(scope):
        return []
    out: list[dict] = []
    language = (lang or "es").strip().lower()
    for group in POSTAR_INT_DEST_GROUPS:
        label = group["label_en"] if language == "en" else group["label_es"]
        out.append({"label": label, "value": _encode_postar_destination_group(group["prefix"])})
    return out


def postar_destination_quick_replies(scope: str | None, destination_group: str | None = None) -> list[dict]:
    selected_group = (destination_group or "").strip().lower() or None
    options: list[dict] = []
    for code in postar_destination_codes_for_scope(scope):
        if selected_group and not code.startswith(selected_group):
            continue
        label = POSTAR_LABEL_BY_CODE.get(code, code)
        options.append({"label": label, "value": label})
    return options


def _extract_peso(texto: str) -> str | None:
    m = PESO_RE.search(texto or "")
    if not m:
        return None
    valor = m.group(1).replace(",", ".")
    unidad = m.group(2).lower()
    return f"{valor}kg" if unidad.startswith("k") else f"{valor}g"


def resolve_scope(value: str | None) -> str | None:
    t = _normalize_text(value or "")
    if not t:
        return None
    if t in SKILL_CONFIG:
        return t
    if t in {"nacional", "ems nacional", "local", "bolivia"}:
        return "nacional"
    if t in {"internacional", "ems internacional", "exterior"}:
        return "internacional"
    if t in {"encomienda nacional", "mi encomienda nacional", "prioritario nacional"}:
        return "encomienda_nacional"
    if t in {"encomienda internacional", "encomiendas postales internacional", "postal internacional"}:
        return "encomienda_internacional"
    if t in {"correo prioritario lc/ao nacional", "correo prioritario lc ao nacional", "lc/ao nacional", "lc ao nacional"}:
        return "ems_hoja5_nacional"
    if t in {"correo prioritario lc/ao internacional", "correo prioritario lc ao internacional", "lc/ao internacional", "lc ao internacional"}:
        return "ems_hoja6_internacional"
    if t in {"correspondencia agrupada nacional", "eca nacional"}:
        return "eca_nacional"
    if t in {"correspondencia agrupada internacional", "eca internacional"}:
        return "eca_internacional"
    if t in {"pliegos oficiales nacional", "pliegos nacional"}:
        return "pliegos_nacional"
    if t in {"pliegos oficiales internacional", "pliegos internacional"}:
        return "pliegos_internacional"
    if t in {"sacas m nacional", "saca m nacional"}:
        return "sacas_m_nacional"
    if t in {"sacas m internacional", "saca m internacional"}:
        return "sacas_m_internacional"
    if t in {"ems contratos nacional", "ems contrato nacional"}:
        return "ems_contratos_nacional"
    if t in {"super express nacional"}:
        return "super_express_nacional"
    if t in {"super express documentos internacional"}:
        return "super_express_documentos_internacional"
    if t in {"super express paquetes internacional"}:
        return "super_express_paquetes_internacional"
    # inferencia por familia + nivel (evita que "nacional/internacional" gane por empate)
    fam = detect_family(t)
    if fam == "eca":
        if _contains_term(t, "internacional"):
            return "eca_internacional"
        if _contains_term(t, "nacional"):
            return "eca_nacional"
    if fam == "pliegos":
        if _contains_term(t, "internacional"):
            return "pliegos_internacional"
        if _contains_term(t, "nacional"):
            return "pliegos_nacional"
    if fam == "sacas_m":
        if _contains_term(t, "internacional"):
            return "sacas_m_internacional"
        if _contains_term(t, "nacional"):
            return "sacas_m_nacional"
    if fam == "ems_contratos":
        return "ems_contratos_nacional"
    if fam == "super_express_documentos":
        return "super_express_documentos_internacional"
    if fam == "super_express_paquetes":
        return "super_express_paquetes_internacional"
    if fam == "super_express":
        return "super_express_nacional"
    # inferencia por palabras clave
    scores = {scope: sum(1 for k in hints if _contains_term(t, k)) for scope, hints in SCOPE_HINTS.items()}
    best_scope, best_score = max(scores.items(), key=lambda kv: kv[1])
    sorted_scores = sorted(scores.values(), reverse=True)
    second_score = sorted_scores[1] if len(sorted_scores) > 1 else 0
    if best_score > 0 and best_score > second_score:
        return best_scope
    return None


def detect_family(value: str | None) -> str | None:
    t = _normalize_text(value or "")
    if not t:
        return None
    ems_score = sum(1 for k in FAMILY_HINTS["ems"] if _contains_term(t, k))
    enc_score = sum(1 for k in FAMILY_HINTS["encomienda"] if _contains_term(t, k))
    ems5_score = sum(1 for k in FAMILY_HINTS["ems_hoja5"] if _contains_term(t, k))
    ems6_score = sum(1 for k in FAMILY_HINTS["ems_hoja6"] if _contains_term(t, k))
    eca_score = sum(1 for k in FAMILY_HINTS["eca"] if _contains_term(t, k))
    pliegos_score = sum(1 for k in FAMILY_HINTS["pliegos"] if _contains_term(t, k))
    sacas_score = sum(1 for k in FAMILY_HINTS["sacas_m"] if _contains_term(t, k))
    contratos_score = sum(1 for k in FAMILY_HINTS["ems_contratos"] if _contains_term(t, k))
    sx_score = sum(1 for k in FAMILY_HINTS["super_express"] if _contains_term(t, k))
    sxd_score = sum(1 for k in FAMILY_HINTS["super_express_documentos"] if _contains_term(t, k))
    sxp_score = sum(1 for k in FAMILY_HINTS["super_express_paquetes"] if _contains_term(t, k))
    max_score = max(
        ems_score, enc_score, ems5_score, ems6_score, eca_score, pliegos_score,
        sacas_score, contratos_score, sx_score, sxd_score, sxp_score
    )
    if ems5_score and ems5_score >= max_score:
        return "ems_hoja5"
    if ems6_score and ems6_score >= max_score:
        return "ems_hoja6"
    if eca_score and eca_score >= max_score:
        return "eca"
    if pliegos_score and pliegos_score >= max_score:
        return "pliegos"
    if sacas_score and sacas_score >= max_score:
        return "sacas_m"
    if contratos_score and contratos_score >= max_score:
        return "ems_contratos"
    if sxd_score and sxd_score >= max_score:
        return "super_express_documentos"
    if sxp_score and sxp_score >= max_score:
        return "super_express_paquetes"
    if sx_score and sx_score >= max_score:
        return "super_express"
    if ems_score and not enc_score:
        return "ems"
    if enc_score and not ems_score:
        return "encomienda"
    return None


def _match_columna_with_map(texto_norm: str, mapping: dict[str, str]) -> str | None:
    for alias, col in mapping.items():
        if _contains_term(texto_norm, alias):
            return col

    tokens = _tokenize(texto_norm)
    candidates = set(tokens)
    for i in range(len(tokens) - 1):
        candidates.add(f"{tokens[i]} {tokens[i + 1]}")

    best = None
    best_ratio = 0.0
    keys = list(mapping.keys())
    for cand in candidates:
        for key in keys:
            ratio = difflib.SequenceMatcher(a=cand, b=key).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best = key

    if best and best_ratio >= 0.84:
        return mapping[best]
    return None


def _extract_columna_and_scope(texto: str) -> tuple[str | None, str | None]:
    txt = _normalize_text(texto)

    m = COLUMNA_RE.search(txt)
    if m:
        return m.group(1).upper(), None

    col_ems_n = _match_columna_with_map(txt, {**DESTINO_NACIONAL, **SERVICIO_NACIONAL})
    col_ems_i = _match_columna_with_map(txt, SERVICIO_INTERNACIONAL)
    col_enc_n = _match_columna_with_map(txt, SERVICIO_ENCOMIENDA_NACIONAL)
    col_enc_i = _match_columna_with_map(txt, SERVICIO_ENCOMIENDA_INTERNACIONAL)
    col_ems5_n = _match_columna_with_map(txt, SERVICIO_EMS_HOJA5_NACIONAL)
    col_ems6_i = _match_columna_with_map(txt, SERVICIO_EMS_HOJA6_INTERNACIONAL)
    col_eca_n = _match_columna_with_map(txt, SERVICIO_ECA_NACIONAL)
    col_eca_i = _match_columna_with_map(txt, SERVICIO_ECA_INTERNACIONAL)
    col_pliegos_n = _match_columna_with_map(txt, SERVICIO_PLIEGOS_NACIONAL)
    col_pliegos_i = _match_columna_with_map(txt, SERVICIO_PLIEGOS_INTERNACIONAL)
    col_sacas_n = _match_columna_with_map(txt, SERVICIO_SACAS_M_NACIONAL)
    col_sacas_i = _match_columna_with_map(txt, SERVICIO_SACAS_M_INTERNACIONAL)
    col_contratos_n = _match_columna_with_map(txt, SERVICIO_EMS_CONTRATOS_NACIONAL)
    col_sx_n = _match_columna_with_map(txt, SERVICIO_SUPER_EXPRESS_NACIONAL)
    col_sxd_i = _match_columna_with_map(txt, SERVICIO_SUPER_EXPRESS_DOCUMENTOS_INTERNACIONAL)
    col_sxp_i = _match_columna_with_map(txt, SERVICIO_SUPER_EXPRESS_PAQUETES_INTERNACIONAL)

    candidates = []
    if col_ems_n:
        candidates.append((col_ems_n, "nacional"))
    if col_ems_i:
        candidates.append((col_ems_i, "internacional"))
    if col_enc_n:
        candidates.append((col_enc_n, "encomienda_nacional"))
    if col_enc_i:
        candidates.append((col_enc_i, "encomienda_internacional"))
    if col_ems5_n:
        candidates.append((col_ems5_n, "ems_hoja5_nacional"))
    if col_ems6_i:
        candidates.append((col_ems6_i, "ems_hoja6_internacional"))
    if col_eca_n:
        candidates.append((col_eca_n, "eca_nacional"))
    if col_eca_i:
        candidates.append((col_eca_i, "eca_internacional"))
    if col_pliegos_n:
        candidates.append((col_pliegos_n, "pliegos_nacional"))
    if col_pliegos_i:
        candidates.append((col_pliegos_i, "pliegos_internacional"))
    if col_sacas_n:
        candidates.append((col_sacas_n, "sacas_m_nacional"))
    if col_sacas_i:
        candidates.append((col_sacas_i, "sacas_m_internacional"))
    if col_contratos_n:
        candidates.append((col_contratos_n, "ems_contratos_nacional"))
    if col_sx_n:
        candidates.append((col_sx_n, "super_express_nacional"))
    if col_sxd_i:
        candidates.append((col_sxd_i, "super_express_documentos_internacional"))
    if col_sxp_i:
        candidates.append((col_sxp_i, "super_express_paquetes_internacional"))

    if len(candidates) == 1:
        return candidates[0]

    family = detect_family(txt)
    if family == "ems":
        for col, scope in candidates:
            if scope in {"nacional", "internacional"}:
                return col, scope
    if family == "encomienda":
        for col, scope in candidates:
            if scope in {"encomienda_nacional", "encomienda_internacional"}:
                return col, scope
    if family == "ems_hoja5":
        for col, scope in candidates:
            if scope == "ems_hoja5_nacional":
                return col, scope
    if family == "ems_hoja6":
        for col, scope in candidates:
            if scope == "ems_hoja6_internacional":
                return col, scope
    if family == "eca":
        for col, scope in candidates:
            if scope in {"eca_nacional", "eca_internacional"}:
                return col, scope
    if family == "pliegos":
        for col, scope in candidates:
            if scope in {"pliegos_nacional", "pliegos_internacional"}:
                return col, scope
    if family == "sacas_m":
        for col, scope in candidates:
            if scope in {"sacas_m_nacional", "sacas_m_internacional"}:
                return col, scope
    if family == "ems_contratos":
        for col, scope in candidates:
            if scope == "ems_contratos_nacional":
                return col, scope
    if family == "super_express":
        for col, scope in candidates:
            if scope == "super_express_nacional":
                return col, scope
    if family == "super_express_documentos":
        for col, scope in candidates:
            if scope == "super_express_documentos_internacional":
                return col, scope
    if family == "super_express_paquetes":
        for col, scope in candidates:
            if scope == "super_express_paquetes_internacional":
                return col, scope

    if candidates:
        # ambiguo por alias o familias: devolver columna sin alcance fijo
        return candidates[0][0], None
    return None, None


def _mapping_for_scope(scope: str | None) -> dict[str, str]:
    sc = (scope or "").strip().lower()
    if sc == "nacional":
        return {**DESTINO_NACIONAL, **SERVICIO_NACIONAL}
    if sc == "internacional":
        return dict(SERVICIO_INTERNACIONAL)
    if sc == "encomienda_nacional":
        return dict(SERVICIO_ENCOMIENDA_NACIONAL)
    if sc == "encomienda_internacional":
        return dict(SERVICIO_ENCOMIENDA_INTERNACIONAL)
    if sc == "ems_hoja5_nacional":
        return dict(SERVICIO_EMS_HOJA5_NACIONAL)
    if sc == "ems_hoja6_internacional":
        return dict(SERVICIO_EMS_HOJA6_INTERNACIONAL)
    if sc == "eca_nacional":
        return dict(SERVICIO_ECA_NACIONAL)
    if sc == "eca_internacional":
        return dict(SERVICIO_ECA_INTERNACIONAL)
    if sc == "pliegos_nacional":
        return dict(SERVICIO_PLIEGOS_NACIONAL)
    if sc == "pliegos_internacional":
        return dict(SERVICIO_PLIEGOS_INTERNACIONAL)
    if sc == "sacas_m_nacional":
        return dict(SERVICIO_SACAS_M_NACIONAL)
    if sc == "sacas_m_internacional":
        return dict(SERVICIO_SACAS_M_INTERNACIONAL)
    if sc == "ems_contratos_nacional":
        return dict(SERVICIO_EMS_CONTRATOS_NACIONAL)
    if sc == "super_express_nacional":
        return dict(SERVICIO_SUPER_EXPRESS_NACIONAL)
    if sc == "super_express_documentos_internacional":
        return dict(SERVICIO_SUPER_EXPRESS_DOCUMENTOS_INTERNACIONAL)
    if sc == "super_express_paquetes_internacional":
        return dict(SERVICIO_SUPER_EXPRESS_PAQUETES_INTERNACIONAL)
    return {}


def resolve_columna(value: str | None, scope: str | None = None) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None
    if scope is not None:
        destination_code = resolve_postar_destination_code(raw, scope)
        if destination_code:
            return _encode_postar_destination(destination_code)
    if len(raw) == 1:
        col = raw.upper()
        if col in {"B", "C", "D", "E", "F", "G", "H", "I", "J"}:
            if scope is None:
                return col
            allowed = SKILL_CONFIG[scope]["columns"]
            return col if col in allowed else None
    if scope is not None:
        scoped_map = _mapping_for_scope(scope)
        if scoped_map:
            col_scoped = _match_columna_with_map(_normalize_text(raw), scoped_map)
            if col_scoped:
                return col_scoped
    col, inferred = _extract_columna_and_scope(raw)
    if not col:
        return None
    if scope is None:
        return col
    return col if col in SKILL_CONFIG[scope]["columns"] else None


def columna_valida_para_scope(columna: str | None, scope: str | None) -> bool:
    token_code = _decode_postar_destination(columna)
    sc = (scope or "").strip().lower()
    if token_code and sc in POSTAR_SCOPE_TO_CATEGORY:
        return _postar_scope_allows_code(sc, token_code)

    col = (columna or "").strip().upper()
    sc = (scope or "").strip().lower()
    if not col or not sc or sc not in SKILL_CONFIG:
        return False
    return col in SKILL_CONFIG[sc]["columns"]


def infer_scope_from_columna(columna: str | None) -> str | None:
    token_code = _decode_postar_destination(columna)
    if token_code:
        matching_scopes = [scope for scope in POSTAR_SCOPE_TO_CATEGORY if _postar_scope_allows_code(scope, token_code)]
        if len(matching_scopes) == 1:
            return matching_scopes[0]
        return None

    col = (columna or "").strip().upper()
    if not col:
        return None
    # I/J siguen siendo columnas exclusivas de EMS Nacional (skill1).
    if col in {"I", "J"}:
        return "nacional"
    # B/C/D/E/F/G/H existen en múltiples hojas (ambiguo).
    return None


def default_columna_for_scope(scope: str | None) -> str | None:
    sc = (scope or "").strip().lower()
    if sc in POSTAR_SCOPE_TO_CATEGORY:
        return None
    cfg = SKILL_CONFIG.get(sc)
    if not cfg:
        return None
    cols = cfg.get("columns") or set()
    if len(cols) != 1:
        return None
    return next(iter(cols))


def extract_tarifa_fragment(
    texto: str | None,
    prefer_scope: str | None = None,
    prefer_family: str | None = None,
) -> TarifaFragment:
    src = texto or ""
    scope = resolve_scope(src)
    family = detect_family(src)
    peso = _extract_peso(src)
    col, col_scope = _extract_columna_and_scope(src)

    preferred = (prefer_scope or "").strip().lower() or None
    preferred_family = (prefer_family or "").strip().lower() or None
    if not family and scope in {"encomienda_nacional", "encomienda_internacional"}:
        family = "encomienda"
    if not family and preferred_family in {
        "ems", "encomienda", "ems_hoja5", "ems_hoja6", "eca", "pliegos", "sacas_m",
        "ems_contratos", "super_express", "super_express_documentos", "super_express_paquetes"
    }:
        family = preferred_family

    if not col:
        col = resolve_columna(src, scope=scope or preferred)
    elif preferred and scope is None and not columna_valida_para_scope(col, preferred):
        # Si la detección global eligió otra familia por alias ambiguo,
        # priorizamos el alcance esperado del flujo conversacional.
        col = resolve_columna(src, scope=preferred) or col

    return TarifaFragment(
        scope=scope,
        family=family,
        peso=peso,
        columna=col,
        columna_scope=col_scope,
    )


def parse_tarifa_request(pregunta: str) -> TarifaRequest:
    t = _normalize_text(pregunta)
    looks_ems_info = any(_contains_term(t, k) for k in EMS_INFO_HINTS)
    has_keyword = any(k in t for k in TARIFA_KEYWORDS)
    has_tariff_topic = any(_contains_term(t, k) for k in ("tarifa", "tarifas", "tarifario", "precios"))
    looks_tracking = any(k in t for k in TRACKING_HINTS)

    fragment = extract_tarifa_fragment(pregunta)
    family = fragment.family
    peso = fragment.peso
    col = fragment.columna
    col_scope = fragment.columna_scope
    scope = fragment.scope
    if not scope and col_scope:
        scope = col_scope
    if not scope:
        scope = infer_scope_from_columna(col)

    is_tarifa = bool(
        (
            has_tariff_topic
            or (has_keyword and (peso or col or "ems" in t))
            or (peso and col)
        )
        and not looks_tracking
    )
    if looks_ems_info and not peso and not col:
        is_tarifa = False

    ambiguous_scope = bool(is_tarifa and scope is None)

    missing: list[str] = []
    if is_tarifa and ambiguous_scope:
        if family == "ems":
            missing.append("alcance_ems")
        elif family == "encomienda":
            missing.append("alcance_encomienda")
        else:
            missing.append("alcance")
    if is_tarifa and not peso:
        missing.append("peso")
    if is_tarifa and not col:
        missing.append("destino")

    return TarifaRequest(
        is_tarifa=is_tarifa,
        scope=scope,
        family=family,
        peso=peso,
        columna=col,
        missing=missing,
        ambiguous_scope=ambiguous_scope,
    )


def missing_message(missing: list[str]) -> str:
    if not missing:
        return ""
    if "tipo_nacional" in missing:
        return "¿Qué servicio quieres usar?"
    if "tipo_internacional" in missing:
        return "¿Qué servicio quieres usar?"
    if "alcance_ems" in missing:
        return "¿Será nacional o internacional?"
    if "alcance_encomienda" in missing:
        return "¿Será nacional o internacional?"
    if "alcance" in missing:
        return "¿Qué tarifario quieres usar?"
    if len(missing) >= 2:
        return "Para calcular la tarifa necesito peso y destino (ej: 2.5kg a Cobija)."
    if missing[0] == "peso":
        return "Para calcular la tarifa necesito el peso (ej: 500g o 2.5kg)."
    return "Para calcular la tarifa necesito el destino/servicio."


def skill_ready(scope: str) -> tuple[bool, str | None]:
    sc = (scope or "").strip().lower()
    if not sc or sc not in SKILL_CONFIG:
        return False, f"Scope de tarifa no soportado: {scope}"
    if sc in POSTAR_UNSUPPORTED_SCOPES:
        return (
            False,
            f"El servicio '{POSTAR_UNSUPPORTED_SCOPES[sc]}' no está disponible en la API POSTAR.",
        )
    if sc not in POSTAR_SCOPE_TO_CATEGORY:
        return False, f"No existe mapeo API para el scope: {sc}"
    if sc not in POSTAR_SCOPE_DESTINATION_BY_COLUMN:
        return False, f"No existe mapeo de destinos API para el scope: {sc}"
    if not POSTAR_API_URL:
        return False, "No se configuró POSTAR_API_URL"
    return True, None


def _parse_peso_to_kg(peso: str) -> float | None:
    raw = (peso or "").strip().lower().replace(",", ".")
    if not raw:
        return None
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([a-z]+)?", raw)
    if not match:
        return None
    value = float(match.group(1))
    unit = (match.group(2) or "kg").strip()
    if unit in {"g", "gr", "gramo", "gramos"}:
        return value / 1000.0
    if unit in {"kg", "k", "kilo", "kilos", "kilogramo", "kilogramos"}:
        return value
    return None


def _resolve_postar_destination(scope: str, columna: str) -> tuple[str, str] | None:
    token_code = _decode_postar_destination(columna)
    if token_code and _postar_scope_allows_code(scope, token_code):
        return token_code, POSTAR_LABEL_BY_CODE.get(token_code, token_code)
    mapping = POSTAR_SCOPE_DESTINATION_BY_COLUMN.get(scope) or {}
    return mapping.get((columna or "").strip().upper())


def _is_out_of_range_message(value: str) -> bool:
    t = _normalize_text(value or "")
    return "fuera de rango" in t or "out of range" in t


def _request_postar_tariff(payload: dict) -> dict:
    try:
        response = requests.post(
            POSTAR_API_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=POSTAR_API_TIMEOUT,
            verify=POSTAR_API_VERIFY_SSL,
        )
    except requests.RequestException as exc:
        return {"ok": False, "error": f"No se pudo conectar con la API de tarifas: {exc}"}

    data: dict | None
    try:
        parsed = response.json()
        data = parsed if isinstance(parsed, dict) else None
    except ValueError:
        data = None

    if response.status_code >= 400:
        detail = ""
        if isinstance(data, dict):
            detail = str(data.get("message") or data.get("error") or data.get("detail") or "").strip()
        if not detail:
            detail = (response.text or "").strip()[:300]
        result = {"ok": False, "error": f"POSTAR devolvió HTTP {response.status_code}. {detail}".strip()}
        if _is_out_of_range_message(detail):
            result["error_code"] = "out_of_range"
        return result

    if not isinstance(data, dict):
        return {"ok": False, "error": "La API POSTAR devolvió una respuesta no JSON válida."}

    success = data.get("success")
    if success is False:
        detail = str(data.get("message") or data.get("error") or "La API POSTAR no pudo calcular la tarifa.")
        result = {"ok": False, "error": detail}
        if _is_out_of_range_message(detail):
            result["error_code"] = "out_of_range"
        return result

    tarifa_raw = data.get("tarifa")
    if tarifa_raw is None:
        return {"ok": False, "error": "La API POSTAR no devolvió el campo 'tarifa'."}
    try:
        tarifa = float(tarifa_raw)
    except (TypeError, ValueError):
        return {"ok": False, "error": "La API POSTAR devolvió una tarifa inválida."}

    return {"ok": True, "tarifa": tarifa, "api_response": data}


def ejecutar_tarifa(peso: str, columna: str, scope: str, xlsx: str | None = None) -> dict:
    scope = (scope or "").strip().lower()
    ok, err = skill_ready(scope)
    if not ok:
        return {"ok": False, "error": err, "scope": scope, "engine": "postar_api"}

    cfg = SKILL_CONFIG[scope]
    allowed_cols = cfg["columns"]
    peso = (peso or "").strip().lower()
    columna = (columna or "").strip()
    columna_upper = columna.upper()
    token_code = _decode_postar_destination(columna)

    if not peso:
        return {"ok": False, "error": "Falta peso", "scope": scope, "engine": "postar_api"}
    if token_code:
        if not _postar_scope_allows_code(scope, token_code):
            return {
                "ok": False,
                "error": f"Destino inválido para {scope}: {token_code}",
                "scope": scope,
                "engine": "postar_api",
            }
    elif columna_upper not in allowed_cols:
        return {"ok": False, "error": f"Columna inválida para {scope}: {columna_upper}", "scope": scope, "engine": "postar_api"}

    cache_col_key = _encode_postar_destination(token_code) if token_code else columna_upper
    cached = get_tariff(scope, peso, cache_col_key, xlsx)
    if cached is not None:
        return {**cached, "cached": True}

    peso_kg = _parse_peso_to_kg(peso)
    if peso_kg is None or peso_kg <= 0:
        return {
            "ok": False,
            "error": "Formato de peso inválido. Usa por ejemplo 500g o 2.5kg.",
            "scope": scope,
            "engine": "postar_api",
        }

    destino_info = _resolve_postar_destination(scope, columna if token_code else columna_upper)
    if not destino_info:
        return {
            "ok": False,
            "error": f"No hay un destino API mapeado para {scope} y selector '{columna}'.",
            "scope": scope,
            "engine": "postar_api",
        }
    destino_code, destino_label = destino_info
    categoria = POSTAR_SCOPE_TO_CATEGORY[scope]

    payload = {
        "categoria": categoria,
        "destino": destino_code,
        "peso": peso_kg,
        "certificado": POSTAR_DEFAULT_CERTIFICADO,
        "espreso": POSTAR_DEFAULT_ESPRESO,
        "recibo": POSTAR_DEFAULT_RECIBO,
    }

    result = _request_postar_tariff(payload)
    if not result.get("ok"):
        result["scope"] = scope
        result["skill_id"] = cfg["skill_id"]
        result["engine"] = "postar_api"
        return result

    tarifa = float(result["tarifa"])
    price = int(tarifa) if tarifa.is_integer() else round(tarifa, 2)
    output = {
        "ok": True,
        "scope": scope,
        "skill_id": cfg["skill_id"],
        "engine": "postar_api",
        "categoria": categoria,
        "destino": destino_code,
        "destino_label": destino_label,
        "peso_kg": round(peso_kg, 6),
        "peso_g": round(peso_kg * 1000.0, 2),
        "tarifa": price,
        "precio": price,
        "servicio": f"{categoria} · {destino_label}",
        "api_payload": payload,
        "api_response": result.get("api_response"),
    }
    if xlsx:
        output["warning"] = "El parámetro xlsx se ignora cuando se usa POSTAR API."
    set_tariff(scope, peso, cache_col_key, output, xlsx)
    return output


def format_tarifa_response(resultado: dict) -> str:
    if not resultado.get("ok"):
        err = resultado.get("error") or "No se pudo calcular la tarifa."
        return f"No pude calcular la tarifa en este momento. Detalle: {err}"

    precio = resultado.get("precio")
    categoria = resultado.get("categoria") or "N/A"
    destino = resultado.get("destino_label") or resultado.get("destino") or "N/A"
    peso_kg = resultado.get("peso_kg")
    scope_key = (resultado.get("scope") or "").strip().lower()
    scope = SKILL_CONFIG.get(scope_key, {}).get("label") or scope_key.capitalize()

    return (
        f"{scope}\n"
        f"Precio final: {precio} Bs\n"
        f"Categoría: {categoria}\n"
        f"Destino: {destino}\n"
        f"Peso consultado: {peso_kg} kg"
    )
