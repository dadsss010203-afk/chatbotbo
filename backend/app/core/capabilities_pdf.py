"""
core/capabilities_pdf.py
Utilidades de PDFs para capabilities.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil

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

PDF_CLEAN_MODE_DEFAULT = os.environ.get("PDF_CLEAN_MODE", "aggressive").strip().lower()
PDF_CLEAN_MODES = {"off", "balanced", "aggressive"}


def _resolve_clean_mode(clean_mode: str | None = None) -> str:
    mode = (clean_mode or PDF_CLEAN_MODE_DEFAULT or "aggressive").strip().lower()
    if mode not in PDF_CLEAN_MODES:
        mode = "aggressive"
    return mode


def _ratio_letras(linea: str) -> float:
    if not linea:
        return 0.0
    letras = len(re.findall(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]", linea))
    return letras / max(len(linea), 1)


def _normalizar_linea(linea: str) -> str:
    linea = (linea or "").strip().lower()
    linea = re.sub(r"\d+", "#", linea)
    linea = re.sub(r"\s+", " ", linea)
    return linea


def _es_linea_tabla_vacia(linea: str, mode: str = "aggressive") -> bool:
    l = (linea or "").strip()
    if not l:
        return True
    if re.fullmatch(r"[-_=|+.:;,\s]{3,}", l):
        return True
    # filas de separadores tipo tabla con poco contenido semántico
    if l.count("|") >= 2 and _ratio_letras(l) < (0.35 if mode == "aggressive" else 0.2):
        return True
    if l.count("\t") >= 2 and _ratio_letras(l) < (0.35 if mode == "aggressive" else 0.2):
        return True
    return False


def _es_linea_basura(linea: str, mode: str = "aggressive") -> bool:
    l = (linea or "").strip()
    if not l:
        return True
    l_norm = _normalizar_linea(l)
    if re.fullmatch(r"p[áa]gina\s+#(?:\s+de\s+#)?", l_norm):
        return True
    if l_norm in {"www", "http", "https", "comparte", "share", "menu", "inicio"}:
        return True
    if re.fullmatch(r"https?://\S+", l_norm):
        return True
    if len(l) <= 2:
        return True
    # líneas con demasiados símbolos y pocos caracteres útiles
    threshold = 0.18 if mode == "aggressive" else 0.1
    if _ratio_letras(l) < threshold and re.search(r"[\|\+\-_=]{2,}", l):
        return True
    return False


def _limpiar_lineas_pagina(texto: str, mode: str = "aggressive") -> list[str]:
    lineas_limpias = []
    for raw in (texto or "").splitlines():
        linea = re.sub(r"\s+", " ", raw).strip()
        if _es_linea_tabla_vacia(linea, mode=mode) or _es_linea_basura(linea, mode=mode):
            continue
        lineas_limpias.append(linea)
    return lineas_limpias


def _filtrar_headers_footers_repetidos(paginas: list[list[str]], mode: str = "aggressive") -> list[list[str]]:
    if len(paginas) < 2:
        return paginas

    ocurrencias = {}
    total_paginas = len(paginas)

    for lineas in paginas:
        candidatos = set()
        # detectar encabezados/pies mirando primeras y últimas líneas
        for linea in lineas[:4] + lineas[-4:]:
            norm = _normalizar_linea(linea)
            if not norm or len(norm) < 4:
                continue
            candidatos.add(norm)
        for norm in candidatos:
            ocurrencias[norm] = ocurrencias.get(norm, 0) + 1

    min_ratio = 0.45 if mode == "aggressive" else 0.6
    repetidos = {
        norm
        for norm, count in ocurrencias.items()
        if count >= 2 and (count / total_paginas) >= min_ratio
    }
    if not repetidos:
        return paginas

    resultado = []
    for lineas in paginas:
        filtradas = [l for l in lineas if _normalizar_linea(l) not in repetidos]
        resultado.append(filtradas)
    return resultado


def _reconstruir_texto_paginas(paginas: list[list[str]]) -> str | None:
    bloques = []
    for idx, lineas in enumerate(paginas, start=1):
        if not lineas:
            continue
        texto = "\n".join(lineas).strip()
        if not texto:
            continue
        bloques.append(f"--- Página {idx} ---\n{texto}")
    return "\n\n".join(bloques) if bloques else None


def _postprocesar_paginas(paginas_texto: list[str], clean_mode: str = "aggressive") -> str | None:
    mode = _resolve_clean_mode(clean_mode)
    if mode == "off":
        paginas = [[re.sub(r"\s+", " ", l).strip() for l in (t or "").splitlines() if l.strip()] for t in paginas_texto]
        return _reconstruir_texto_paginas(paginas)
    paginas = [_limpiar_lineas_pagina(t, mode=mode) for t in paginas_texto]
    paginas = _filtrar_headers_footers_repetidos(paginas, mode=mode)
    return _reconstruir_texto_paginas(paginas)


def _normalizar_texto_extraido(texto: str | None) -> str | None:
    if not texto:
        return None
    texto = texto.replace("\x00", " ")
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip() or None


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


def _extraer_con_pdfplumber(ruta: str, clean_mode: str = "aggressive") -> str | None:
    if not _PDFPLUMBER_AVAILABLE:
        return None
    paginas_texto = []
    with pdfplumber.open(ruta) as pdf:  # type: ignore[arg-type]
        for pagina in pdf.pages:
            texto = pagina.extract_text(x_tolerance=1.5, y_tolerance=3)
            if texto and texto.strip():
                paginas_texto.append(texto)
    return _postprocesar_paginas(paginas_texto, clean_mode=clean_mode)


def _extraer_con_pdfplumber_words(ruta: str, clean_mode: str = "aggressive") -> str | None:
    if not _PDFPLUMBER_AVAILABLE:
        return None
    paginas_texto = []
    with pdfplumber.open(ruta) as pdf:  # type: ignore[arg-type]
        for pagina in pdf.pages:
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
                paginas_texto.append(texto)
    return _postprocesar_paginas(paginas_texto, clean_mode=clean_mode)


def _extraer_con_pypdf2(ruta: str, clean_mode: str = "aggressive") -> str | None:
    if not _PYPDF2_AVAILABLE:
        return None
    paginas_texto = []
    with open(ruta, "rb") as fh:
        reader = PyPDF2.PdfReader(fh)  # type: ignore[union-attr]
        for pagina in reader.pages:
            texto = pagina.extract_text()
            if texto and texto.strip():
                paginas_texto.append(texto)
    return _postprocesar_paginas(paginas_texto, clean_mode=clean_mode)


def _extraer_con_ocr(ruta: str, clean_mode: str = "aggressive") -> str | None:
    if not _OCR_AVAILABLE:
        return None
    if not shutil.which("tesseract") or not shutil.which("pdftoppm"):
        return None
    paginas = convert_from_path(ruta, dpi=220, first_page=1, last_page=12)  # type: ignore[misc]
    paginas_texto = []
    for imagen in paginas:
        texto = pytesseract.image_to_string(imagen, lang="spa+eng", config="--psm 6")  # type: ignore[union-attr]
        texto = _normalizar_texto_extraido(texto)
        if texto and len(texto) > 20:
            paginas_texto.append(texto)
    return _postprocesar_paginas(paginas_texto, clean_mode=clean_mode)


def extraer_texto_pdf(ruta: str, clean_mode: str | None = None) -> tuple[str | None, str | None]:
    mode = _resolve_clean_mode(clean_mode)
    extractores = [
        ("pdfplumber_text", _extraer_con_pdfplumber),
        ("pdfplumber_words", _extraer_con_pdfplumber_words),
        ("pypdf2", _extraer_con_pypdf2),
        ("ocr", _extraer_con_ocr),
    ]
    for metodo, fn in extractores:
        try:
            texto = _normalizar_texto_extraido(fn(ruta, clean_mode=mode))
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
    base = "||".join(
        [
            str(item.get("nombre_archivo") or ""),
            str(item.get("url") or ""),
            str(item.get("pagina_fuente") or ""),
            str(item.get("archivo_local") or ""),
        ]
    )
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]
