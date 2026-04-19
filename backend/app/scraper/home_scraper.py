"""
scraper/home_scraper.py
=======================
Extrae:
  - Secciones del footer/home  → secciones_home.json
  - Sucursales con coordenadas → sucursales_contacto.json
  - Historia institucional     → historia_institucional.json
  - Noticias y eventos         → noticias_eventos.json

Unifica: ExtractorSecciones + ExtractorSucursales + ExtractorHistoria
         + ExtractorNoticias de v3.0, más lógica de sucursales de v4.0
"""

import re
from typing import Any, Optional
from urllib.parse import unquote                          # ← NUEVO
from bs4 import BeautifulSoup

from base_scraper import (
    limpiar_texto, validar_coords_bolivia, generar_maps_url
)
from config import ScraperConfig


# ─────────────────────────────────────────────
#  COORDENADAS DE GOOGLE MAPS
# ─────────────────────────────────────────────

def resolver_url_corta(url: str) -> str:                 # ← NUEVO
    """
    Si es un enlace corto (goo.gl, maps.app.goo.gl), sigue la redirección
    para obtener la URL real con las coordenadas.
    """
    if not url:
        return url
    if "goo.gl" in url or "maps.app.goo.gl" in url:
        try:
            import requests
            resp = requests.head(
                url, allow_redirects=True, timeout=5,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            return resp.url
        except Exception:
            pass
    return url


def extraer_coordenadas_de_url(url: str) -> dict | None:
    """
    Extrae coordenadas de casi cualquier formato de Google Maps.

    Patrones soportados (en orden de prioridad):
      1. !3d LAT !4d LNG  → Place Link (pin exacto)
      2. !2d LNG !3d LAT  → Embed iframe (orden invertido)
      3. @ LAT , LNG      → Vista del mapa
      4. ?q= LAT , LNG    → Query / iframe embed (acepta %2C y espacios)

    También resuelve enlaces cortos goo.gl / maps.app.goo.gl.
    """
    if not url:
        return None

    # 0. Resolver enlace corto si aplica
    url = resolver_url_corta(url)

    # 0b. Decodificar caracteres URL (%2C%20 → ", ")
    url = unquote(url)

    # ─── 1. PATRÓN EXACTO (Prioridad Alta) ───
    # Formato: !3d-16.499149!4d-68.135114
    match = re.search(r"!3d(-?\d{1,3}\.\d+)!4d(-?\d{1,3}\.\d+)", url)
    if match:
        try:
            lat, lng = float(match.group(1)), float(match.group(2))
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                return {"lat": lat, "lng": lng}
        except ValueError:
            pass

    # ─── 2. PATRÓN EMBED IFRAME (orden invertido) ───
    # Formato: !2d-68.135114!3d-16.499149  → primer grupo es LNG, segundo LAT
    match = re.search(r"!2d(-?\d{1,3}\.\d+)!3d(-?\d{1,3}\.\d+)", url)
    if match:
        try:
            lng, lat = float(match.group(1)), float(match.group(2))
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                return {"lat": lat, "lng": lng}
        except ValueError:
            pass

    # ─── 3. PATRÓN DE VISTA DE MAPA (Prioridad Media) ───
    # Formato: @-16.499149,-68.135114,17z
    match = re.search(r"@(-?\d{1,3}\.\d+),(-?\d{1,3}\.\d+)", url)
    if match:
        try:
            lat, lng = float(match.group(1)), float(match.group(2))
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                return {"lat": lat, "lng": lng}
        except ValueError:
            pass

    # ─── 4. PATRÓN DE BÚSQUEDA / EMBED (Prioridad Baja) ───
    # Formato: ?q=-16.499149,-68.135114  (acepta espacio opcional tras coma)
    match = re.search(r"q=(-?\d{1,3}\.\d+),\s*(-?\d{1,3}\.\d+)", url)
    if match:
        try:
            lat, lng = float(match.group(1)), float(match.group(2))
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                return {"lat": lat, "lng": lng}
        except ValueError:
            pass

    return None


def extraer_coordenadas_de_soup(soup: BeautifulSoup) -> list[dict]:
    """
    Extrae TODAS las coordenadas únicas de mapas en una página.

    Fuentes buscadas (en orden):
      1. <iframe src="...maps...">
      2. <iframe data-src="...maps...">
      3. <a href="...maps..."> (fallback)

    La deduplicación se hace por coordenadas redondeadas a 5 decimales
    para evitar duplicados por diferencias mínimas de codificación de URL.
    """
    coords: list[dict] = []
    coords_vistas: set[tuple] = set()          # ← NUEVO: deduplicar por valor

    def _registrar(url_src: str) -> None:
        c = extraer_coordenadas_de_url(url_src)
        if not c:
            return
        clave = (round(c["lat"], 5), round(c["lng"], 5))
        if clave in coords_vistas:
            return
        coords_vistas.add(clave)
        coords.append(c)

    # 1 + 2: iframes (src y data-src)
    for iframe in soup.find_all("iframe"):
        src = iframe.get("src", "") or iframe.get("data-src", "")
        if "maps.google" in src or "google.com/maps" in src:
            _registrar(src)

    # 3: enlaces <a> como fallback
    if not coords:
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "maps.google" in href or "google.com/maps" in href:
                _registrar(href)

    return coords


# ─────────────────────────────────────────────
#  SECCIONES DEL HOME
# ─────────────────────────────────────────────

def extraer_secciones(html: str) -> dict[str, list[str]]:
    """Extrae secciones del footer/home para secciones_home.json."""
    soup    = BeautifulSoup(html, "html.parser")
    footer  = soup.find("footer") or soup
    secciones: dict[str, list[str]] = {}

    for bloque in footer.find_all(["div", "section", "nav"]):
        titulo_tag = bloque.find(["h2", "h3", "h4", "h5"])
        if not titulo_tag:
            continue
        titulo = limpiar_texto(titulo_tag.get_text())
        if not titulo or len(titulo) < 3:
            continue
        items = []
        for li in bloque.find_all("li"):
            texto = limpiar_texto(li.get_text())
            if texto and 2 < len(texto) < 100:
                items.append(texto)
        if items:
            secciones[titulo] = list(dict.fromkeys(items))

    return secciones


# ─────────────────────────────────────────────
#  SUCURSALES
# ─────────────────────────────────────────────

def _extraer_campo_elementor(seccion: Any, nombre: str) -> str:
    """Extrae un campo de un widget Elementor image-box."""
    for wrapper in seccion.find_all("div", class_="elementor-image-box-wrapper"):
        titulo_elem = wrapper.find("h4", class_="elementor-image-box-title")
        if not titulo_elem:
            continue
        if nombre.lower() in limpiar_texto(titulo_elem.get_text()).lower():
            valor_elem = wrapper.find("p", class_="elementor-image-box-description")
            if valor_elem:
                return limpiar_texto(valor_elem.get_text())
    return ""


def _extraccion_sucursales_alternativa(soup: BeautifulSoup, url: str, coords: list) -> list[dict]:
    """Extracción alternativa para páginas sin estructura Elementor estándar."""
    sucursales = []
    contenedores = soup.find_all(
        ["div", "section"],
        class_=re.compile(r'elementor-widget|oficina|sucursal|contact', re.I)
    )
    for cont in contenedores:
        texto = cont.get_text(separator="\n", strip=True)
        if not re.search(r'direcci[oó]n|tel[eé]fono|email', texto, re.I):
            continue
        lineas = [l.strip() for l in texto.split("\n") if l.strip()]
        if len(lineas) < 2:
            continue
        s = {
            "nombre"   : lineas[0],
            "direccion": "",
            "telefono" : "",
            "email"    : ScraperConfig.EMAIL_DEFAULT,
            "horario"  : ScraperConfig.HORARIO_DEFAULT,
            "lat": None, "lng": None, "enlaces": {},
            "fuente"   : url,
        }
        for linea in lineas[1:]:
            if re.search(r'direcci[oó]n', linea, re.I):
                s["direccion"] = linea
            elif re.search(r'tel[eé]fono|celular', linea, re.I):
                s["telefono"] = linea
            elif "@" in linea:
                s["email"] = linea
            elif re.search(r'horario', linea, re.I):
                s["horario"] = linea
        if s["direccion"] or s["telefono"]:
            idx = len(sucursales)
            if idx < len(coords):
                s["lat"] = coords[idx]["lat"]
                s["lng"] = coords[idx]["lng"]
                s["enlaces"] = generar_maps_url(s["lat"], s["lng"])
            sucursales.append(s)
    return sucursales


def extraer_sucursales(html: str, url: str) -> list[dict]:
    """
    Extrae sucursales de la página de contacto.
    Combina distintos métodos según la estructura:
      * primero intentamos el extractor v5 que usa enlaces de Maps para
        asociar coordenadas al bloque de texto más cercano;
      * si no devuelve nada, seguimos con los métodos habituales (elementor
        y regex) que manejan HTML más estructurado.
    """
    soup   = BeautifulSoup(html, "html.parser")
    sucursales: list[dict] = []

    # ── MÉTODO V5: BUSCAR LINKS A GOOGLE MAPS Y SUBIR EN EL DOM ──
    def extraer_con_map_links() -> list[dict]:
        resultados = []
        links = soup.find_all("a", href=re.compile(r"google\.com/maps|maps\.app\.goo\.gl"))
        for link in links:
            map_url = link.get("href", "")
            coords = extraer_coordenadas_de_url(map_url)

            container = link.find_parent("div")
            nivel = 0
            while container and nivel < 5:
                texto_interno = container.get_text(separator=" ", strip=True)
                if len(texto_interno) > 50 and (
                    "dirección" in texto_interno.lower()
                    or "regional" in texto_interno.lower()
                    or "tel" in texto_interno.lower()
                ):
                    break
                container = container.find_parent("div")
                nivel += 1

            if not container:
                continue

            texto_completo = container.get_text(separator="\n", strip=True)
            lineas = [limpiar_texto(l) for l in texto_completo.split("\n") if limpiar_texto(l)]

            data = {
                "nombre": "",
                "direccion": "",
                "telefono": "",
                "email": "",
                "horario": "",
                "lat": coords.get("lat") if coords else None,
                "lng": coords.get("lng") if coords else None,
                "enlaces": {},
                "fuente": url,
            }

            for linea in lineas:
                llow = linea.lower()
                if not data["nombre"] and ("regional" in llow or "agencia" in llow or "oficina" in llow):
                    data["nombre"] = linea
                elif "dirección" in llow or "direccion" in llow or "calle" in llow:
                    data["direccion"] = linea
                elif "teléfono" in llow or "telefono" in llow or "fax" in llow:
                    data["telefono"] = linea
                elif "@" in linea:
                    data["email"] = linea
                elif "horario" in llow or "hora" in llow or "atención" in llow:
                    data["horario"] = linea

            if not data["nombre"] and lineas:
                data["nombre"] = lineas[0]

            if data["nombre"] or data["direccion"]:
                resultados.append(data)
        return resultados

    sucursales = extraer_con_map_links()
    if sucursales:
        return sucursales

    def coords_en_elemento(elem: Any) -> dict | None:
        """Busca coordenadas sólo dentro del elemento HTML dado."""
        iframe = elem.find("iframe")
        if iframe:
            src = iframe.get("src", "") or iframe.get("data-src", "")
            c = extraer_coordenadas_de_url(src)
            if c:
                return c
        for a in elem.find_all("a", href=True):
            href = a["href"]
            if "maps.google" in href or "google.com/maps" in href:
                c = extraer_coordenadas_de_url(href)
                if c:
                    return c
        return None

    # ── Método 1: h3 con clase elementor-heading-title (v3)
    for h3 in soup.find_all("h3", class_="elementor-heading-title"):
        titulo = limpiar_texto(h3.get_text())
        if not re.search(r'Oficina Central|Regional|Agencia|Sucursal', titulo, re.IGNORECASE):
            continue
        seccion = h3.find_parent("section")
        if not seccion:
            continue
        s = {
            "nombre"   : titulo,
            "direccion": _extraer_campo_elementor(seccion, "Direcci"),
            "telefono" : _extraer_campo_elementor(seccion, "Tel"),
            "email"    : _extraer_campo_elementor(seccion, "Email") or ScraperConfig.EMAIL_DEFAULT,
            "horario"  : _extraer_campo_elementor(seccion, "Horario") or ScraperConfig.HORARIO_DEFAULT,
            "lat": None, "lng": None, "enlaces": {},
            "fuente": url,
        }
        coords_local = coords_en_elemento(seccion)
        if coords_local:
            s["lat"]     = coords_local["lat"]
            s["lng"]     = coords_local["lng"]
            s["enlaces"] = generar_maps_url(s["lat"], s["lng"])
        sucursales.append(s)

    # ── Método 2: h2/h3/h4 con regex (v4)
    if not sucursales:
        for h in soup.find_all(["h2", "h3", "h4"]):
            titulo = limpiar_texto(h.get_text())
            if not re.search(r'Oficina|Regional|Agencia|Sucursal', titulo, re.I):
                continue
            seccion = h.find_parent(["section", "div"])
            if not seccion:
                continue
            texto_sec = seccion.get_text(separator="\n", strip=True)
            s = {"nombre": titulo, "fuente": url,
                 "lat": None, "lng": None, "enlaces": {},
                 "email": ScraperConfig.EMAIL_DEFAULT,
                 "horario": ScraperConfig.HORARIO_DEFAULT,
                 "direccion": "", "telefono": ""}
            for pat, campo in [
                (r'Direcci[oó]n[:\s]+([^\n]+)', "direccion"),
                (r'Tel[eé]fono[:\s]+([^\n]+)',  "telefono"),
                (r'Horario[:\s]+([^\n]+)',       "horario"),
            ]:
                m = re.search(pat, texto_sec, re.I)
                if m:
                    s[campo] = limpiar_texto(m.group(1))
            m_email = re.search(r'[\w.-]+@[\w.-]+\.\w+', texto_sec)
            if m_email:
                s["email"] = m_email.group(0)
            coords_local = coords_en_elemento(seccion)
            if coords_local:
                s["lat"]     = coords_local["lat"]
                s["lng"]     = coords_local["lng"]
                s["enlaces"] = generar_maps_url(coords_local["lat"], coords_local["lng"])
            if s["direccion"] or s["telefono"]:
                sucursales.append(s)

    # ── Método 3: Extracción alternativa (v3 fallback)
    if not sucursales:
        coords = extraer_coordenadas_de_soup(soup)
        sucursales = _extraccion_sucursales_alternativa(soup, url, coords)

    return sucursales


# ─────────────────────────────────────────────
#  HISTORIA INSTITUCIONAL
# ─────────────────────────────────────────────

def extraer_historia(html: str, url: str) -> Optional[dict]:
    """Extrae contenido histórico de la institución."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(ScraperConfig.TAGS_ELIMINAR):
        tag.decompose()

    texto = ""
    for selector in ScraperConfig.SELECTORES_CONTENIDO:
        nodo = soup.select_one(selector)
        if nodo:
            texto = nodo.get_text(separator="\n", strip=True)
            if len(texto) > 200:
                break
    if not texto and soup.body:
        texto = soup.body.get_text(separator="\n", strip=True)

    texto = limpiar_texto(texto)
    if not re.search(
        r'hist[oó]ria|rese[ñn]a|antecedente|fundaci[oó]n|trayectoria',
        texto, re.I
    ):
        return None

    titulo = ""
    for tag in soup.find_all(["h1", "h2", "h3"]):
        t = limpiar_texto(tag.get_text())
        if t:
            titulo = t
            break

    anos = sorted(set(re.findall(r'\b(18\d{2}|19\d{2}|20\d{2})\b', texto)))

    return {
        "titulo"          : titulo,
        "contenido"       : texto,
        "anos_mencionados": anos,
        "url"             : url,
        "longitud"        : len(texto),
    }


# ─────────────────────────────────────────────
#  NOTICIAS Y EVENTOS
# ─────────────────────────────────────────────

def extraer_noticias(html: str, url: str) -> list[dict]:
    """Extrae noticias y eventos de la página."""
    soup     = BeautifulSoup(html, "html.parser")
    noticias = []
    vistas   = set()

    contenedores = soup.find_all(
        ["article", "div"],
        class_=re.compile(r'post|article|news|noticia|entry|card|item', re.I)
    )
    if not contenedores:
        contenedores = soup.find_all(
            ["div", "section"],
            class_=re.compile(r'elementor-widget', re.I)
        )

    for cont in contenedores:
        titulo = ""
        for tag in cont.find_all(["h1", "h2", "h3", "h4", "h5"]):
            t = limpiar_texto(tag.get_text())
            if t and len(t) > 5:
                titulo = t
                break
        if not titulo or titulo in vistas:
            continue
        vistas.add(titulo)

        desc = ""
        for p in cont.find_all("p"):
            t = limpiar_texto(p.get_text())
            if t and len(t) > 30 and t != titulo:
                desc = t[:400]
                break

        fecha = ""
        time_tag = cont.find(["time", "span"], class_=re.compile(r'date|fecha', re.I))
        if time_tag:
            fecha = limpiar_texto(time_tag.get_text())
        if not fecha:
            m = re.search(
                r'(\d{1,2}[\-/]\d{1,2}[\-/]\d{2,4}|\d{1,2}\s+de\s+\w+\s+de\s+\d{4})',
                cont.get_text()
            )
            if m:
                fecha = m.group(1)

        enlace = ""
        a = cont.find("a", href=True)
        if a:
            h = a["href"]
            enlace = h if h.startswith("http") else f"{ScraperConfig.BASE_URL}{h}"

        noticias.append({
            "titulo"     : titulo,
            "descripcion": desc,
            "fecha"      : fecha,
            "enlace"     : enlace,
            "fuente"     : url,
        })

    return noticias