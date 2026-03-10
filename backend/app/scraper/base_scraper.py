"""
scraper/base_scraper.py
=======================
Cliente HTTP con reintentos + utilidades compartidas.
Unifica ClienteHTTP de v3 + helpers de v4.
"""

import re
import time
import hashlib
import unicodedata
import warnings
import urllib3
from typing import Optional, Set
from urllib.parse import urlparse, unquote
from datetime import datetime

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import ScraperConfig

warnings.filterwarnings("ignore")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ─────────────────────────────────────────────
#  ESTADÍSTICAS
# ─────────────────────────────────────────────

class Estadisticas:
    def __init__(self):
        self.inicio                 = datetime.now().isoformat()
        self.fin                    = None
        self.paginas_exitosas       = 0
        self.paginas_fallidas       = 0
        self.caracteres_extraidos   = 0
        self.sucursales_encontradas = 0
        self.aplicativos_encontrados= 0
        self.servicios_encontrados  = 0
        self.noticias_encontradas   = 0
        self.pdfs_descargados       = 0
        self.historia_encontrada    = False
        self.errores: list          = []

    def to_dict(self) -> dict:
        duracion = 0
        if self.inicio and self.fin:
            try:
                i = datetime.fromisoformat(self.inicio)
                f = datetime.fromisoformat(self.fin)
                duracion = (f - i).total_seconds()
            except Exception:
                pass
        return {
            "inicio"                 : self.inicio,
            "fin"                    : self.fin,
            "duracion_segundos"      : duracion,
            "paginas_exitosas"       : self.paginas_exitosas,
            "paginas_fallidas"       : self.paginas_fallidas,
            "caracteres_extraidos"   : self.caracteres_extraidos,
            "sucursales_encontradas" : self.sucursales_encontradas,
            "aplicativos_encontrados": self.aplicativos_encontrados,
            "servicios_encontrados"  : self.servicios_encontrados,
            "noticias_encontradas"   : self.noticias_encontradas,
            "pdfs_descargados"       : self.pdfs_descargados,
            "historia_encontrada"    : self.historia_encontrada,
            "errores"                : self.errores[:30],
        }


# ─────────────────────────────────────────────
#  CLIENTE HTTP
# ─────────────────────────────────────────────

