"""
core/capabilities.py
Registro ejecutable de skills, PDFs y recursos del bot.
"""

import json
import os
import re
import shutil
import unicodedata
import hashlib
from datetime import datetime

from core import observability, contacto
from core.capabilities_pdf import (
    PDF_CLEAN_MODE_DEFAULT,
    PDF_CLEAN_MODES,
    _clean_pdf_entry,
    _file_stats,
    _pdf_record_id,
    _resolve_clean_mode,
    _sanitize_filename,
    extraer_texto_pdf,
)


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(BASE_DIR, "data")

SKILLS_FILE = os.environ.get("SKILLS_FILE", os.path.join(DATA_DIR, "skills.json"))
PDFS_FILE = os.environ.get("PDFS_FILE", os.path.join(DATA_DIR, "pdfs_contenido.json"))
PDF_DIR = os.environ.get("PDF_DIR", os.path.join(DATA_DIR, "pdfs_descargados"))
PDF_REPROCESS_MIN_TEXT = int(os.environ.get("PDF_REPROCESS_MIN_TEXT", "180"))
SCRAPER_STATS_FILE = os.path.join(DATA_DIR, "estadisticas.json")
SCRAPER_APLICATIVOS_FILE = os.path.join(DATA_DIR, "aplicativos_detalle.json")
SCRAPER_SERVICIOS_FILE = os.path.join(DATA_DIR, "aplicaciones_servicios.json")
SCRAPER_HISTORIA_FILE = os.path.join(DATA_DIR, "historia_institucional.json")
SCRAPER_NOTICIAS_FILE = os.path.join(DATA_DIR, "noticias_eventos.json")
SCRAPER_SECCIONES_FILE = os.path.join(DATA_DIR, "secciones_home.json")
SCRAPER_SUCURSALES_FILE = os.path.join(DATA_DIR, "sucursales_contacto.json")
EXCLUDED_MANAGED_JSON_FILES = {"pdfs_contenido.json", "skills.json"}

DEFAULT_SKILLS: list = []  # Sin skills manuales. Todo es busqueda semantica en Qdrant.

SUPPORTED_SKILL_MODES = [
    {"id": "rag+llm", "nombre": "RAG + LLM"},
    {"id": "translation", "nombre": "Traduccion"},
    {"id": "internal", "nombre": "Interna"},
    {"id": "custom", "nombre": "Personalizada"},
]

SUPPORTED_SKILL_CATEGORIES = [
    {"id": "atencion", "nombre": "Atencion"},
    {"id": "idioma", "nombre": "Idioma"},
    {"id": "operacion", "nombre": "Operacion"},
    {"id": "documental", "nombre": "Documental"},
    {"id": "analitica", "nombre": "Analitica"},
    {"id": "custom", "nombre": "Custom"},
]

SUPPORTED_SKILL_MODE_IDS = {item["id"] for item in SUPPORTED_SKILL_MODES}
SUPPORTED_SKILL_CATEGORY_IDS = {item["id"] for item in SUPPORTED_SKILL_CATEGORIES}

SKILL_SCOPE_KEYWORDS = {
    "correos", "agbc", "postal", "postales", "envio", "envíos", "envios", "paquete", "paquetes",
    "rastreo", "seguimiento", "guia", "guía", "tracking", "ems", "encomienda",
    "reclamo", "queja", "quejas", "estafa", "fraude", "seguridad", "filatelia", "sello", "sellos",
    "oficina", "oficinas", "sucursal", "sucursales", "estampilla", "estampillas",
    # Consultas de servicios — palabras cortas pero válidas en este contexto
    "servicio", "servicios", "chasqui", "casilla", "casillas", "giro", "giros",
    "certificado", "ordinario", "correspondencia", "delivery",
}

SKILL_GENERIC_WORDS_BY_ID = {
    # "servicios" ya no es genérica — es una consulta válida directa al bot
    "historia_correos_bolivia": {"historia", "origen", "evolucion", "antecedentes"},
    "estado_plataforma": {"estado", "sistema", "skills", "capacidades"},
}

POSTAL_CONTEXT_HINTS = {
    "correos", "agbc", "postal", "postales", "envio", "envios", "guia", "tracking", "rastreo",
    "sucursal", "oficina", "filatelia", "reclamo", "queja", "ems", "encomienda", "paquete",
}

ROLE_OVERRIDE_PATTERNS = (
    "ahora eres", "olvida que eres", "actua como", "actúa como", "haz de cuenta que eres",
    "pretende ser", "finge ser", "desde ahora eres", "comportate como", "compórtate como",
)

GENERIC_TRIGGER_TERMS = {
    "info", "informacion", "información", "ayuda", "consulta", "consultas",
    "bot", "chatbot", "servicio", "servicios", "tema", "temas", "datos",
    "general", "soporte", "asistencia",
}
MIN_TRIGGER_TOKENS = 3
MIN_TRIGGER_WORDS = 4

SKILL_STORAGE_FIELDS = [
    "id",
    "nombre",
    "descripcion",
    "modo",
    "categoria",
    "prioridad",
    "trigger",
    "activa",
]

PDF_STORAGE_FIELDS = [
    "url",
    "archivo_local",
    "nombre_archivo",
    "tamano_bytes",
    "texto_extraido",
    "longitud_texto",
    "metodo_extraccion",
    "pagina_fuente",
    "subido_manual",
    "archivo_guardado",
    "content_hash",
    "clean_mode",
    "skill_id",
]

OUT_OF_SCOPE_SAMPLES = (
    "Esa pregunta está fuera de mi área. Soy el asistente de Correos de Bolivia y solo puedo ayudarte con: "
    "rastreo de envíos, tarifas, servicios postales, reclamos, sucursales, horarios y filatelia. "
    "¿Tienes alguna consulta sobre envíos o servicios de Correos Bolivia?"
)

# Respuestas de redirección por tema cercano
_OUT_OF_SCOPE_REDIRECTS = {
    # Geografía/país
    ("bolivia", "pais", "sudamerica", "america"): (
        "Soy el asistente de Correos de Bolivia. En Bolivia puedes enviar paquetes y cartas "
        "a cualquier parte del mundo a través de nuestros servicios. ¿Te ayudo con un envío?"
    ),
    # Gobierno/instituciones
    ("gobierno", "estado", "ministerio", "decreto"): (
        "Solo puedo ayudarte con temas de Correos de Bolivia. "
        "¿Necesitas información sobre envíos, tarifas o sucursales?"
    ),
    # Clima/geografía
    ("clima", "tiempo", "temperatura", "lluvia"): (
        "No tengo información sobre el clima. Soy el asistente de Correos de Bolivia. "
        "¿Puedo ayudarte con un envío o rastreo de paquete?"
    ),
    # Fútbol/deportes
    ("futbol", "partido", "deporte", "equipo"): (
        "Solo manejo temas postales. ¿Tienes algún paquete que rastrear o enviar?"
    ),
}


