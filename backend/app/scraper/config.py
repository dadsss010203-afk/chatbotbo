"""
scraper/config.py
=================
Configuración centralizada para todos los módulos del scraper.
Unifica Config de v3.0 + parámetros de v4.0 + aplicativos de v2.
"""

import os

class ScraperConfig:

    # ── URLs base
    BASE_URL = "https://correos.gob.bo"
    OUTPUT_DIR = "data"
    PDF_DIR = os.path.join("data", "pdfs_descargados")

    # ── Archivos de salida
    TEXT_FILE         = os.path.join("data", "correos_bolivia.txt")
    SUCURSALES_FILE   = os.path.join("data", "sucursales_contacto.json")
    SECCIONES_FILE    = os.path.join("data", "secciones_home.json")
    STATS_FILE        = os.path.join("data", "estadisticas.json")
    APLICATIVOS_FILE  = os.path.join("data", "aplicativos_detalle.json")
    SERVICIOS_FILE    = os.path.join("data", "aplicaciones_servicios.json")
    HISTORIA_FILE     = os.path.join("data", "historia_institucional.json")
    NOTICIAS_FILE     = os.path.join("data", "noticias_eventos.json")
    PDFS_FILE         = os.path.join("data", "pdfs_contenido.json")
    ENLACES_FILE      = os.path.join("data", "enlaces_interes.json")

    # ── Límites
    MAX_PAGINAS   = 300
    MAX_PDFS      = 100
    REQUEST_TIMEOUT = 30
    DELAY_REQUESTS  = 0.2

    # ── Headers HTTP
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0",
    }

    # ── Páginas iniciales a visitar (unión de v3 + v4)
    PAGINAS_INICIALES = [
        # Principales
        "/", "/services", "/sp", "/servicio-encomienda-postal",
        "/me", "/eca", "/ems", "/realiza-envios-diarios-a",
        "/institucional", "/contact-us", "/noticias",
        "/about", "/filatelia", "/chasquiexpressbo",
        # Servicios
        "/servicios", "/envios-nacionales", "/envios-internacionales",
        "/servicio-telegramas", "/servicio-giros", "/servicio-casillas",
        # Aplicativos y herramientas
        "/aplicativos", "/calculadora", "/rastreo", "/tracking",
        "/cotizador", "/tarifas", "/precios",
        # Institucional
        "/historia", "/resena-historica", "/quienes-somos",
        "/mision-vision", "/organigrama", "/autoridades",
        "/marco-legal", "/normativa", "/transparencia",
        # Productos
        "/productos", "/estampillas", "/colecciones",
        # Atención
        "/atencion-cliente", "/faq", "/preguntas-frecuentes",
        "/reclamos", "/terminos",
        # Red
        "/red-agencias", "/agencias", "/sucursales", "/cobertura",
        # EMS
        "/ems-internacional", "/envio-expreso",
        # Otros
        "/mapa-sitio", "/sitemap",
    ]

    # ── Aplicativos específicos con sus URLs (de v2)
    APLICATIVOS_ESPECIFICOS = [
        ("POSTAR - Calculadora",      "https://postar.correos.gob.bo:8104/"),
        ("TrackingBO - Rastreo",      "https://trackingbo.correos.gob.bo:8100/"),
        ("SIRECO - Reclamos",         "https://sireco.correos.gob.bo:8102/"),
        ("UNIENVIO - ECA",            "https://unienvio.correos.gob.bo:8103/"),
        ("GESDO - Carteros",          "https://gesdo.correos.gob.bo:8106/"),
        ("SIREN - Encomiendas",       "https://siren.correos.gob.bo:8107/"),
        ("ULTRAPOST - EMS",           "https://ultrapost.correos.gob.bo:8108/login"),
        ("GESCON - Contratos",        "http://gescon.correos.gob.bo:3005/"),
        ("IPS Web Tracking",          "https://ips.correos.gob.bo/ipswebtracking/"),
        ("Filatelia",                 "https://correos.gob.bo/filatelia/"),
        ("Servicio Postal SP",        "https://correos.gob.bo/sp/"),
        ("Encomienda Postal",         "https://correos.gob.bo/servicio-encomienda-postal/"),
        ("ECA - Correspondencia",     "https://correos.gob.bo/eca/"),
        ("EMS Internacional",         "https://correos.gob.bo/ems/"),
        ("Casillas Postales",         "https://correos.gob.bo/casillas/"),
        ("Chasqui Express",           "https://correos.gob.bo/chasquiexpressbo/"),
    ]

    # ── Tags HTML a eliminar
    TAGS_ELIMINAR = {
        "script", "style", "form", "iframe", "noscript", "svg",
        "button", "input", "select", "textarea", "meta", "link",
        "nav", "header", "footer",
    }

    # ── Selectores CSS para contenido principal
    SELECTORES_CONTENIDO = [
        "main", "article", "#content", ".content", "#main", ".main",
        ".entry-content", ".post-content", ".elementor-section",
        ".elementor-widget-container", ".elementor-text-editor",
        ".wp-block-group", ".container", ".wrapper",
        ".main-content", "#main-content", "body",
    ]

    # ── Valores por defecto para sucursales
    HORARIO_DEFAULT = "Lunes a viernes: 8:30 a 16:30"
    EMAIL_DEFAULT   = "agbc@correos.gob.bo"

    # ── Patrones de detección de tipo de contenido
    PATRONES_HISTORIA = [
        r'hist[oó]ria', r'rese[ñn]a', r'antecedente', r'fundaci[oó]n',
        r'trayectoria', r'tradici[oó]n', r'a[ñn]os de servicio',
    ]
    PATRONES_APLICACION = [
        r'aplicativo', r'aplicaci[oó]n', r'\bapp\b', r'sistema',
        r'plataforma', r'portal', r'servicio en l[ií]nea',
    ]
    PATRONES_SERVICIO = [
        r'servicio', r'env[ií]o', r'correo', r'paquete',
        r'encomienda', r'carta', r'telegrama', r'giro',
        r'casilla', r'apartado', r'filatelia',
    ]
