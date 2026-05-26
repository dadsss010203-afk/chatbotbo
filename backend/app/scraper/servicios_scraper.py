"""
scraper/servicios_scraper.py
============================
Extrae:
  - Aplicativos específicos (POSTAR, TrackingBO, SIRECO…) ← de v2
  - Servicios y herramientas detectados en páginas       ← de v3 + v4
  - PDFs: descarga + extracción de texto                 ← de v3 + v4

Unifica: ExtractorAplicaciones v3 + procesar_aplicativo v2 + lógica PDFs v4
"""

import os
import re
import hashlib
import shutil
from collections import Counter
from typing import Optional
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup

from base_scraper import ClienteHTTP, limpiar_texto, es_url_pdf
from config import ScraperConfig

# ── Soporte PDF
try:
    import pdfplumber
    _PDF_LIB = "pdfplumber"
except ImportError:
    try:
        import PyPDF2
        _PDF_LIB = "PyPDF2"
    except ImportError:
        _PDF_LIB = None
        print("[WARNING] Sin librería PDF. Instala: pip install pdfplumber")

try:
    import pytesseract
    from pdf2image import convert_from_path
    from PIL import ImageOps, ImageFilter
    _OCR_AVAILABLE = True
except ImportError:
    pytesseract = None  # type: ignore
    convert_from_path = None  # type: ignore
    ImageOps = None  # type: ignore
    ImageFilter = None  # type: ignore
    _OCR_AVAILABLE = False


# ─────────────────────────────────────────────
#  DESCARGADOR DE PDFs
# ─────────────────────────────────────────────