def out_of_scope_response(pregunta: str = "") -> str:
    """Devuelve respuesta de redirección amigable según el tema de la pregunta."""
    texto = pregunta.lower().strip() if pregunta else ""
    for palabras_clave, respuesta in _OUT_OF_SCOPE_REDIRECTS.items():
        if any(p in texto for p in palabras_clave):
            return respuesta
    return OUT_OF_SCOPE_SAMPLES


def _load_catalog(path: str, fallback: list[dict]) -> list[dict]:
    if not os.path.exists(path):
        return fallback
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            return data
    except Exception as exc:
        print(f"   Error leyendo catalogo {path}: {exc}")
    return fallback


def _save_catalog(path: str, data: list[dict]) -> list[dict]:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    return data


def _normalizar_match_text(texto: str | None) -> str:
    texto = (texto or "").strip().lower()
    texto = "".join(
        ch for ch in unicodedata.normalize("NFKD", texto)
        if not unicodedata.combining(ch)
    )
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def _to_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in ("false", "0", "no", "off", "")
    if value is None:
        return default
    return bool(value)


def _to_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _text_fingerprint(texto: str | None) -> str:
    base = _normalizar_match_text(texto or "")
    if not base:
        return ""
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


def _tokenizar_trigger(trigger: str) -> list[str]:
    tokens = []
    seen = set()
    for token in re.split(r"[,;|]", trigger or ""):
        limpio = _normalizar_match_text(token)
        if not limpio or limpio in seen:
            continue
        seen.add(limpio)
        tokens.append(limpio)
    return tokens


def _contains_whole_phrase(texto: str, phrase: str) -> bool:
    base = _normalizar_match_text(texto)
    target = _normalizar_match_text(phrase)
    if not base or not target:
        return False
    pattern = r"(?<![a-z0-9])" + r"\s+".join(re.escape(part) for part in target.split()) + r"(?![a-z0-9])"
    return re.search(pattern, base) is not None


def looks_like_role_override(pregunta: str) -> bool:
    texto = _normalizar_match_text(pregunta)
    if not texto:
        return False
    return any(_contains_whole_phrase(texto, pattern) for pattern in ROLE_OVERRIDE_PATTERNS)


def _validar_trigger(trigger: str) -> tuple[str, list[str]]:
    tokens = _tokenizar_trigger(trigger)
    if len(tokens) < MIN_TRIGGER_TOKENS:
        raise ValueError(
            f"trigger debe incluir al menos {MIN_TRIGGER_TOKENS} frases separadas por coma"
        )

    trigger_words = set()
    tokens_genericos = []
    for token in tokens:
        words = [w for w in token.split() if len(w) >= 4]
        if token in GENERIC_TRIGGER_TERMS and len(words) <= 1:
            tokens_genericos.append(token)
        trigger_words.update(words)

    if len(trigger_words) < MIN_TRIGGER_WORDS:
        raise ValueError(
            f"trigger debe incluir al menos {MIN_TRIGGER_WORDS} palabras utiles (de 4+ letras)"
        )

    if len(tokens_genericos) == len(tokens):
        raise ValueError(
            "trigger es demasiado genérico. Usa términos específicos del caso de uso (ej: rastreo, guía, seguimiento)."
        )

    normalized_trigger = ", ".join(tokens)
    return normalized_trigger, tokens_genericos


def listar_skills() -> list[dict]:
    raw_skills = _load_catalog(SKILLS_FILE, DEFAULT_SKILLS)
    sanitized, report = _sanitize_skills_catalog(raw_skills)
    if sanitized != raw_skills:
        _save_catalog(SKILLS_FILE, sanitized)
        observability.log_event(
            "catalog.skills_sanitized",
            dropped=report["dropped"],
            deduped=report["deduped"],
            total=len(sanitized),
        )
    skills = [_normalizar_skill(item) for item in sanitized]
    return sorted(
        skills,
        key=lambda item: (
            0 if item.get("activa", True) else 1,
            -(item.get("prioridad", 3) or 3),
            (item.get("nombre") or "").lower(),
        ),
    )


def listar_modos_skill() -> list[dict]:
    return [dict(item) for item in SUPPORTED_SKILL_MODES]


def listar_categorias_skill() -> list[dict]:
    return [dict(item) for item in SUPPORTED_SKILL_CATEGORIES]


def _normalizar_skill(item: dict) -> dict:
    skill = dict(item)
    skill["categoria"] = (skill.get("categoria") or "custom").strip()
    try:
        prioridad = int(skill.get("prioridad", 3))
    except (TypeError, ValueError):
        prioridad = 3
    skill["prioridad"] = min(max(prioridad, 1), 5)
    skill["trigger"] = (skill.get("trigger") or "").strip()
    activa = skill.get("activa", True)
    if isinstance(activa, str):
        activa = activa.strip().lower() not in ("false", "0", "no", "off", "")
    skill["activa"] = bool(activa)
    raw_tokens = _tokenizar_trigger(skill.get("trigger") or "")
    trigger_tokens = []
    trigger_words = set()
    for token in raw_tokens:
        limpio = _normalizar_match_text(token)
        if not limpio:
            continue
        trigger_tokens.append(limpio)
        for word in limpio.split():
            if len(word) >= 4:
                trigger_words.add(word)
    skill["trigger_tokens"] = trigger_tokens
    skill["trigger_words"] = sorted(trigger_words)
    if trigger_tokens:
        skill["trigger"] = ", ".join(trigger_tokens)
    return skill


def _skill_storage_record(item: dict) -> dict:
    normalized = _normalizar_skill(item)
    record = {
        "id": str(normalized.get("id") or "").strip(),
        "nombre": str(normalized.get("nombre") or "").strip(),
        "descripcion": str(normalized.get("descripcion") or "").strip(),
        "modo": str(normalized.get("modo") or "").strip(),
        "categoria": str(normalized.get("categoria") or "custom").strip() or "custom",
        "prioridad": _to_int(normalized.get("prioridad"), 3),
        "trigger": str(normalized.get("trigger") or "").strip(),
        "activa": _to_bool(normalized.get("activa", True), True),
    }
    record["prioridad"] = min(max(record["prioridad"], 1), 5)
    return record


