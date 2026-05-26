"""
scraper/runner.py
=================
Punto de entrada del scraper. Orquesta todos los módulos:

  1. Sitemap         → descubre URLs automáticamente
  2. Páginas         → extrae texto, secciones, sucursales, historia, noticias
  3. Aplicativos     → procesa cada sistema específico (POSTAR, TrackingBO…)
  4. PDFs            → descarga y extrae texto
  5. Exporters       → guarda todos los archivos en /data

Unifica los 3 scrapers anteriores:
  - scraper_correos_bolivia_super.py (v3.0) → lógica de crawling + extractores
  - scraper_aplicativos_v2.py               → aplicativos específicos
  - scraper_completo_v4.py (v4.0)           → sitemap + lógica combinada

Uso:
    python -m scraper.runner
    python scraper/runner.py
"""

import os
import re
import time
import xml.etree.ElementTree as ET
from typing import Set
from urllib.parse import urlparse
from bs4 import BeautifulSoup

from config          import ScraperConfig
from base_scraper    import (
    ClienteHTTP, Estadisticas, limpiar_texto,
    normalizar_ruta, es_url_pdf, detectar_tipos,
    es_duplicado, throttle,
)
from home_scraper    import (
    extraer_secciones, extraer_sucursales,
    extraer_historia, extraer_noticias,
)
from servicios_scraper import (
    DescargadorPDFs, procesar_todos_los_aplicativos,
    extraer_servicios_de_pagina,
)
from exporters import (
    inicializar_texto, guardar_texto, guardar_sucursales,
    guardar_secciones, guardar_aplicativos, guardar_servicios,
    guardar_historia, guardar_noticias, guardar_pdfs,
    guardar_enlaces, guardar_estadisticas, imprimir_resumen,
)