class ClienteHTTP:
    """Cliente HTTP con reintentos automáticos y soporte de streaming para PDFs."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(ScraperConfig.HEADERS)

        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://",  adapter)

    def obtener_html(self, url: str) -> Optional[str]:
        """Descarga y devuelve el HTML de una URL."""
        try:
            r = self.session.get(
                url,
                timeout=ScraperConfig.REQUEST_TIMEOUT,
                verify=False,
                allow_redirects=True,
            )
            r.raise_for_status()
            ct = r.headers.get("Content-Type", "")
            # Ignorar XML puro (sitemaps se manejan aparte)
            if "xml" in ct and "html" not in ct:
                return None
            if "html" not in ct.lower() and not url.endswith("/"):
                return None
            return r.text
        except requests.exceptions.Timeout:
            print("       [ERROR] Timeout")
        except requests.exceptions.ConnectionError:
            print("       [ERROR] Conexión fallida")
        except requests.exceptions.HTTPError as e:
            print(f"       [ERROR] HTTP {e.response.status_code}")
        except Exception as e:
            print(f"       [ERROR] {type(e).__name__}: {str(e)[:60]}")
        return None

    def obtener_binario(self, url: str, timeout: int = 45) -> Optional[bytes]:
        """Descarga contenido binario (PDFs)."""
        try:
            r = self.session.get(
                url, timeout=timeout, verify=False, stream=True
            )
            r.raise_for_status()
            return r.content
        except Exception:
            return None

    def obtener_texto_raw(self, url: str) -> Optional[str]:
        """Descarga contenido de texto plano (sitemaps XML)."""
        try:
            r = self.session.get(
                url,
                timeout=ScraperConfig.REQUEST_TIMEOUT,
                verify=False,
            )
            r.raise_for_status()
            return r.text
        except Exception:
            return None

    def cerrar(self):
        self.session.close()


# ─────────────────────────────────────────────
#  UTILIDADES COMPARTIDAS
# ─────────────────────────────────────────────

def limpiar_texto(texto: str) -> str:
    """Limpia y normaliza texto eliminando ruido."""
    if not texto:
        return ""
    texto = unicodedata.normalize("NFKC", texto)
    texto = re.sub(r'https?://\S+', '', texto)
    texto = re.sub(r'\S+@\S+\.\S+', '', texto)
    texto = re.sub(r'[_\-=*#]{3,}', '', texto)
    texto = re.sub(r' {2,}', ' ', texto)
    texto = re.sub(r'\n{3,}', '\n\n', texto)
    texto = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', texto)
    lineas = [
        l.strip() for l in texto.splitlines()
        if len(l.strip()) > 3
        and not re.match(r'^[\d\s.,;:\-/()\[\]]+$', l.strip())
    ]
    return "\n".join(lineas)


def normalizar_ruta(href: str, base_netloc: str) -> Optional[str]:
    """Convierte un href a ruta relativa interna válida."""
    if not href or href.startswith(("javascript:", "#", "mailto:", "tel:", "data:", "blob:")):
        return None
    try:
        href = href.strip()
        if href.startswith("//"):
            href = "https:" + href
        parsed = urlparse(href)
        if parsed.netloc and parsed.netloc != base_netloc:
            return None
        ruta = parsed.path or "/"
        if re.search(
            r'\.(css|js|apk|exe|dmg|zip|rar|mp[34]|avi|mov|webp|png|jpg|gif|svg)$',
            ruta, re.I
        ):
            return None
        if re.search(
            r'(wp-admin|wp-login|wp-content/uploads|login|logout|feed|xmlrpc)',
            ruta, re.I
        ):
            return None
        return unquote(ruta).rstrip("/") or "/"
    except Exception:
        return None


def es_url_pdf(url: str) -> bool:
    return url.lower().endswith(".pdf") or ".pdf?" in url.lower()


def generar_hash(contenido: str) -> str:
    return hashlib.md5(contenido.encode("utf-8", errors="ignore")).hexdigest()


def es_duplicado(texto: str, hashes: Set[str]) -> bool:
    h = generar_hash(texto)
    if h in hashes:
        return True
    hashes.add(h)
    return False


def detectar_tipos(texto: str, url: str) -> list[str]:
    """Detecta tipos de contenido en base a texto y URL."""
    tipos = []
    tl = texto.lower()
    ul = url.lower()

    checks = [
        ("historia",      ScraperConfig.PATRONES_HISTORIA),
        ("aplicacion",    ScraperConfig.PATRONES_APLICACION),
        ("servicio",      ScraperConfig.PATRONES_SERVICIO),
    ]
    for tipo, patrones in checks:
        for p in patrones:
            if re.search(p, tl) or re.search(p, ul):
                tipos.append(tipo)
                break

    if re.search(r'noticia|evento|comunicado|boletin', tl) or "/noticia" in ul:
        tipos.append("noticia")
    if re.search(r'filatelia|estampilla', tl) or "/filatelia" in ul:
        tipos.append("filatelia")
    if re.search(r'transparencia|contratacion', tl) or "/transparencia" in ul:
        tipos.append("transparencia")
    if re.search(r'institucional|mision|vision|organigrama', tl) or "/institucional" in ul:
        tipos.append("institucional")

    return tipos or ["general"]


def validar_coords_bolivia(lat: float, lng: float) -> bool:
    return -23 < lat < -9 and -70 < lng < -57


def generar_maps_url(lat: float, lng: float) -> dict:
    return {
        "busqueda"   : f"https://www.google.com/maps/search/?api=1&query={lat},{lng}",
        "direcciones": f"https://www.google.com/maps/dir/?api=1&destination={lat},{lng}",
        "mapa"       : f"https://www.google.com/maps/@{lat},{lng},17z",
    }


def throttle():
    time.sleep(ScraperConfig.DELAY_REQUESTS)