def _pdf_storage_record(item: dict) -> dict:
    raw = dict(item or {})
    texto = raw.get("texto_extraido")
    if texto is not None:
        texto = str(texto).strip() or None
    archivo_local = str(raw.get("archivo_local") or "").replace("\\", os.sep).strip()
    nombre_archivo = str(raw.get("nombre_archivo") or "").strip()
    if not nombre_archivo and archivo_local:
        nombre_archivo = os.path.basename(archivo_local)
    longitud_texto = _to_int(raw.get("longitud_texto"), 0)
    if texto and longitud_texto <= 0:
        longitud_texto = len(texto)
    content_hash = _text_fingerprint(texto)
    clean_mode = _resolve_clean_mode(str(raw.get("clean_mode") or ""))
    return {
        "url": str(raw.get("url") or "").strip(),
        "archivo_local": archivo_local,
        "nombre_archivo": nombre_archivo,
        "tamano_bytes": max(_to_int(raw.get("tamano_bytes"), 0), 0),
        "texto_extraido": texto,
        "longitud_texto": max(longitud_texto, 0),
        "metodo_extraccion": (str(raw.get("metodo_extraccion")).strip() if raw.get("metodo_extraccion") else None),
        "pagina_fuente": str(raw.get("pagina_fuente") or "").strip(),
        "subido_manual": _to_bool(raw.get("subido_manual"), False),
        "archivo_guardado": _to_bool(raw.get("archivo_guardado"), False),
        "content_hash": content_hash or (str(raw.get("content_hash") or "").strip()),
        "clean_mode": clean_mode,
        "skill_id": str(raw.get("skill_id") or "").strip(),
    }


def _sanitize_skills_catalog(raw_items: list[dict]) -> tuple[list[dict], dict]:
    sanitized = []
    dropped = 0
    deduped = 0
    seen_ids = set()
    for item in raw_items:
        if not isinstance(item, dict):
            dropped += 1
            continue
        record = _skill_storage_record(item)
        if not record["id"] or not record["nombre"] or not record["descripcion"] or not record["modo"]:
            dropped += 1
            continue
        if record["id"] in seen_ids:
            deduped += 1
            continue
        seen_ids.add(record["id"])
        sanitized.append(record)
    return sanitized, {"dropped": dropped, "deduped": deduped}


def _sanitize_pdfs_catalog(raw_items: list[dict]) -> tuple[list[dict], dict]:
    sanitized = []
    dropped = 0
    deduped = 0
    seen_keys = set()
    seen_hashes = set()
    for item in raw_items:
        if not isinstance(item, dict):
            dropped += 1
            continue
        record = _pdf_storage_record(item)
        if not (
            record.get("nombre_archivo")
            or record.get("archivo_local")
            or record.get("url")
            or record.get("texto_extraido")
        ):
            dropped += 1
            continue
        key = (
            record.get("nombre_archivo") or "",
            record.get("url") or "",
            record.get("pagina_fuente") or "",
        )
        content_hash = record.get("content_hash") or ""
        if content_hash and content_hash in seen_hashes:
            deduped += 1
            continue
        if key in seen_keys:
            deduped += 1
            continue
        seen_keys.add(key)
        if content_hash:
            seen_hashes.add(content_hash)
        sanitized.append(record)
    return sanitized, {"dropped": dropped, "deduped": deduped}


def get_active_skills() -> list[dict]:
    return [item for item in listar_skills() if item.get("activa", True)]


# IDs de skills donde los datos numéricos deben ser exactos
# (códigos de rastreo, teléfonos, direcciones) — el guardia anti-inventado
# solo se aplica a estas. Para el resto, el LLM responde con datos del RAG
# que ya son válidos y el guardia genera demasiados falsos positivos.
_SKILLS_GUARDIA_NUMERICA = {"rastreo_envios", "oficinas_contacto"}


def skill_requiere_guardia_numerica(skill_id: str | None) -> bool:
    """Sin skills de tarifas, no se necesita guardia numerica."""
    return False


def resolve_skills_for_query(pregunta: str) -> dict:
    """
    Router simplificado: solo 3 reglas deterministicas.
    Todo lo demas → busqueda semantica en Qdrant (RAG).
    """
    # Siempre in_scope para Correos Bolivia
    return {
        "in_scope": True,
        "matched_skills": [],
        "primary_skill": None,
        "skill_ids": [],
    }


def build_skill_manifest(skills: list[dict] | None = None) -> str:
    return "Busqueda semantica unificada en Qdrant. Sin skills manuales."


def preferred_sources_for_skill(skill: dict | None) -> list[str]:
    """Sin skills manuales: buscar en todas las fuentes disponibles."""
    return ["pdf", "history", "json_data", "web_main", "section", "branch"]


def listar_pdfs() -> list[dict]:
    raw_pdfs = _load_catalog(PDFS_FILE, [])
    pdfs, report = _sanitize_pdfs_catalog(raw_pdfs)
    if pdfs != raw_pdfs:
        _save_catalog(PDFS_FILE, pdfs)
        observability.log_event(
            "catalog.pdfs_sanitized",
            dropped=report["dropped"],
            deduped=report["deduped"],
            total=len(pdfs),
        )
    salida = []
    for item in pdfs:
        pdf = dict(item)
        archivo_local = (pdf.get("archivo_local") or "").replace("\\", os.sep)
        nombre_archivo = pdf.get("nombre_archivo") or os.path.basename(archivo_local)
        ruta_real = archivo_local
        if archivo_local and not os.path.isabs(archivo_local):
            ruta_real = os.path.join(BASE_DIR, archivo_local)
        existe = bool(ruta_real and os.path.exists(ruta_real))
        longitud = pdf.get("longitud_texto") or 0
        if not longitud and pdf.get("texto_extraido"):
            longitud = len(pdf["texto_extraido"])
        pdf["nombre_archivo"] = nombre_archivo
        pdf["registro_id"] = _pdf_record_id(pdf)
        pdf["archivo_local"] = archivo_local
        pdf["archivo_existe"] = existe
        pdf["ruta_real"] = ruta_real if ruta_real else None
        pdf["texto_disponible"] = bool(pdf.get("texto_extraido"))
        pdf["longitud_texto"] = longitud
        pdf["estado_extraccion"] = "ok" if pdf["texto_disponible"] else "sin_texto"
        salida.append(pdf)
    return salida


def resumen_pdfs() -> dict:
    pdfs = listar_pdfs()
    return {
        "total": len(pdfs),
        "con_texto": sum(1 for item in pdfs if item["texto_disponible"]),
        "sin_texto": sum(1 for item in pdfs if not item["texto_disponible"]),
        "archivos_presentes": sum(1 for item in pdfs if item["archivo_existe"]),
        "tamano_directorio_kb": _dir_size_kb(PDF_DIR),
        "pdfs_file": _file_stats(PDFS_FILE),
        "pdf_dir": _file_stats(PDF_DIR),
    }