class DescargadorPDFs:
    """Descarga PDFs y extrae su texto."""

    def __init__(self, cliente: ClienteHTTP):
        self.cliente          = cliente
        self._vistos: set     = set()
        self.contenido: list  = []
        self._ultimo_metodo_extraccion = None

    def procesar(self, url: str, pagina_fuente: str) -> Optional[dict]:
        if not url.startswith("http"):
            url = urljoin(ScraperConfig.BASE_URL, url)
        if url in self._vistos or len(self._vistos) >= ScraperConfig.MAX_PDFS:
            return None
        self._vistos.add(url)

        print(f"       [PDF] Descargando: {url}")
        contenido_bytes = self.cliente.obtener_binario(url)
        if not contenido_bytes:
            print("       [PDF] Error descargando")
            return None

        nombre = self._nombre_archivo(url)
        ruta   = os.path.join(ScraperConfig.PDF_DIR, nombre)
        os.makedirs(ScraperConfig.PDF_DIR, exist_ok=True)

        try:
            with open(ruta, "wb") as f:
                f.write(contenido_bytes)
        except OSError as e:
            print(f"       [PDF] Error guardando: {e}")
            return None

        texto = self._extraer_texto(ruta)
        try:
            if os.path.exists(ruta):
                os.remove(ruta)
        except OSError as e:
            print(f"       [PDF] No se pudo limpiar temporal {ruta}: {e}")
        info  = {
            "url"           : url,
            "archivo_local" : "",
            "nombre_archivo": nombre,
            "tamano_bytes"  : len(contenido_bytes),
            "texto_extraido": texto,
            "longitud_texto": len(texto) if texto else 0,
            "metodo_extraccion": self._ultimo_metodo_extraccion,
            "pagina_fuente" : pagina_fuente,
            "archivo_guardado": False,
        }
        self.contenido.append(info)
        print(f"       [PDF] OK: {len(contenido_bytes):,} bytes")
        return info

    def _nombre_archivo(self, url: str) -> str:
        nombre = os.path.basename(urlparse(url).path) or f"doc_{len(self._vistos)}.pdf"
        nombre = re.sub(r'[^\w\-_\.]', '_', nombre)
        if len(nombre) > 100:
            h = hashlib.md5(url.encode()).hexdigest()[:8]
            nombre = f"{nombre[:50]}_{h}.pdf"
        return nombre

    def _extraer_texto(self, ruta: str) -> Optional[str]:
        self._ultimo_metodo_extraccion = None

        extractores = [
            ("pdfplumber_text", self._extraer_con_pdfplumber),
            ("pdfplumber_words", self._extraer_con_pdfplumber_words),
            ("pypdf2", self._extraer_con_pypdf2),
            ("ocr", self._extraer_con_ocr),
        ]

        mejor_texto = None
        mejor_metodo = None
        mejor_score = -1

        for metodo, fn in extractores:
            try:
                texto = fn(ruta)
                texto = self._normalizar_texto_extraido(texto)
                score = self._score_texto(texto)
                if score > mejor_score:
                    mejor_texto = texto
                    mejor_metodo = metodo
                    mejor_score = score
                if self._texto_util(texto):
                    print(f"       [PDF] Candidato {metodo}: {len(texto):,} chars")
            except Exception as e:
                print(f"       [PDF] Falló {metodo}: {e}")

        if self._texto_util(mejor_texto):
            self._ultimo_metodo_extraccion = mejor_metodo
            print(f"       [PDF] Texto extraído con {mejor_metodo}: {len(mejor_texto):,} chars")
            return mejor_texto

        print("       [PDF] No se pudo extraer texto util")
        return None

    def _extraer_con_pdfplumber(self, ruta: str) -> Optional[str]:
        if _PDF_LIB != "pdfplumber":
            return None
        import pdfplumber
        bloques = []
        with pdfplumber.open(ruta) as pdf:
            for idx, pagina in enumerate(pdf.pages, start=1):
                texto = pagina.extract_text(x_tolerance=1.5, y_tolerance=3)
                if texto and texto.strip():
                    bloques.append(f"--- Página {idx} ---\n{texto}")
        return self._postprocesar_bloques_paginas(bloques)

    def _extraer_con_pdfplumber_words(self, ruta: str) -> Optional[str]:
        if _PDF_LIB != "pdfplumber":
            return None
        import pdfplumber
        bloques = []
        with pdfplumber.open(ruta) as pdf:
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
        return self._postprocesar_bloques_paginas(bloques)

    def _extraer_con_pypdf2(self, ruta: str) -> Optional[str]:
        try:
            import PyPDF2
        except ImportError:
            return None
        bloques = []
        with open(ruta, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for idx, pagina in enumerate(reader.pages, start=1):
                texto = pagina.extract_text()
                if texto and texto.strip():
                    bloques.append(f"--- Página {idx} ---\n{texto}")
        return self._postprocesar_bloques_paginas(bloques)

    def _extraer_con_ocr(self, ruta: str) -> Optional[str]:
        if not _OCR_AVAILABLE:
            return None
        if not shutil.which("tesseract") or not shutil.which("pdftoppm"):
            return None

        paginas = convert_from_path(
            ruta,
            dpi=ScraperConfig.PDF_OCR_DPI,
            first_page=1,
            last_page=ScraperConfig.PDF_OCR_MAX_PAGES,
        )
        bloques = []
        for idx, imagen in enumerate(paginas, start=1):
            texto = self._ocr_pagina(imagen)
            if self._texto_util(texto):
                bloques.append(f"--- Página {idx} ---\n{texto}")
        return self._postprocesar_bloques_paginas(bloques)

    def _ocr_pagina(self, imagen) -> Optional[str]:
        variantes = [imagen]

        try:
            gris = ImageOps.grayscale(imagen)
            variantes.append(gris)

            autocontrast = ImageOps.autocontrast(gris)
            variantes.append(autocontrast)

            sharpen = autocontrast.filter(ImageFilter.SHARPEN)
            variantes.append(sharpen)

            binaria = autocontrast.point(lambda px: 255 if px > 170 else 0, mode="1")
            variantes.append(binaria)
        except Exception:
            pass

        mejores_textos = []
        configs = [
            "--psm 6",
            "--psm 4",
            "--psm 11",
        ]

        for variante in variantes:
            for config in configs:
                try:
                    texto = pytesseract.image_to_string(  # type: ignore[union-attr]
                        variante, lang="spa+eng", config=config
                    )
                    texto = self._normalizar_texto_extraido(texto)
                    if texto:
                        mejores_textos.append((self._score_texto(texto), texto))
                except Exception:
                    continue

        if not mejores_textos:
            return None

        mejores_textos.sort(key=lambda item: item[0], reverse=True)
        return mejores_textos[0][1]

    def _normalizar_texto_extraido(self, texto: Optional[str]) -> Optional[str]:
        if not texto:
            return None
        texto = texto.replace("\x00", " ")
        texto = re.sub(r"(\w)-\n(\w)", r"\1\2", texto)
        texto = re.sub(r"([A-ZÁÉÍÓÚÑ])\s(?=[A-ZÁÉÍÓÚÑ]\s){3,}", r"\1", texto)
        texto = re.sub(r"[ \t]+", " ", texto)
        texto = re.sub(r" ?\n ?", "\n", texto)
        texto = re.sub(r"\n{3,}", "\n\n", texto)
        texto = re.sub(r"[|~_=]{3,}", " ", texto)
        return texto.strip()

    def _postprocesar_bloques_paginas(self, bloques: list[str]) -> Optional[str]:
        if not bloques:
            return None

        lineas_por_pagina = []
        frecuencia_lineas = Counter()

        for bloque in bloques:
            contenido = re.sub(r"^--- Página \d+ ---\n?", "", bloque).strip()
            lineas = [linea.strip() for linea in contenido.splitlines() if linea.strip()]
            lineas_por_pagina.append(lineas)
            for linea in set(lineas):
                if len(linea) <= 120:
                    frecuencia_lineas[linea] += 1

        minimo_repeticion = max(3, len(lineas_por_pagina) // 3)
        lineas_ruido = {
            linea for linea, total in frecuencia_lineas.items()
            if total >= minimo_repeticion and not re.search(r"\b(art[ií]culo|cap[ií]tulo|ley|decreto|resoluci[oó]n)\b", linea, re.I)
        }

        salida = []
        for idx, lineas in enumerate(lineas_por_pagina, start=1):
            limpias = [linea for linea in lineas if linea not in lineas_ruido]
            if limpias:
                salida.append(f"--- Página {idx} ---\n" + "\n".join(limpias))

        return "\n\n".join(salida) if salida else "\n\n".join(bloques)

    def _texto_util(self, texto: Optional[str]) -> bool:
        if not texto:
            return False
        if len(texto) < ScraperConfig.PDF_TEXTO_MINIMO:
            return False
        letras = len(re.findall(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]", texto))
        lineas = len([linea for linea in texto.splitlines() if linea.strip()])
        return letras >= 40 and lineas >= 2

    def _score_texto(self, texto: Optional[str]) -> int:
        if not texto:
            return -1
        letras = len(re.findall(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]", texto))
        palabras = len(re.findall(r"\b\w+\b", texto, flags=re.UNICODE))
        lineas = len([linea for linea in texto.splitlines() if linea.strip()])
        penalizacion_ruido = len(re.findall(r"[|~_=]{2,}", texto))
        return letras + palabras + (lineas * 10) - (penalizacion_ruido * 25)

    @property
    def total(self) -> int:
        return len(self._vistos)


# ─────────────────────────────────────────────
#  APLICATIVOS ESPECÍFICOS (de v2)
# ─────────────────────────────────────────────

def procesar_aplicativo(cliente: ClienteHTTP, nombre: str, url: str) -> dict:
    """
    Procesa un aplicativo específico (POSTAR, TrackingBO, etc.)
    Extrae: título, contenido, formularios, funcionalidades, PDFs.
    """
    print(f"\n{'='*50}")
    print(f"  {nombre}")
    print(f"  {url}")

    resultado = {
        "nombre"          : nombre,
        "url"             : url,
        "estado"          : "error",
        "titulo"          : "",
        "contenido"       : "",
        "forms"           : [],
        "funcionalidades" : [],
        "pdfs_encontrados": [],
        "error"           : None,
    }

    # Saltar binarios
    if re.search(r'\.(apk|exe|dmg|deb)$', url, re.I):
        resultado["estado"] = "saltado"
        resultado["error"]  = "Archivo binario"
        return resultado

    html = cliente.obtener_html(url)
    if not html:
        resultado["error"] = "No se pudo obtener la página"
        return resultado

    resultado["estado"] = "ok"
    soup = BeautifulSoup(html, "html.parser")

    # Título
    t = soup.find("title")
    resultado["titulo"] = limpiar_texto(t.get_text()) if t else ""

    # Contenido limpio
    for tag in soup.find_all(["script", "style", "nav", "footer"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.body
    resultado["contenido"] = limpiar_texto(
        main.get_text(separator=" ", strip=True)
    )[:5000] if main else ""

    # Formularios e inputs
    for form in soup.find_all("form"):
        form_info = {
            "action": form.get("action", ""),
            "method": form.get("method", "get"),
            "inputs": [],
        }
        for inp in form.find_all(["input", "select", "textarea"]):
            form_info["inputs"].append({
                "type"       : inp.get("type", inp.name),
                "name"       : inp.get("name", ""),
                "placeholder": inp.get("placeholder", ""),
                "required"   : inp.get("required") is not None,
            })
        resultado["forms"].append(form_info)

    # Funcionalidades detectadas
    cl = resultado["contenido"].lower()
    funciones = {
        "Rastreo de envíos"    : r'rastreo|tracking',
        "Reclamos/Sugerencias" : r'reclamo|sugerencia',
        "Autenticación"        : r'login|usuario|contraseña',
        "Gestión encomiendas"  : r'encomienda',
        "EMS Internacional"    : r'\bems\b',
        "Casillas postales"    : r'casilla',
        "Filatelia"            : r'filatelia|estampilla',
        "Giros postales"       : r'giro postal',
    }
    for func, patron in funciones.items():
        if re.search(patron, cl):
            resultado["funcionalidades"].append(func)

    # PDFs encontrados (sin descargar aquí — el runner decide)
    for a in soup.find_all("a", href=True):
        if es_url_pdf(a["href"]):
            resultado["pdfs_encontrados"].append(
                urljoin(url, a["href"])
            )

    print(f"    {resultado['titulo'][:50]} | {len(resultado['funcionalidades'])} funcionalidades")
    return resultado


def procesar_todos_los_aplicativos(cliente: ClienteHTTP) -> list[dict]:
    """Procesa todos los aplicativos definidos en ScraperConfig."""
    resultados = []
    for nombre, url in ScraperConfig.APLICATIVOS_ESPECIFICOS:
        r = procesar_aplicativo(cliente, nombre, url)
        resultados.append(r)
    return resultados


# ─────────────────────────────────────────────
#  SERVICIOS DETECTADOS EN PÁGINAS
# ─────────────────────────────────────────────

def extraer_servicios_de_pagina(html: str, url: str) -> dict:
    """
    Extrae aplicaciones, servicios y herramientas de cualquier página.
    Combina lógica de ExtractorAplicaciones (v3) + v4.
    """
    soup      = BeautifulSoup(html, "html.parser")
    resultado = {
        "aplicaciones"    : [],
        "servicios"       : [],
        "herramientas"    : [],
        "enlaces_externos": [],
    }
    vistas = set()

    # ── Widgets/tarjetas con título
    for widget in soup.find_all(
        ["div", "section"],
        class_=re.compile(r'elementor-widget|card|service|app|feature', re.I)
    ):
        titulo_tag = None
        for h in widget.find_all(["h1","h2","h3","h4","h5","h6"]):
            t = limpiar_texto(h.get_text())
            if t and len(t) > 3:
                titulo_tag = t
                break
        if not titulo_tag or titulo_tag in vistas:
            continue
        vistas.add(titulo_tag)

        desc = ""
        for p in widget.find_all("p"):
            t = limpiar_texto(p.get_text())
            if t and len(t) > 20 and t != titulo_tag:
                desc = t[:300]
                break

        enlace = next(
            (a["href"] for a in widget.find_all("a", href=True)
             if not a["href"].startswith(("#","javascript:","tel:","mailto:"))),
            None
        )

        texto_widget = widget.get_text(separator=" ").lower()
        if re.search(r'aplicativo|app|sistema|plataforma', titulo_tag.lower() + texto_widget):
            tipo = "aplicaciones"
        elif re.search(r'herramienta|rastreo|tracking', titulo_tag.lower() + texto_widget):
            tipo = "herramientas"
        else:
            tipo = "servicios"

        resultado[tipo].append({
            "nombre"     : titulo_tag,
            "descripcion": desc,
            "url"        : enlace,
            "fuente"     : url,
        })

    # ── Links directos a aplicativos/servicios
    patron_app  = re.compile(r'aplicativo|aplicaci[oó]n|\bapp\b|sistema|plataforma|tracking|rastreo|portal|reclamo', re.I)
    patron_serv = re.compile(r'servicio|env[ií]o|correo|paquete|encomienda|carta|telegrama|giro|casilla|apartado', re.I)
    base_netloc = urlparse(ScraperConfig.BASE_URL).netloc

    for a in soup.find_all("a", href=True):
        href   = a["href"]
        texto  = limpiar_texto(a.get_text())
        if not texto or len(texto) < 4 or texto in vistas:
            continue
        vistas.add(texto)

        url_completa = href if href.startswith("http") else urljoin(ScraperConfig.BASE_URL, href)
        es_externo   = bool(urlparse(url_completa).netloc) and urlparse(url_completa).netloc != base_netloc

        if patron_app.search(texto + " " + href):
            entrada = {"nombre": texto, "url": url_completa, "fuente": url}
            if es_externo:
                resultado["enlaces_externos"].append(entrada)
            else:
                resultado["aplicaciones"].append(entrada)
        elif patron_serv.search(texto):
            resultado["servicios"].append({"nombre": texto, "url": url_completa, "fuente": url})

    return resultado
