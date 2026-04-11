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
import subprocess
import time
import unicodedata
from dataclasses import dataclass


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

DEFAULT_TIMEOUT_SECONDS = int(os.environ.get("TARIFF_SKILL_TIMEOUT", "18"))
DEFAULT_RETRIES = int(os.environ.get("TARIFF_SKILL_RETRIES", "1"))
CACHE_TTL_SECONDS = int(os.environ.get("TARIFF_CACHE_TTL_SECONDS", "60"))
CACHE_MAX_ITEMS = int(os.environ.get("TARIFF_CACHE_MAX_ITEMS", "256"))
_CACHE: dict[tuple[str, str, str, str], tuple[float, dict]] = {}

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
    col = (columna or "").strip().upper()
    sc = (scope or "").strip().lower()
    if not col or not sc or sc not in SKILL_CONFIG:
        return False
    return col in SKILL_CONFIG[sc]["columns"]


def infer_scope_from_columna(columna: str | None) -> str | None:
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
    cfg = SKILL_CONFIG.get(scope)
    if not cfg:
        return False, f"Scope de tarifa no soportado: {scope}"
    wrapper = cfg["wrapper"]
    if not os.path.exists(wrapper):
        return False, f"No se encontró wrapper de tarifas en: {wrapper}"
    return True, None


def _cache_get(scope: str, peso: str, columna: str, xlsx: str | None) -> dict | None:
    key = (scope, peso, columna, xlsx or "")
    item = _CACHE.get(key)
    if not item:
        return None
    ts, data = item
    if time.time() - ts > CACHE_TTL_SECONDS:
        _CACHE.pop(key, None)
        return None
    return data


def _cache_set(scope: str, peso: str, columna: str, xlsx: str | None, data: dict) -> None:
    if CACHE_MAX_ITEMS <= 0:
        return
    if len(_CACHE) >= CACHE_MAX_ITEMS:
        oldest_key = min(_CACHE.items(), key=lambda kv: kv[1][0])[0]
        _CACHE.pop(oldest_key, None)
    _CACHE[(scope, peso, columna, xlsx or "")] = (time.time(), data)


def _parse_wrapper_output(raw: str, exit_code: int) -> dict:
    text = (raw or "").strip()
    if not text:
        return {"ok": False, "error": "La skill de tarifas no devolvió salida", "exit_code": exit_code}

    low = _normalize_text(text)
    if "peso fuera de rango" in low or "precio vacio" in low or "precio vacio" in low:
        return {
            "ok": False,
            "error": "Peso fuera de rango para este tarifario",
            "error_code": "out_of_range",
            "raw": text,
            "exit_code": exit_code,
        }

    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(0))
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    return {
        "ok": False,
        "error": "No se pudo parsear JSON de la skill de tarifas",
        "raw": text,
        "exit_code": exit_code,
    }


def ejecutar_tarifa(peso: str, columna: str, scope: str, xlsx: str | None = None) -> dict:
    scope = (scope or "").strip().lower()
    ok, err = skill_ready(scope)
    if not ok:
        return {"ok": False, "error": err}

    cfg = SKILL_CONFIG[scope]
    allowed_cols = cfg["columns"]
    wrapper = cfg["wrapper"]

    peso = (peso or "").strip().lower()
    columna = (columna or "").strip().upper()

    if not peso:
        return {"ok": False, "error": "Falta peso"}
    if columna not in allowed_cols:
        return {"ok": False, "error": f"Columna inválida para EMS {scope}: {columna}"}

    cached = _cache_get(scope, peso, columna, xlsx)
    if cached is not None:
        return {**cached, "cached": True}

    cmd = ["bash", wrapper, "--peso", peso, "--columna", columna]
    if xlsx:
        cmd.extend(["--xlsx", xlsx])

    attempts = max(DEFAULT_RETRIES, 1)
    last = {"ok": False, "error": "Error desconocido"}

    for _ in range(attempts):
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=DEFAULT_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired:
            last = {"ok": False, "error": f"Timeout al ejecutar skill de tarifas ({DEFAULT_TIMEOUT_SECONDS}s)"}
            continue
        except Exception as exc:
            last = {"ok": False, "error": f"Error ejecutando skill de tarifas: {exc}"}
            continue

        parsed = _parse_wrapper_output(proc.stdout or proc.stderr or "", proc.returncode)
        if parsed.get("ok"):
            parsed["scope"] = scope
            parsed["skill_id"] = cfg["skill_id"]
            _cache_set(scope, peso, columna, xlsx, parsed)
            return parsed
        last = parsed

    if isinstance(last, dict):
        last["scope"] = scope
    return last


def format_tarifa_response(resultado: dict) -> str:
    if not resultado.get("ok"):
        err = resultado.get("error") or "No se pudo calcular la tarifa."
        return f"No pude calcular la tarifa en este momento. Detalle: {err}"

    precio = resultado.get("precio")
    servicio = resultado.get("servicio") or "No especificado"
    rango = resultado.get("rango") or {}
    min_g = rango.get("min_g")
    max_g = rango.get("max_g")
    peso_g = resultado.get("peso_g")
    scope_key = (resultado.get("scope") or "").strip().lower()
    scope = SKILL_CONFIG.get(scope_key, {}).get("label") or scope_key.capitalize()

    nota = ""
    try:
        if peso_g is not None and min_g is not None and float(peso_g) < float(min_g):
            nota = "\nNota: se aplicó tarifa del siguiente rango disponible."
    except Exception:
        nota = ""

    return (
        f"{scope}\n"
        f"Precio final: {precio} Bs\n"
        f"Servicio: {servicio}\n"
        f"Rango aplicado: {min_g}-{max_g} g\n"
        f"Peso consultado: {peso_g} g"
        f"{nota}"
    )