def _managed_data_json_paths() -> list[str]:
    if not os.path.isdir(DATA_DIR):
        return []
    paths = []
    for name in sorted(os.listdir(DATA_DIR)):
        if not name.endswith(".json"):
            continue
        if name in EXCLUDED_MANAGED_JSON_FILES:
            continue
        paths.append(os.path.join(DATA_DIR, name))
    return paths


def _safe_data_json_path(nombre_archivo: str) -> str:
    filename = os.path.basename((nombre_archivo or "").strip())
    if not filename.endswith(".json"):
        raise ValueError("El archivo debe tener extensión .json")
    if filename in EXCLUDED_MANAGED_JSON_FILES:
        raise ValueError(f"{filename} se administra por su módulo específico")
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        raise FileNotFoundError("Archivo JSON no encontrado")
    return path


def listar_data_jsons() -> list[dict]:
    salida: list[dict] = []
    for path in _managed_data_json_paths():
        nombre = os.path.basename(path)
        info = {
            "nombre_archivo": nombre,
            "ruta": path,
            "tamano_bytes": os.path.getsize(path) if os.path.exists(path) else 0,
            "modificado_en": datetime.fromtimestamp(os.path.getmtime(path)).isoformat() if os.path.exists(path) else None,
            "estado": "ok",
            "tipo": "unknown",
            "entradas": 0,
        }
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, list):
                info["tipo"] = "array"
                info["entradas"] = len(data)
            elif isinstance(data, dict):
                info["tipo"] = "object"
                info["entradas"] = len(data)
            else:
                info["tipo"] = type(data).__name__
                info["entradas"] = 1
        except Exception:
            info["estado"] = "error"
            info["tipo"] = "invalid_json"
            info["entradas"] = 0
        salida.append(info)
    return salida


def resumen_data_jsons() -> dict:
    items = listar_data_jsons()
    total_bytes = sum(int(item.get("tamano_bytes") or 0) for item in items)
    return {
        "total": len(items),
        "validos": sum(1 for item in items if item.get("estado") == "ok"),
        "invalidos": sum(1 for item in items if item.get("estado") != "ok"),
        "total_entradas": sum(int(item.get("entradas") or 0) for item in items),
        "tamano_total_kb": round(total_bytes / 1024, 2) if total_bytes else 0,
    }


def obtener_data_json(nombre_archivo: str) -> dict:
    path = _safe_data_json_path(nombre_archivo)
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    # Extraer _skill_id si existe (metadata opcional del JSON)
    skill_id = ""
    content_display = data
    if isinstance(data, dict):
        skill_id = str(data.pop("_skill_id", "")).strip()
        content_display = {k: v for k, v in data.items() if k != "_skill_id"}
    return {
        "nombre_archivo": os.path.basename(path),
        "ruta": path,
        "tamano_bytes": os.path.getsize(path),
        "modificado_en": datetime.fromtimestamp(os.path.getmtime(path)).isoformat(),
        "content": content_display,
        "content_pretty": json.dumps(content_display, ensure_ascii=False, indent=2),
        "skill_id": skill_id,
    }