class ScraperRunner:
    """Orquestador principal del scraping."""

    def __init__(self):
        self.cliente       = ClienteHTTP()
        self.stats         = Estadisticas()
        self.descargador   = DescargadorPDFs(self.cliente)
        self.base_netloc   = urlparse(ScraperConfig.BASE_URL).netloc

        self.visitadas  : Set[str] = set()
        self.cola       : list     = []
        self.cola_set   : Set[str] = set()
        self.hashes     : Set[str] = set()

        # Almacenamiento de datos
        self.sucursales : list = []
        self.aplicativos: list = []
        self.servicios  : dict = {
            "aplicaciones": [], "servicios": [],
            "herramientas": [], "enlaces_externos": []
        }
        self.historia   : list = []
        self.noticias   : list = []
        self.enlaces    : list = []

    # ──────────────────────────────────────────
    #  PUNTO DE ENTRADA
    # ──────────────────────────────────────────

    def ejecutar(self):
        self._iniciar()
        try:
            # 1. Sitemap → descubre URLs
            self._procesar_sitemap()

            # 2. Páginas iniciales
            for ruta in ScraperConfig.PAGINAS_INICIALES:
                ruta_norm = normalizar_ruta(ruta, self.base_netloc)
                if ruta_norm:
                    self._encolar(ruta_norm)

            print(f"\n[CRAWLING] {len(self.cola)} URLs en cola inicial\n")

            # 3. Crawl principal
            while self.cola and len(self.visitadas) < ScraperConfig.MAX_PAGINAS:
                ruta = self.cola.pop(0)
                self.cola_set.discard(ruta)
                self._procesar_pagina(ruta)

            # 4. Aplicativos específicos
            print("\n[APLICATIVOS] Procesando aplicativos específicos...")
            self.aplicativos = procesar_todos_los_aplicativos(self.cliente)

            # 5. PDFs encontrados en aplicativos
            for app in self.aplicativos:
                for pdf_url in app.get("pdfs_encontrados", []):
                    self.descargador.procesar(pdf_url, app["url"])

        except KeyboardInterrupt:
            print("\n[INFO] Interrumpido por usuario")
        finally:
            self._finalizar()

    # ──────────────────────────────────────────
    #  SITEMAP
    # ──────────────────────────────────────────

    def _procesar_sitemap(self):
        sitemap_url = f"{ScraperConfig.BASE_URL}/sitemap.xml"
        print(f"[SITEMAP] {sitemap_url}")
        urls = self._extraer_urls_sitemap(sitemap_url)
        for url in urls:
            self._encolar(url)
        print(f"[SITEMAP] {len(urls)} URLs encontradas")

    def _extraer_urls_sitemap(self, url: str, profundidad: int = 0) -> Set[str]:
        urls: Set[str] = set()
        if profundidad > 3:
            return urls
        raw = self.cliente.obtener_texto_raw(url)
        if not raw:
            return urls
        try:
            root = ET.fromstring(raw)
            ns   = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            for loc in root.findall(".//ns:sitemap/ns:loc", ns):
                if loc.text:
                    urls.update(self._extraer_urls_sitemap(loc.text.strip(), profundidad + 1))
            for loc in root.findall(".//ns:url/ns:loc", ns):
                if loc.text:
                    ruta = normalizar_ruta(loc.text.strip(), self.base_netloc)
                    if ruta:
                        urls.add(ruta)
        except ET.ParseError:
            pass
        return urls

    # ──────────────────────────────────────────
    #  CRAWL
    # ──────────────────────────────────────────

    def _encolar(self, ruta: str):
        if ruta and ruta not in self.visitadas and ruta not in self.cola_set:
            self.cola.append(ruta)
            self.cola_set.add(ruta)

    def _procesar_pagina(self, ruta: str):
        if ruta in self.visitadas:
            return
        self.visitadas.add(ruta)

        url = f"{ScraperConfig.BASE_URL.rstrip('/')}{ruta}"
        print(f"[{len(self.visitadas):>3}/{ScraperConfig.MAX_PAGINAS}] {url}  (cola: {len(self.cola)})")

        html = self.cliente.obtener_html(url)
        if not html:
            self.stats.paginas_fallidas += 1
            return

        try:
            soup = BeautifulSoup(html, "html.parser")

            # ── Descubrir nuevos links y PDFs
            if len(self.visitadas) < ScraperConfig.MAX_PAGINAS:
                nuevos = 0
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if es_url_pdf(href):
                        self.descargador.procesar(href, url)
                        continue
                    link = normalizar_ruta(href, self.base_netloc)
                    if link and link not in self.visitadas and link not in self.cola_set:
                        self._encolar(link)
                        nuevos += 1
                if nuevos:
                    print(f"       +{nuevos} links")

            ruta_norm = ruta.rstrip("/") or "/"

            # ── HOME
            if ruta_norm == "/":
                secciones = extraer_secciones(html)
                if secciones:
                    guardar_secciones(secciones)
                    print(f"       {sum(len(v) for v in secciones.values())} items en secciones")

            # ── CONTACTO / SUCURSALES
            if "contact" in ruta_norm or "sucursal" in ruta_norm or "agencia" in ruta_norm:
                nuevas = extraer_sucursales(html, url)
                if nuevas:
                    # Evitar duplicados por nombre
                    nombres_existentes = {s["nombre"] for s in self.sucursales}
                    sin_dup = [s for s in nuevas if s["nombre"] not in nombres_existentes]
                    self.sucursales.extend(sin_dup)
                    guardar_sucursales(self.sucursales)
                    self.stats.sucursales_encontradas = len(self.sucursales)
                    print(f"       {len(sin_dup)} sucursales nuevas (total: {self.stats.sucursales_encontradas})")

            # ── Detectar tipos de contenido
            tipos = detectar_tipos(html, url)

            if "aplicacion" in tipos:
                servicios_pagina = extraer_servicios_de_pagina(html, url)
                self._acumular_servicios(servicios_pagina)

            if "servicio" in tipos:
                servicios_pagina = extraer_servicios_de_pagina(html, url)
                self._acumular_servicios(servicios_pagina)

            if "historia" in tipos:
                h = extraer_historia(html, url)
                if h:
                    self.historia.append(h)
                    print(f"       Historia: {h['titulo'][:50]}")

            if "noticia" in tipos:
                nuevas_noticias = extraer_noticias(html, url)
                titulos_existentes = {n["titulo"] for n in self.noticias}
                sin_dup = [n for n in nuevas_noticias if n["titulo"] not in titulos_existentes]
                self.noticias.extend(sin_dup)
                self.stats.noticias_encontradas = len(self.noticias)
                if sin_dup:
                    print(f"       {len(sin_dup)} noticias nuevas")

            # ── Extraer texto general
            self._extraer_y_guardar_texto(soup, html, url, tipos)

        except Exception as e:
            self.stats.paginas_fallidas += 1
            self.stats.errores.append(f"{url}: {str(e)}")
            print(f"       [ERROR] {e}")

        throttle()

    def _acumular_servicios(self, nuevo: dict):
        for clave in self.servicios:
            if clave in nuevo:
                # Deduplicar por nombre
                nombres = {s.get("nombre", "") for s in self.servicios[clave]}
                self.servicios[clave].extend(
                    s for s in nuevo[clave] if s.get("nombre") not in nombres
                )
        self.stats.servicios_encontrados = len(self.servicios["servicios"])

    def _extraer_y_guardar_texto(
        self, soup: BeautifulSoup, html: str, url: str, tipos: list
    ):
        soup_limpio = BeautifulSoup(html, "html.parser")
        for tag in soup_limpio.find_all(ScraperConfig.TAGS_ELIMINAR):
            tag.decompose()

        texto = ""
        for selector in ScraperConfig.SELECTORES_CONTENIDO:
            nodo = soup_limpio.select_one(selector)
            if nodo:
                texto = nodo.get_text(separator="\n", strip=True)
                if len(texto) > 100:
                    break
        if not texto and soup_limpio.body:
            texto = soup_limpio.body.get_text(separator="\n", strip=True)

        texto = limpiar_texto(texto)

        if es_duplicado(texto, self.hashes):
            return
        if len(texto) < 100 or "sitemap" in url.lower():
            self.stats.paginas_fallidas += 1
            return

        # Metadata
        titulo_tag = soup.find("title")
        titulo     = limpiar_texto(titulo_tag.get_text()) if titulo_tag else ""
        meta_desc  = soup.find("meta", attrs={"name": "description"})
        descripcion= limpiar_texto(meta_desc.get("content", "")) if meta_desc else ""

        tipos_str = ", ".join(tipos)
        partes    = [
            f"\n{'='*60}",
            f"FUENTE: {url}",
        ]
        if titulo:
            partes.append(f"TITULO: {titulo}")
        if descripcion:
            partes.append(f"DESCRIPCION: {descripcion}")
        partes += [f"TIPOS: {tipos_str}", f"{'='*60}", texto, ""]

        guardar_texto("\n".join(partes))
        self.stats.caracteres_extraidos += len(texto)
        self.stats.paginas_exitosas     += 1
        print(f"       {len(texto):,} chars [{tipos_str}]")

    # ──────────────────────────────────────────
    #  INICIO / FIN
    # ──────────────────────────────────────────

    def _iniciar(self):
        os.makedirs(ScraperConfig.OUTPUT_DIR, exist_ok=True)
        os.makedirs(ScraperConfig.PDF_DIR, exist_ok=True)
        inicializar_texto()
        print("=" * 70)
        print("    SCRAPER UNIFICADO - CORREOS BOLIVIA v5.0")
        print("=" * 70)
        print(f"    Base    : {ScraperConfig.BASE_URL}")
        print(f"    Límite  : {ScraperConfig.MAX_PAGINAS} páginas")
        print(f"    PDFs    : máximo {ScraperConfig.MAX_PDFS}")
        print(f"    Salida  : {ScraperConfig.OUTPUT_DIR}/")
        print("=" * 70)

    def _finalizar(self):
        from datetime import datetime
        self.stats.fin                    = datetime.now().isoformat()
        self.stats.pdfs_descargados       = self.descargador.total
        self.stats.aplicativos_encontrados= len(self.aplicativos)
        self.stats.historia_encontrada    = len(self.historia) > 0

        # Guardar todo
        guardar_sucursales(self.sucursales)
        guardar_aplicativos(self.aplicativos)
        guardar_servicios(self.servicios)
        guardar_historia(self.historia)
        guardar_noticias(self.noticias)
        guardar_pdfs(self.descargador.contenido)
        guardar_enlaces(self.servicios.get("enlaces_externos", []))
        guardar_estadisticas(self.stats.to_dict())

        self.cliente.cerrar()
        imprimir_resumen(self.stats.to_dict())


# ─────────────────────────────────────────────
#  PUNTO DE ENTRADA
# ─────────────────────────────────────────────

def main():
    print("\n  Instala dependencias si no lo has hecho:")
    print("  pip install requests beautifulsoup4 pdfplumber\n")
    runner = ScraperRunner()
    runner.ejecutar()


if __name__ == "__main__":
    main()
