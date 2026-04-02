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

try:
    import pdfplumber
    _PDFPLUMBER_AVAILABLE = True
except ImportError:
    pdfplumber = None  # type: ignore
    _PDFPLUMBER_AVAILABLE = False

try:
    import PyPDF2
    _PYPDF2_AVAILABLE = True
except ImportError:
    PyPDF2 = None  # type: ignore
    _PYPDF2_AVAILABLE = False

try:
    import pytesseract
    from pdf2image import convert_from_path
    _OCR_AVAILABLE = True
except ImportError:
    pytesseract = None  # type: ignore
    convert_from_path = None  # type: ignore
    _OCR_AVAILABLE = False


DEFAULT_SKILLS = [
    {
        "id": "rastreo_envios",
        "nombre": "Rastreo de envíos",
        "descripcion": "Atiende consultas sobre seguimiento, estado y trazabilidad de envíos postales.",
        "modo": "rag+llm",
        "categoria": "atencion",
        "prioridad": 5,
        "trigger": "rastreo, seguimiento, track, tracking, guia, código de envío, estado de envío, paquete",
        "activa": True,
    },
    {
        "id": "calculadora_tarifas",
        "nombre": "Calculadora de tarifas",
        "descripcion": "Responde sobre tarifas, precios, costos, pesos y referencias de cobro de servicios postales.",
        "modo": "rag+llm",
        "categoria": "atencion",
        "prioridad": 5,
        "trigger": "tarifa, tarifas, precio, precios, costo, costos, cotización, cuanto cuesta, peso, envío internacional",
        "activa": True,
    },
    {
        "id": "servicios_correos",
        "nombre": "Servicios de Correos de Bolivia",
        "descripcion": "Explica servicios, características, coberturas, modalidades y condiciones operativas de AGBC.",
        "modo": "rag+llm",
        "categoria": "atencion",
        "prioridad": 5,
        "trigger": "servicio, servicios, ems, certificado, ordinario, express mail service, giros, encomienda, paquetería",
        "activa": True,
    },
    {
        "id": "guia_envio_correcto",
        "nombre": "Cómo enviar correctamente",
        "descripcion": "Guía paso a paso para preparar, embalar, rotular y enviar documentos o paquetes correctamente.",
        "modo": "rag+llm",
        "categoria": "atencion",
        "prioridad": 5,
        "trigger": "cómo enviar, como enviar, paso a paso, guía de envío, embalaje, rotulado, destinatario, remitente",
        "activa": True,
    },
    {
        "id": "reclamos_quejas",
        "nombre": "Reclamos y quejas",
        "descripcion": "Orienta sobre reclamos, quejas, demoras, pérdidas, incidencias y canales de atención.",
        "modo": "rag+llm",
        "categoria": "atencion",
        "prioridad": 5,
        "trigger": "reclamo, reclamos, queja, quejas, denuncia, demora, perdido, extraviado, no llegó, no llego",
        "activa": True,
    },
    {
        "id": "alertas_seguridad",
        "nombre": "Evita estafas y alertas de seguridad",
        "descripcion": "Ayuda a identificar fraudes, enlaces sospechosos y prácticas seguras relacionadas con servicios postales.",
        "modo": "rag+llm",
        "categoria": "analitica",
        "prioridad": 5,
        "trigger": "estafa, fraude, phishing, alerta, seguridad, mensaje falso, enlace sospechoso, scam",
        "activa": True,
    },
    {
        "id": "filatelia_boliviana",
        "nombre": "Filatelia boliviana",
        "descripcion": "Informa sobre sellos de colección, productos filatélicos y contenido histórico relacionado.",
        "modo": "rag+llm",
        "categoria": "documental",
        "prioridad": 4,
        "trigger": "filatelia, sello, sellos, colección, coleccion, estampilla, estampillas",
        "activa": True,
    },
    {
        "id": "oficinas_contacto",
        "nombre": "Oficinas, sucursales y contacto",
        "descripcion": "Resuelve ubicación, horarios, contacto y datos de oficinas o sucursales de Correos de Bolivia.",
        "modo": "rag+llm",
        "categoria": "atencion",
        "prioridad": 5,
        "trigger": "oficina, oficinas, sucursal, sucursales, contacto, teléfono, telefono, dirección, direccion, horario",
        "activa": True,
    },
    {
        "id": "historia_correos_bolivia",
        "nombre": "Historia de Correos Bolivia",
        "descripcion": "Responde sobre historia institucional, evolución y antecedentes de Correos de Bolivia.",
        "modo": "rag+llm",
        "categoria": "documental",
        "prioridad": 3,
        "trigger": "historia, historia institucional, origen, evolución, evolucion, antecedentes, correos bolivia",
        "activa": True,
    },
    {
        "id": "multilenguaje",
        "nombre": "Traducción conversacional",
        "descripcion": "Mantiene la conversación en varios idiomas y traduce respuestas visibles del bot.",
        "modo": "translation",
        "categoria": "idioma",
        "prioridad": 4,
        "trigger": "traducir, idioma, language, traducción, translation",
        "activa": True,
    },
    {
        "id": "estado_plataforma",
        "nombre": "Estado del sistema",
        "descripcion": "Resume el estado operativo del bot, el modelo, el RAG y los recursos cargados.",
        "modo": "internal",
        "categoria": "operacion",
        "prioridad": 3,
        "trigger": "skills, capacidades, estado del bot, estado del sistema",
        "activa": True,
    },
]

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
    "rastreo", "seguimiento", "tarifa", "tarifas", "precio", "precios", "servicio", "servicios",
    "reclamo", "queja", "quejas", "estafa", "fraude", "seguridad", "filatelia", "sello", "sellos",
    "oficina", "oficinas", "sucursal", "sucursales", "contacto", "historia", "estampilla", "estampillas",
}