def actualizar_data_json(nombre_archivo: str, content, skill_id: str = None) -> dict:
    path = _safe_data_json_path(nombre_archivo)
    parsed = content
    if isinstance(content, str):
        parsed = json.loads(content)
    if not isinstance(parsed, (dict, list)):
        raise ValueError("El contenido JSON debe ser objeto o arreglo")
    # Guardar _skill_id como metadata dentro del JSON si se proporciona
    if skill_id and isinstance(parsed, dict):
        parsed["_skill_id"] = skill_id
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(parsed, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return obtener_data_json(os.path.basename(path))


def _dir_size_kb(path: str) -> float:
    total = 0
    if os.path.isdir(path):
        for root, _, files in os.walk(path):
            for name in files:
                full = os.path.join(root, name)
                if os.path.isfile(full):
                    total += os.path.getsize(full)
    return round(total / 1024, 2) if total else 0


def get_scraping_summary() -> dict:
    stats = _load_catalog(SCRAPER_STATS_FILE, {}) if SCRAPER_STATS_FILE.endswith(".json") else {}
    if not isinstance(stats, dict):
        stats = {}
    paginas_exitosas = int(stats.get("paginas_exitosas", 0) or 0)
    paginas_fallidas = int(stats.get("paginas_fallidas", 0) or 0)
    paginas_totales = paginas_exitosas + paginas_fallidas
    extraction_success_rate = round((paginas_exitosas / paginas_totales) * 100, 2) if paginas_totales else 0.0

    aplicativos_raw = _load_catalog(SCRAPER_APLICATIVOS_FILE, {})
    servicios_raw = _load_catalog(SCRAPER_SERVICIOS_FILE, {})
    historia_raw = _load_catalog(SCRAPER_HISTORIA_FILE, [])
    noticias_raw = _load_catalog(SCRAPER_NOTICIAS_FILE, [])
    secciones_raw = _load_catalog(SCRAPER_SECCIONES_FILE, {})
    sucursales_raw = _load_catalog(SCRAPER_SUCURSALES_FILE, [])

    aplicativos_detalle = aplicativos_raw.get("detalle", []) if isinstance(aplicativos_raw, dict) else []
    aplicativos_resumen = aplicativos_raw.get("resumen", []) if isinstance(aplicativos_raw, dict) else []
    servicios = servicios_raw.get("servicios", []) if isinstance(servicios_raw, dict) else []
    aplicaciones = servicios_raw.get("aplicaciones", []) if isinstance(servicios_raw, dict) else []
    herramientas = servicios_raw.get("herramientas", []) if isinstance(servicios_raw, dict) else []
    enlaces_externos = servicios_raw.get("enlaces_externos", []) if isinstance(servicios_raw, dict) else []

    return {
        "stats": stats,
        "counts": {
            "paginas_exitosas": paginas_exitosas,
            "paginas_fallidas": paginas_fallidas,
            "paginas_totales": paginas_totales,
            "extraction_success_rate": extraction_success_rate,
            "caracteres_extraidos": stats.get("caracteres_extraidos", 0),
            "sucursales": len(sucursales_raw) if isinstance(sucursales_raw, list) else 0,
            "secciones": len(secciones_raw) if isinstance(secciones_raw, dict) else 0,
            "aplicativos": len(aplicativos_detalle),
            "aplicativos_resumen": len(aplicativos_resumen),
            "servicios": len(servicios),
            "aplicaciones": len(aplicaciones),
            "herramientas": len(herramientas),
            "noticias": len(noticias_raw) if isinstance(noticias_raw, list) else 0,
            "historia_items": len(historia_raw) if isinstance(historia_raw, list) else 0,
            "enlaces_externos": len(enlaces_externos),
            "pdfs": len(_load_catalog(PDFS_FILE, [])),
        },
        "samples": {
            "secciones": list(secciones_raw.keys())[:8] if isinstance(secciones_raw, dict) else [],
            "aplicativos": [
                item.get("nombre", "")
                for item in aplicativos_resumen[:8]
                if isinstance(item, dict)
            ],
            "servicios": [
                item.get("nombre", "")
                for item in servicios[:8]
                if isinstance(item, dict)
            ],
            "noticias": [
                item.get("titulo", "")
                for item in noticias_raw[:6]
                if isinstance(item, dict)
            ],
        },
        "files": {
            "estadisticas": _file_stats(SCRAPER_STATS_FILE),
            "aplicativos": _file_stats(SCRAPER_APLICATIVOS_FILE),
            "servicios": _file_stats(SCRAPER_SERVICIOS_FILE),
            "historia": _file_stats(SCRAPER_HISTORIA_FILE),
            "noticias": _file_stats(SCRAPER_NOTICIAS_FILE),
            "secciones": _file_stats(SCRAPER_SECCIONES_FILE),
            "sucursales": _file_stats(SCRAPER_SUCURSALES_FILE),
        },
        "observability": observability.get_observability_snapshot().get("extraction", {}),
    }


def resumen_rag(chunks: int, embedding_model: str, chroma_path: str) -> dict:
    return {
        "activo": chunks > 0,
        "chunks": chunks,
        "embedding_model": embedding_model,
        "chroma_path": chroma_path,
    }


def get_runtime_capabilities(
    *,
    chunks: int,
    embedding_model: str,
    chroma_path: str,
    ollama_ok: bool,
    modelo: str,
    sesiones_activas: int,
    sucursales: list[dict],
    actualizacion: dict,
) -> dict:
    rag = resumen_rag(chunks=chunks, embedding_model=embedding_model, chroma_path=chroma_path)
    skills = []
    for skill in listar_skills():
        item = dict(skill)
        item["estado"] = "activa" if item.get("activa", True) else "inactiva"
        item["supported_mode"] = item.get("modo") in SUPPORTED_SKILL_MODE_IDS
        item["supported_category"] = item.get("categoria") in SUPPORTED_SKILL_CATEGORY_IDS
        item["automatizable"] = item.get("modo") in {"rag+llm", "translation", "internal"}
        skills.append(item)

    skills_summary = {
        "total": len(skills),
        "activas": sum(1 for item in skills if item.get("estado") == "activa"),
        "categorias": {},
    }
    for item in skills:
        cat = item.get("categoria", "custom")
        skills_summary["categorias"][cat] = skills_summary["categorias"].get(cat, 0) + 1

    return {
        "skills": skills,
        "skills_summary": skills_summary,
        "rag": rag,
        "runtime": {
            "ollama": ollama_ok,
            "modelo": modelo,
            "sesiones_activas": sesiones_activas,
            "sucursales": len(sucursales),
            "sucursales_con_coords": sum(1 for s in sucursales if s.get("lat") and s.get("lng")),
            "actualizacion": actualizacion,
        },
        "ai_resources": {
            "llm": {
                "modelo": modelo,
                "ollama_disponible": ollama_ok,
                "timeout_segundos": int(os.environ.get("OLLAMA_TIMEOUT", "600")),
            },
            "embeddings": {
                "modelo": embedding_model,
                "chunk_size": int(os.environ.get("CHUNK_SIZE", "600")),
                "batch_size": int(os.environ.get("BATCH_SIZE", "500")),
                "n_resultados": int(os.environ.get("N_RESULTADOS", "3")),
            },
            "session": {
                "max_historial": int(os.environ.get("MAX_HISTORIAL", "6")),
                "sesiones_activas": sesiones_activas,
            },
            "storage": {
                "chroma_path": _file_stats(chroma_path),
                "skills_file": _file_stats(SKILLS_FILE),
                "pdfs_file": _file_stats(PDFS_FILE),
                "pdf_dir": _file_stats(PDF_DIR),
                "data_file": _file_stats(os.environ.get("DATA_FILE", "data/correos_bolivia.txt")),
                "sucursales_file": _file_stats(os.environ.get("SUCURSALES_FILE", "data/sucursales_contacto.json")),
                "secciones_file": _file_stats(os.environ.get("SECCIONES_FILE", "data/secciones_home.json")),
            },
            "capabilities": {
                "modos_skill_soportados": listar_modos_skill(),
                "skills_registradas": len(skills),
            },
            "pdfs": resumen_pdfs(),
        },
    }


def detectar_codigo_seguimiento(pregunta: str) -> str | None:
    """Detecta códigos de seguimiento bolivianos (terminan en BO) o internacionales."""
    import re
    
    texto = (pregunta or "").strip().upper()
    if not texto:
        return None
    
    # Patrones de códigos de seguimiento (de más específico a más general)
    patrones = [
        # Formato boliviano real: letra + dígitos + letra(s) + dígitos + BO
        # Ejemplos válidos: C0028A03441BO, C0007A02018BO, R123456789BO
        # Debe tener al menos un dígito antes del BO
        r'[A-Z]\d+[A-Z]\d+BO',                # C0028A03441BO (más común)
        r'[A-Z]\d{6,}BO',                      # R123456789BO
        r'\d{4,}[A-Z]\d+BO',                   # 0028A03441BO (sin letra inicial)
        # Formato internacional XX123456789XX (2 letras + 9 dígitos + 2 letras)
        r'[A-Z]{2}\d{9}[A-Z]{2}',              # ES123456789CN
        # Solo números (12-14 dígitos) — códigos numéricos puros
        r'\b\d{12,14}\b',
    ]
    
    for patron in patrones:
        match = re.search(patron, texto)
        if match:
            codigo = match.group(0)
            print(f"[TRACKING] Código detectado: {codigo}")
            return codigo
    
    print(f"[TRACKING] No se detectó código en: {texto[:50]}")
    return None


# Test al importar
if __name__ == "__main__":
    # Probar con el código del usuario
    test_codigo = "C0007A02018BO"
    resultado = detectar_codigo_seguimiento(test_codigo)
    print(f"Test '{test_codigo}': {resultado}")


def detectar_consulta_especial(pregunta: str) -> str | None:
    texto = _normalizar_match_text(pregunta)
    if not texto:
        return None

    # Detectar código de seguimiento primero
    codigo = detectar_codigo_seguimiento(pregunta)
    if codigo:
        print(f"[CONSULTA_ESPECIAL] Detectado tracking con código: {codigo}")
        return "tracking"

    # Bloquear consultas de introspección técnica interna:
    # "skills internas", "skills cargadas", "skills en memoria", etc.
    # Estas revelan arquitectura interna y no aportan valor al usuario final.
    _INTROSPECTION_PATTERNS = (
        "skills internas", "skills cargadas", "skills en memoria",
        "skills del sistema", "skills del bot", "todas las skills",
        "lista de skills", "cuantas skills", "cuántas skills",
        "skills de sistema", "dame los skills", "dame las skills",
        "cuales son las skills", "cuáles son las skills",
        "rag", "chroma", "embeddings", "chunks", "base vectorial",
        "estado del sistema", "status del sistema", "estado bot", "estado del bot",
        "sucursales cargadas", "resumen de sucursales", "estado de sucursales",
    )
    if any(_contains_whole_phrase(texto, token) for token in _INTROSPECTION_PATTERNS):
        return "capacidades_usuario"

    # "skills" o "habilidades" sin contexto de introspección → también redirigir
    if any(_contains_whole_phrase(texto, token) for token in ("skill", "skills", "habilidad", "habilidades")):
        return "capacidades_usuario"

    if any(_contains_whole_phrase(texto, token) for token in ("que puedes hacer", "capacidades del bot", "que sabes hacer")):
        return "capacidades_usuario"

    return None


def _render_skills(skills: list[dict]) -> str:
    listado = "\n".join(
        (
            f"- {item.get('nombre', 'Skill')} "
            f"[{item.get('categoria', 'custom')} | prioridad {item.get('prioridad', 3)} | {item.get('estado', 'activa')}] "
            f": {item.get('descripcion', 'Sin descripcion')}"
        )
        for item in skills
    )
    return (
        f"Skills configuradas: {len(skills)}.\n"
        f"{listado}\n"
        "Las skills se aplican dentro del flujo del bot para conversar, traducir, operar el sistema y organizar respuestas por prioridad."
    )


def render_generar(runtime_capabilities: dict) -> str:
    return (
        "Puedo generar respuestas usando el modelo local y el RAG institucional.\n"
        f"Skills activas: {runtime_capabilities['skills_summary']['activas']} de {runtime_capabilities['skills_summary']['total']}. "
        f"Chunks RAG: {runtime_capabilities['rag']['chunks']}.\n"
        "Respondo mejor si la pregunta está dentro del dominio postal de Correos de Bolivia."
    )


def guardar_skill(payload: dict) -> dict:
    skill_id = (payload.get("id") or "").strip()
    nombre = (payload.get("nombre") or "").strip()
    descripcion = (payload.get("descripcion") or "").strip()
    modo = (payload.get("modo") or "").strip()
    categoria = (payload.get("categoria") or "custom").strip()
    trigger = (payload.get("trigger") or "").strip()
    activa = payload.get("activa", True)
    prioridad_raw = payload.get("prioridad", 3)

    if not skill_id or not nombre or not descripcion or not modo:
        raise ValueError("id, nombre, descripcion y modo son obligatorios")
    if categoria not in SUPPORTED_SKILL_CATEGORY_IDS:
        raise ValueError("categoria no soportada")
    try:
        prioridad = int(prioridad_raw)
    except (TypeError, ValueError):
        raise ValueError("prioridad debe ser numérica")
    if prioridad < 1 or prioridad > 5:
        raise ValueError("prioridad debe estar entre 1 y 5")
    if isinstance(activa, str):
        activa = activa.strip().lower() not in ("false", "0", "no", "off", "")
    trigger_normalizado, tokens_genericos = _validar_trigger(trigger)
    if tokens_genericos:
        observability.log_event(
            "skills.trigger_generic_terms_detected",
            skill_id=skill_id,
            generic_terms=tokens_genericos,
        )

    skills = listar_skills()
    nuevo = _normalizar_skill({
        "id": skill_id,
        "nombre": nombre,
        "descripcion": descripcion,
        "modo": modo,
        "categoria": categoria,
        "prioridad": prioridad,
        "trigger": trigger_normalizado,
        "activa": bool(activa),
    })

    replaced = False
    for idx, item in enumerate(skills):
        if item.get("id") == skill_id:
            skills[idx] = nuevo
            replaced = True
            break
    if not replaced:
        skills.append(nuevo)
    skills_storage = [_skill_storage_record(item) for item in skills]
    _save_catalog(SKILLS_FILE, skills_storage)
    return {"skill": nuevo, "created": not replaced}


def eliminar_skill(skill_id: str) -> bool:
    skills = listar_skills()
    filtrados = [item for item in skills if item.get("id") != skill_id]
    if len(filtrados) == len(skills):
        return False
    _save_catalog(SKILLS_FILE, [_skill_storage_record(item) for item in filtrados])
    return True


def management_options() -> dict:
    return {
        "modos_skill": listar_modos_skill(),
        "categorias_skill": listar_categorias_skill(),
        "modos_skill_ids": sorted(SUPPORTED_SKILL_MODE_IDS),
        "categorias_skill_ids": sorted(SUPPORTED_SKILL_CATEGORY_IDS),
        "schemas": {
            "skills_storage_fields": SKILL_STORAGE_FIELDS,
            "pdfs_storage_fields": PDF_STORAGE_FIELDS,
        },
        "pdf_cleaning": {
            "default_mode": _resolve_clean_mode(PDF_CLEAN_MODE_DEFAULT),
            "modes": sorted(PDF_CLEAN_MODES),
        },
        "trigger_guidelines": {
            "min_tokens": MIN_TRIGGER_TOKENS,
            "min_words": MIN_TRIGGER_WORDS,
            "avoid_terms": sorted(GENERIC_TRIGGER_TERMS),
            "example": "rastreo, seguimiento de envio, codigo de guia",
        },
    }


def guardar_pdf_subido(
    file_storage,
    fuente_url: str = "",
    pagina_fuente: str = "",
    clean_mode: str | None = None,
    skill_id: str = "",
    texto_frontend: str = "",
) -> dict:
    if file_storage is None or not getattr(file_storage, "filename", ""):
        raise ValueError("Debes seleccionar un archivo PDF")

    nombre_archivo = _sanitize_filename(file_storage.filename)
    os.makedirs(PDF_DIR, exist_ok=True)
    ruta_real = os.path.join(PDF_DIR, nombre_archivo)

    if hasattr(file_storage, "save"):
        file_storage.save(ruta_real)
    else:
        file_obj = getattr(file_storage, "file", file_storage)
        try:
            file_obj.seek(0)
        except Exception:
            pass
        with open(ruta_real, "wb") as out:
            shutil.copyfileobj(file_obj, out)

    clean_mode_resolved = _resolve_clean_mode(clean_mode)

    try:
        # Si el frontend ya extrajo el texto (pdf.js), usarlo directamente
        if (texto_frontend or "").strip():
            texto = texto_frontend.strip()
            metodo = "pdfjs_frontend"
        else:
            texto, metodo = extraer_texto_pdf(ruta_real, clean_mode=clean_mode_resolved)
        tamano_bytes = os.path.getsize(ruta_real) if os.path.exists(ruta_real) else 0
        observability.record_extraction(
            kind="pdf_upload",
            success=bool(texto),
            method=metodo,
            chars=len(texto) if texto else 0,
            reason="" if texto else "sin_texto",
        )
    finally:
        try:
            if os.path.exists(ruta_real):
                os.remove(ruta_real)
        except OSError as exc:
            print(f"   Error eliminando PDF temporal subido: {exc}")

    pdfs = [_clean_pdf_entry(item) for item in listar_pdfs()]
    registro = {
        "url": (fuente_url or "").strip(),
        "archivo_local": "",
        "nombre_archivo": nombre_archivo,
        "tamano_bytes": tamano_bytes,
        "texto_extraido": texto,
        "longitud_texto": len(texto) if texto else 0,
        "metodo_extraccion": metodo,
        "pagina_fuente": (pagina_fuente or "").strip(),
        "subido_manual": True,
        "archivo_guardado": False,
        "clean_mode": clean_mode_resolved,
        "skill_id": (skill_id or "").strip(),
    }

    replaced = False
    for idx, item in enumerate(pdfs):
        if item.get("nombre_archivo") == nombre_archivo:
            pdfs[idx] = registro
            replaced = True
            break
    if not replaced:
        pdfs.append(registro)

    _save_catalog(PDFS_FILE, [_pdf_storage_record(item) for item in pdfs])
    salida = dict(registro)
    salida["archivo_existe"] = False
    salida["texto_disponible"] = bool(texto)
    salida["estado_extraccion"] = "ok" if texto else "sin_texto"
    return {"ok": True, "created": not replaced, "pdf": salida}


def reprocesar_pdf(nombre_archivo: str) -> dict:
    pdfs = [_clean_pdf_entry(item) for item in listar_pdfs()]
    objetivo = None
    for idx, item in enumerate(pdfs):
        if item.get("nombre_archivo") == nombre_archivo:
            objetivo = (idx, item)
            break

    if objetivo is None:
        raise FileNotFoundError("PDF no encontrado")

    idx, registro = objetivo
    ruta_real = registro.get("archivo_local") or os.path.join(PDF_DIR, nombre_archivo)
    if ruta_real and not os.path.isabs(ruta_real):
        ruta_real = os.path.join(BASE_DIR, ruta_real)
    if not ruta_real or not os.path.exists(ruta_real):
        raise FileNotFoundError("El archivo físico del PDF no existe")

    clean_mode = _resolve_clean_mode(registro.get("clean_mode"))
    texto, metodo = extraer_texto_pdf(ruta_real, clean_mode=clean_mode)
    observability.record_extraction(
        kind="pdf_reprocess_single",
        success=bool(texto),
        method=metodo,
        chars=len(texto) if texto else 0,
        reason="" if texto else "sin_texto",
    )
    registro["archivo_local"] = ruta_real
    registro["texto_extraido"] = texto
    registro["longitud_texto"] = len(texto) if texto else 0
    registro["metodo_extraccion"] = metodo
    registro["clean_mode"] = clean_mode
    pdfs[idx] = registro
    _save_catalog(PDFS_FILE, [_pdf_storage_record(item) for item in pdfs])

    salida = dict(registro)
    salida["archivo_existe"] = True
    salida["texto_disponible"] = bool(texto)
    salida["estado_extraccion"] = "ok" if texto else "sin_texto"
    salida["ruta_real"] = ruta_real
    return {"ok": True, "pdf": salida}


def reprocesar_pdfs_pendientes(force: bool = False) -> dict:
    """
    Reprocesa PDFs con extracción antigua, vacía o demasiado pobre.
    Se usa especialmente al arrancar o reindexar dentro del contenedor.
    """
    pdfs = [_clean_pdf_entry(item) for item in listar_pdfs()]
    if not pdfs:
        return {"ok": True, "total": 0, "reprocesados": 0, "mejorados": 0, "fallidos": 0}

    reprocesados = 0
    mejorados = 0
    fallidos = 0
    actualizados = []

    for item in pdfs:
        registro = dict(item)
        nombre_archivo = registro.get("nombre_archivo") or os.path.basename(registro.get("archivo_local", ""))
        ruta_real = registro.get("archivo_local") or os.path.join(PDF_DIR, nombre_archivo)
        if ruta_real and not os.path.isabs(ruta_real):
            ruta_real = os.path.join(BASE_DIR, ruta_real)

        texto_actual = registro.get("texto_extraido") or ""
        metodo_actual = registro.get("metodo_extraccion")
        necesita_reproceso = force or not metodo_actual or len(texto_actual.strip()) < PDF_REPROCESS_MIN_TEXT

        if not necesita_reproceso:
            actualizados.append(registro)
            continue

        if not ruta_real or not os.path.exists(ruta_real):
            fallidos += 1
            observability.record_extraction(
                kind="pdf_reprocess_batch",
                success=False,
                reason="archivo_no_existe",
            )
            actualizados.append(registro)
            continue

        clean_mode = _resolve_clean_mode(registro.get("clean_mode"))
        texto_nuevo, metodo_nuevo = extraer_texto_pdf(ruta_real, clean_mode=clean_mode)
        reprocesados += 1
        observability.record_extraction(
            kind="pdf_reprocess_batch",
            success=bool(texto_nuevo),
            method=metodo_nuevo,
            chars=len(texto_nuevo) if texto_nuevo else 0,
            reason="" if texto_nuevo else "sin_texto",
        )

        if texto_nuevo and len(texto_nuevo) > len(texto_actual):
            mejorados += 1

        registro["archivo_local"] = ruta_real
        registro["texto_extraido"] = texto_nuevo
        registro["longitud_texto"] = len(texto_nuevo) if texto_nuevo else 0
        registro["metodo_extraccion"] = metodo_nuevo
        registro["clean_mode"] = clean_mode
        actualizados.append(registro)

    _save_catalog(PDFS_FILE, [_pdf_storage_record(item) for item in actualizados])
    return {
        "ok": True,
        "total": len(pdfs),
        "reprocesados": reprocesados,
        "mejorados": mejorados,
        "fallidos": fallidos,
    }


def eliminar_pdf(nombre_archivo: str) -> dict:
    pdfs = listar_pdfs()
    objetivo = None
    restantes = []
    for item in pdfs:
        if item.get("registro_id") == nombre_archivo or item.get("nombre_archivo") == nombre_archivo:
            objetivo = item
            continue
        limpio = _clean_pdf_entry(item)
        restantes.append(limpio)

    if objetivo is None:
        raise FileNotFoundError("PDF no encontrado")

    _save_catalog(PDFS_FILE, restantes)

    eliminado_archivo = False
    ruta_real = objetivo.get("ruta_real")
    if ruta_real and os.path.exists(ruta_real):
        os.remove(ruta_real)
        eliminado_archivo = True

    return {
        "ok": True,
        "nombre_archivo": nombre_archivo,
        "archivo_eliminado": eliminado_archivo,
        "registro_eliminado": True,
    }


def actualizar_texto_pdf(nombre_archivo: str, texto_extraido: str | None, skill_id: str = "") -> dict:
    """
    Actualiza manualmente el texto extraído y/o el skill vinculado de un PDF ya registrado.
    `nombre_archivo` puede ser nombre real o `registro_id`.
    """
    pdfs = listar_pdfs()
    objetivo = None
    actualizados = []
    texto_normalizado = (texto_extraido or "").strip() or None
    skill_id_normalizado = (skill_id or "").strip()

    for item in pdfs:
        if item.get("registro_id") == nombre_archivo or item.get("nombre_archivo") == nombre_archivo:
            objetivo = dict(item)
            limpio = _clean_pdf_entry(item)
            limpio["texto_extraido"] = texto_normalizado
            limpio["longitud_texto"] = len(texto_normalizado) if texto_normalizado else 0
            limpio["metodo_extraccion"] = "manual_edit"
            limpio["skill_id"] = skill_id_normalizado
            actualizados.append(limpio)
            continue
        actualizados.append(_clean_pdf_entry(item))

    if objetivo is None:
        raise FileNotFoundError("PDF no encontrado")

    _save_catalog(PDFS_FILE, [_pdf_storage_record(item) for item in actualizados])

    # devolver registro actualizado
    refreshed = listar_pdfs()
    registro = next(
        (
            item
            for item in refreshed
            if item.get("registro_id") == nombre_archivo or item.get("nombre_archivo") == nombre_archivo
        ),
        None,
    )
    if registro is None:
        raise RuntimeError("No se pudo recuperar el PDF actualizado")

    observability.record_extraction(
        kind="pdf_manual_edit",
        success=bool(registro.get("texto_extraido")),
        method="manual_edit",
        chars=int(registro.get("longitud_texto") or 0),
        reason="" if registro.get("texto_extraido") else "sin_texto",
    )
    return {"ok": True, "pdf": registro}


def execute_special_query(tipo: str, runtime_capabilities: dict, pregunta: str = "") -> dict:
    if tipo == "capacidades_usuario":
        respuesta = (
            "Soy ChatbotBO, el asistente virtual de Correos de Bolivia. Puedo ayudarte con:\n"
            "• Rastreo de envíos — consulta el estado de tu paquete con tu código de seguimiento.\n"
            "• Tarifas — cotiza el costo de envíos nacionales e internacionales.\n"
            "• Sucursales y horarios — encuentra oficinas, direcciones y horarios de atención.\n"
            "• Servicios postales — EMS, Encomienda, Correo Prioritario, ChasquiExpressBO y más.\n"
            "• Reclamos y quejas — orienta sobre cómo reportar incidencias o paquetes perdidos.\n"
            "• Filatelia — información sobre sellos de colección bolivianos.\n"
            "• Historia institucional — antecedentes y evolución de Correos de Bolivia.\n\n"
            "¿En qué puedo ayudarte hoy?"
        )
        return {"kind": "capacidades_usuario", "payload": {}, "response": respuesta}
    if tipo == "skills":
        # Redirigir al mismo handler de usuario (no exponer arquitectura interna)
        return execute_special_query("capacidades_usuario", runtime_capabilities, pregunta)
    if tipo == "generar":
        return {
            "kind": "summary",
            "payload": {
                "skills": len(runtime_capabilities["skills"]),
                "chunks": runtime_capabilities["rag"]["chunks"],
            },
            "response": render_generar(runtime_capabilities),
        }
    if tipo == "rag_local":
        result = _rag_local_summary(runtime_capabilities)
        return {"kind": "rag", "payload": result, "response": result["text"]}
    if tipo == "system_status":
        result = _system_status_summary(runtime_capabilities)
        return {"kind": "status", "payload": result, "response": result["text"]}
    if tipo == "branches_summary":
        result = _branches_summary(runtime_capabilities)
        return {"kind": "branches", "payload": result, "response": result["text"]}
    if tipo == "tracking":
        codigo = detectar_codigo_seguimiento(pregunta)
        url_tracking = f"{contacto.tracking_url()}/search?tracking={codigo}"
        return {
            "kind": "tracking",
            "payload": {"codigo": codigo, "url": url_tracking},
            "response": f"Detecté el código de seguimiento: **{codigo}**\n\nPuedes consultar el estado de tu envío en:\n🔗 {url_tracking}\n\nSi prefieres, puedo ayudarte a interpretar la información una vez que accedas al enlace.",
        }
    raise ValueError(f"Consulta especial no soportada: {tipo}")


def _rag_local_summary(runtime_capabilities: dict) -> dict:
    rag = runtime_capabilities["rag"]
    runtime = runtime_capabilities["runtime"]
    estado = "activo" if rag["activo"] else "sin indexacion"
    text = (
        f"Estado RAG: {estado}.\n"
        f"Chunks indexados: {rag['chunks']}.\n"
        f"Modelo de embeddings: {rag['embedding_model']}.\n"
        f"Base vectorial: {rag['chroma_path']}.\n"
        f"Modelo generativo: {runtime['modelo']}.\n"
        f"Ollama disponible: {'si' if runtime['ollama'] else 'no'}."
    )
    return {"ok": True, "data": rag, "text": text}


def _system_status_summary(runtime_capabilities: dict) -> dict:
    runtime = runtime_capabilities["runtime"]
    act = runtime["actualizacion"]
    text = (
        "Estado del sistema:\n"
        f"Modelo: {runtime['modelo']}.\n"
        f"Ollama: {'disponible' if runtime['ollama'] else 'no disponible'}.\n"
        f"Sesiones activas: {runtime['sesiones_activas']}.\n"
        f"Actualizacion en proceso: {'si' if act['en_proceso'] else 'no'}.\n"
        f"Ultimo resultado: {act['ultimo_resultado']}."
    )
    return {"ok": True, "data": runtime, "text": text}


def _branches_summary(runtime_capabilities: dict) -> dict:
    runtime = runtime_capabilities["runtime"]
    text = (
        "Resumen de sucursales:\n"
        f"Sucursales cargadas: {runtime['sucursales']}.\n"
        f"Con coordenadas: {runtime['sucursales_con_coords']}.\n"
        f"Sin coordenadas: {runtime['sucursales'] - runtime['sucursales_con_coords']}."
    )
    return {
        "ok": True,
        "data": {
            "sucursales": runtime["sucursales"],
            "sucursales_con_coords": runtime["sucursales_con_coords"],
        },
        "text": text,
    }
