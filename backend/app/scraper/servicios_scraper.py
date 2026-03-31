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


# ─────────────────────────────────────────────
#  DESCARGADOR DE PDFs
# ─────────────────────────────────────────────

class DescargadorPDFs:
    """Descarga PDFs y extrae su texto."""

    def __init__(self, cliente: ClienteHTTP):
        self.cliente          = cliente
        self._vistos: set     = set()
        self.contenido: list  = []

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
        info  = {
            "url"           : url,
            "archivo_local" : ruta,
            "nombre_archivo": nombre,
            "tamano_bytes"  : len(contenido_bytes),
            "texto_extraido": texto,
            "longitud_texto": len(texto) if texto else 0,
            "pagina_fuente" : pagina_fuente,
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
        if not _PDF_LIB:
            return None
        try:
            texto = []
            if _PDF_LIB == "pdfplumber":
                import pdfplumber
                with pdfplumber.open(ruta) as pdf:
                    for p in pdf.pages:
                        t = p.extract_text()
                        if t:
                            texto.append(t)
            else:
                import PyPDF2
                with open(ruta, "rb") as f:
                    reader = PyPDF2.PdfReader(f)
                    for i, p in enumerate(reader.pages):
                        t = p.extract_text()
                        if t:
                            texto.append(f"--- Página {i+1} ---\n{t}")
            return "\n\n".join(texto) if texto else None
        except Exception as e:
            print(f"       [PDF] Error extrayendo texto: {e}")
            return None

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
        "Calculadora de tarifas": r'calculadora|tarifa',
        "Reclamos/Sugerencias" : r'reclamo|sugerencia',
        "Autenticación"        : r'login|usuario|contraseña',
        "Gestión encomiendas"  : r'encomienda',
        "EMS Internacional"    : r'\bems\b',
        "Casillas postales"    : r'casilla',
        "Filatelia"            : r'filatelia|estampilla',
        "Giros postales"       : r'giro postal',
        "Cotización"           : r'cotiz',
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
        elif re.search(r'herramienta|calculadora|rastreo|tracking|cotizador', titulo_tag.lower() + texto_widget):
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
    patron_app  = re.compile(r'aplicativo|aplicaci[oó]n|\bapp\b|sistema|plataforma|tracking|rastreo|calculadora|cotizador|portal|reclamo', re.I)
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