OUT_OF_SCOPE_SAMPLES = (
    "Puedo ayudarte solo con temas de Correos de Bolivia: rastreo de envíos, tarifas, servicios, "
    "cómo enviar correctamente, reclamos, alertas de seguridad, filatelia, oficinas, contacto e historia institucional."
)


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


def _normalizar_texto_extraido(texto: str | None) -> str | None:
    if not texto:
        return None
    texto = texto.replace("\x00", " ")
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip() or None


def _normalizar_match_text(texto: str | None) -> str:
    texto = (texto or "").strip().lower()
    texto = "".join(
        ch for ch in unicodedata.normalize("NFKD", texto)
        if not unicodedata.combining(ch)
    )
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def _texto_util(texto: str | None) -> bool:
    if not texto or len(texto) < 40:
        return False
    letras = len(re.findall(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]", texto))
    return letras >= 20


def _sanitize_filename(nombre: str) -> str:
    nombre = os.path.basename(nombre or "").strip()
    nombre = re.sub(r"[^\w\-.]", "_", nombre)
    if not nombre.lower().endswith(".pdf"):
        raise ValueError("El archivo debe tener extensión .pdf")
    return nombre


def _extraer_con_pdfplumber(ruta: str) -> str | None:
    if not _PDFPLUMBER_AVAILABLE:
        return None
    bloques = []
    with pdfplumber.open(ruta) as pdf:  # type: ignore[arg-type]
        for idx, pagina in enumerate(pdf.pages, start=1):
            texto = pagina.extract_text(x_tolerance=1.5, y_tolerance=3)
            if texto and texto.strip():
                bloques.append(f"--- Página {idx} ---\n{texto}")
    return "\n\n".join(bloques) if bloques else None


def _extraer_con_pdfplumber_words(ruta: str) -> str | None:
    if not _PDFPLUMBER_AVAILABLE:
        return None
    bloques = []
    with pdfplumber.open(ruta) as pdf:  # type: ignore[arg-type]
        for idx, pagina in enumerate(pdf.pages, start=1):
            palabras = pagina.extract_words(
                x_tolerance=2,
                y_tolerance=3,
                keep_blank_chars=False,
                use_text_flow=True,
            )
            if not palabras:
                continue
            lineas = []
            actual_top = None
            actual = []
            for palabra in palabras:
                top = round(float(palabra.get("top", 0)), 1)
                if actual_top is None or abs(top - actual_top) <= 3:
                    actual.append(palabra.get("text", ""))
                    actual_top = top if actual_top is None else actual_top
                else:
                    lineas.append(" ".join(actual))
                    actual = [palabra.get("text", "")]
                    actual_top = top
            if actual:
                lineas.append(" ".join(actual))
            texto = "\n".join(linea.strip() for linea in lineas if linea.strip())
            if texto:
                bloques.append(f"--- Página {idx} ---\n{texto}")
    return "\n\n".join(bloques) if bloques else None


def _extraer_con_pypdf2(ruta: str) -> str | None:
    if not _PYPDF2_AVAILABLE:
        return None
    bloques = []
    with open(ruta, "rb") as fh:
        reader = PyPDF2.PdfReader(fh)  # type: ignore[union-attr]
        for idx, pagina in enumerate(reader.pages, start=1):
            texto = pagina.extract_text()
            if texto and texto.strip():
                bloques.append(f"--- Página {idx} ---\n{texto}")
    return "\n\n".join(bloques) if bloques else None


def _extraer_con_ocr(ruta: str) -> str | None:
    if not _OCR_AVAILABLE:
        return None
    if not shutil.which("tesseract") or not shutil.which("pdftoppm"):
        return None
    paginas = convert_from_path(ruta, dpi=220, first_page=1, last_page=12)  # type: ignore[misc]
    bloques = []
    for idx, imagen in enumerate(paginas, start=1):
        texto = pytesseract.image_to_string(imagen, lang="spa+eng", config="--psm 6")  # type: ignore[union-attr]
        texto = _normalizar_texto_extraido(texto)
        if texto and len(texto) > 20:
            bloques.append(f"--- Página {idx} ---\n{texto}")
    return "\n\n".join(bloques) if bloques else None


def extraer_texto_pdf(ruta: str) -> tuple[str | None, str | None]:
    extractores = [
        ("pdfplumber_text", _extraer_con_pdfplumber),
        ("pdfplumber_words", _extraer_con_pdfplumber_words),
        ("pypdf2", _extraer_con_pypdf2),
        ("ocr", _extraer_con_ocr),
    ]
    for metodo, fn in extractores:
        try:
            texto = _normalizar_texto_extraido(fn(ruta))
            if _texto_util(texto):
                return texto, metodo
        except Exception as exc:
            print(f"   Error extrayendo PDF con {metodo}: {exc}")
    return None, None


def _clean_pdf_entry(item: dict) -> dict:
    limpio = dict(item)
    for key in ("archivo_existe", "ruta_real", "texto_disponible", "estado_extraccion"):
        limpio.pop(key, None)
    return limpio


def _file_stats(path: str) -> dict:
    real_path = path
    exists = os.path.exists(real_path)
    size_bytes = os.path.getsize(real_path) if exists and os.path.isfile(real_path) else 0
    return {
        "path": real_path,
        "exists": exists,
        "size_bytes": size_bytes,
        "size_kb": round(size_bytes / 1024, 2) if size_bytes else 0,
    }


def _pdf_record_id(item: dict) -> str:
    base = "||".join([
        str(item.get("nombre_archivo") or ""),
        str(item.get("url") or ""),
        str(item.get("pagina_fuente") or ""),
        str(item.get("archivo_local") or ""),
    ])
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


def listar_skills() -> list[dict]:
    skills = [_normalizar_skill(item) for item in _load_catalog(SKILLS_FILE, DEFAULT_SKILLS)]
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
    raw_tokens = re.split(r"[,;|]", skill.get("trigger") or "")
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
    return skill


def get_active_skills() -> list[dict]:
    return [item for item in listar_skills() if item.get("activa", True)]


def resolve_skills_for_query(pregunta: str) -> dict:
    texto = _normalizar_match_text(pregunta)
    palabras = set(texto.split())
    skills = get_active_skills()
    matches = []

    for skill in skills:
        score = 0
        for token in skill.get("trigger_tokens", []):
            if token and token in texto:
                score += max(3, len(token.split()) * 2)
                continue
            token_words = [word for word in token.split() if len(word) >= 4]
            if token_words and all(word in palabras for word in token_words):
                score += max(2, len(token_words))
        for word in skill.get("trigger_words", []):
            if word in palabras:
                score += 1
        if skill["id"] == "oficinas_contacto" and any(word in texto for word in ("donde", "direccion", "ubicacion", "horario", "telefono")):
            score += 2
        if skill["id"] == "rastreo_envios" and any(word in texto for word in ("codigo", "guia", "tracking", "seguimiento", "rastreo", "envio", "paquete")):
            score += 3
        if skill["id"] == "calculadora_tarifas" and any(word in texto for word in ("cuanto cuesta", "cotizacion", "peso")):
            score += 2
        if skill["id"] == "servicios_correos" and any(word in texto for word in ("servicio", "ems", "certificado", "ordinario", "encomienda")):
            score += 2
        if skill["id"] == "reclamos_quejas" and any(word in texto for word in ("reclamo", "queja", "demora", "extraviado", "perdido")):
            score += 2
        if score > 0:
            item = dict(skill)
            item["match_score"] = score + int(skill.get("prioridad", 3))
            matches.append(item)

    matches.sort(key=lambda item: (-item["match_score"], -(item.get("prioridad", 3)), item.get("nombre", "")))
    if matches:
        top_score = matches[0]["match_score"]
        filtered = []
        for idx, item in enumerate(matches):
            if idx == 0:
                filtered.append(item)
                continue
            if len(filtered) >= 2:
                break
            score_gap = top_score - item["match_score"]
            if item["match_score"] >= 7 and score_gap <= 3:
                filtered.append(item)
        matches = filtered
    in_scope = bool(matches) or any(token in texto.split() for token in SKILL_SCOPE_KEYWORDS) or "correos" in texto or "agbc" in texto

    return {
        "in_scope": in_scope,
        "matched_skills": matches,
        "primary_skill": matches[0] if matches else None,
        "skill_ids": [item["id"] for item in matches],
    }


def build_skill_manifest(skills: list[dict] | None = None) -> str:
    active = skills or get_active_skills()
    lineas = []
    for item in active:
        lineas.append(
            f"- {item['nombre']} ({item['id']}): "
            f"categoria={item.get('categoria','custom')}, prioridad={item.get('prioridad',3)}, "
            f"trigger={item.get('trigger','sin trigger')}."
        )
    return "\n".join(lineas)


def out_of_scope_response() -> str:
    return OUT_OF_SCOPE_SAMPLES


def preferred_sources_for_skill(skill: dict | None) -> list[str]:
    if not skill:
        return ["web_main", "section", "branch", "history", "pdf"]

    skill_id = skill.get("id")
    categoria = skill.get("categoria")

    if skill_id == "historia_correos_bolivia":
        return ["history", "pdf", "section", "web_main", "branch"]
    if skill_id == "filatelia_boliviana" or categoria == "documental":
        return ["pdf", "history", "section", "web_main", "branch"]
    if skill_id == "oficinas_contacto":
        return ["branch", "web_main", "section", "history", "pdf"]
    if skill_id in {"rastreo_envios", "calculadora_tarifas", "servicios_correos", "guia_envio_correcto", "reclamos_quejas"}:
        return ["web_main", "section", "pdf", "branch", "history"]
    if skill_id == "estado_plataforma":
        return ["section", "web_main", "pdf", "branch", "history"]
    return ["web_main", "section", "branch", "history", "pdf"]


def listar_pdfs() -> list[dict]:
    pdfs = _load_catalog(PDFS_FILE, [])
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
            "paginas_exitosas": stats.get("paginas_exitosas", 0),
            "paginas_fallidas": stats.get("paginas_fallidas", 0),
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

    return {
        "skills": skills,
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
                "ollama_url": os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434/api/chat"),
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


def detectar_consulta_especial(pregunta: str) -> str | None:
    texto = (pregunta or "").strip().lower()
    if not texto:
        return None

    if any(token in texto for token in ("skill", "skills", "habilidad", "habilidades")):
        return "skills"
    if any(token in texto for token in ("rag", "chroma", "embeddings", "chunks", "base vectorial")):
        return "rag_local"
    if any(token in texto for token in ("estado del sistema", "status del sistema", "estado bot", "estado del bot")):
        return "system_status"
    if any(token in texto for token in ("sucursales cargadas", "resumen de sucursales", "estado de sucursales")):
        return "branches_summary"
    if any(token in texto for token in ("genera", "generar", "que puedes hacer", "capacidades del bot")):
        return "generar"
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
        "Puedo generar respuestas con el modelo local, consultar el RAG institucional y usar skills internas.\n"
        f"Skills: {len(runtime_capabilities['skills'])}. "
        f"Chunks RAG: {runtime_capabilities['rag']['chunks']}.\n"
        "Usa Skills o Analizar RAG para inspeccionar cada capacidad."
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

    skills = listar_skills()
    nuevo = _normalizar_skill({
        "id": skill_id,
        "nombre": nombre,
        "descripcion": descripcion,
        "modo": modo,
        "categoria": categoria,
        "prioridad": prioridad,
        "trigger": trigger,
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

    _save_catalog(SKILLS_FILE, skills)
    return {"skill": nuevo, "created": not replaced}


def eliminar_skill(skill_id: str) -> bool:
    skills = listar_skills()
    filtrados = [item for item in skills if item.get("id") != skill_id]
    if len(filtrados) == len(skills):
        return False
    _save_catalog(SKILLS_FILE, filtrados)
    return True


def management_options() -> dict:
    return {
        "modos_skill": listar_modos_skill(),
        "categorias_skill": listar_categorias_skill(),
        "modos_skill_ids": sorted(SUPPORTED_SKILL_MODE_IDS),
        "categorias_skill_ids": sorted(SUPPORTED_SKILL_CATEGORY_IDS),
    }


def guardar_pdf_subido(file_storage, fuente_url: str = "", pagina_fuente: str = "") -> dict:
    if file_storage is None or not getattr(file_storage, "filename", ""):
        raise ValueError("Debes seleccionar un archivo PDF")

    nombre_archivo = _sanitize_filename(file_storage.filename)
    os.makedirs(PDF_DIR, exist_ok=True)
    ruta_real = os.path.join(PDF_DIR, nombre_archivo)
    file_storage.save(ruta_real)

    try:
        texto, metodo = extraer_texto_pdf(ruta_real)
        tamano_bytes = os.path.getsize(ruta_real) if os.path.exists(ruta_real) else 0
    finally:
        try:
            if os.path.exists(ruta_real):
                os.remove(ruta_real)
        except OSError as exc:
            print(f"   Error eliminando PDF temporal subido: {exc}")

    pdfs = [_clean_pdf_entry(item) for item in _load_catalog(PDFS_FILE, [])]
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
    }

    replaced = False
    for idx, item in enumerate(pdfs):
        if item.get("nombre_archivo") == nombre_archivo:
            pdfs[idx] = registro
            replaced = True
            break
    if not replaced:
        pdfs.append(registro)

    _save_catalog(PDFS_FILE, pdfs)
    salida = dict(registro)
    salida["archivo_existe"] = False
    salida["texto_disponible"] = bool(texto)
    salida["estado_extraccion"] = "ok" if texto else "sin_texto"
    return {"ok": True, "created": not replaced, "pdf": salida}


def reprocesar_pdf(nombre_archivo: str) -> dict:
    pdfs = _load_catalog(PDFS_FILE, [])
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

    texto, metodo = extraer_texto_pdf(ruta_real)
    registro["archivo_local"] = ruta_real
    registro["texto_extraido"] = texto
    registro["longitud_texto"] = len(texto) if texto else 0
    registro["metodo_extraccion"] = metodo
    pdfs[idx] = registro
    _save_catalog(PDFS_FILE, pdfs)

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
    pdfs = _load_catalog(PDFS_FILE, [])
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
            actualizados.append(registro)
            continue

        texto_nuevo, metodo_nuevo = extraer_texto_pdf(ruta_real)
        reprocesados += 1

        if texto_nuevo and len(texto_nuevo) > len(texto_actual):
            mejorados += 1

        registro["archivo_local"] = ruta_real
        registro["texto_extraido"] = texto_nuevo
        registro["longitud_texto"] = len(texto_nuevo) if texto_nuevo else 0
        registro["metodo_extraccion"] = metodo_nuevo
        actualizados.append(registro)

    _save_catalog(PDFS_FILE, actualizados)
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


def execute_special_query(tipo: str, runtime_capabilities: dict) -> dict:
    if tipo == "skills":
        return {
            "kind": "skills",
            "payload": runtime_capabilities["skills"],
            "response": _render_skills(runtime_capabilities["skills"]),
        }
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
