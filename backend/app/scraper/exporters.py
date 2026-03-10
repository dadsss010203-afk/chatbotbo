"""
scraper/exporters.py
====================
Guarda todos los resultados del scraping en los archivos de salida.
Centraliza toda la lógica de escritura a disco.
"""

import json
import os
from config import ScraperConfig


def _guardar_json(ruta: str, datos: any, descripcion: str = "") -> None:
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
    if descripcion:
        print(f"    {descripcion}: {ruta}")


def guardar_texto(bloque: str) -> None:
    """Agrega un bloque de texto al archivo principal (modo append)."""
    os.makedirs(ScraperConfig.OUTPUT_DIR, exist_ok=True)
    with open(ScraperConfig.TEXT_FILE, "a", encoding="utf-8") as f:
        f.write(bloque)


def inicializar_texto() -> None:
    """Limpia el archivo de texto al inicio del scraping."""
    os.makedirs(ScraperConfig.OUTPUT_DIR, exist_ok=True)
    open(ScraperConfig.TEXT_FILE, "w", encoding="utf-8").close()


def guardar_sucursales(sucursales: list) -> None:
    _guardar_json(
        ScraperConfig.SUCURSALES_FILE,
        sucursales,
        f"sucursales_contacto.json ({len(sucursales)} sucursales)"
    )


def guardar_secciones(secciones: dict) -> None:
    _guardar_json(
        ScraperConfig.SECCIONES_FILE,
        secciones,
        f"secciones_home.json ({len(secciones)} secciones)"
    )


def guardar_aplicativos(aplicativos: list) -> None:
    resumen = [
        {
            "nombre"         : a["nombre"],
            "url"            : a["url"],
            "estado"         : a["estado"],
            "titulo"         : a["titulo"],
            "funcionalidades": a["funcionalidades"],
            "forms"          : len(a.get("forms", [])),
            "error"          : a.get("error"),
        }
        for a in aplicativos
    ]
    _guardar_json(
        ScraperConfig.APLICATIVOS_FILE,
        {"detalle": aplicativos, "resumen": resumen},
        f"aplicativos_detalle.json ({len(aplicativos)} aplicativos)"
    )


def guardar_servicios(servicios: dict) -> None:
    _guardar_json(
        ScraperConfig.SERVICIOS_FILE,
        servicios,
        f"aplicaciones_servicios.json"
    )


def guardar_historia(historia: list) -> None:
    if historia:
        _guardar_json(
            ScraperConfig.HISTORIA_FILE,
            historia,
            f"historia_institucional.json ({len(historia)} entradas)"
        )


def guardar_noticias(noticias: list) -> None:
    if noticias:
        _guardar_json(
            ScraperConfig.NOTICIAS_FILE,
            noticias,
            f"noticias_eventos.json ({len(noticias)} noticias)"
        )


def guardar_pdfs(pdfs: list) -> None:
    if pdfs:
        _guardar_json(
            ScraperConfig.PDFS_FILE,
            pdfs,
            f"pdfs_contenido.json ({len(pdfs)} PDFs)"
        )


def guardar_enlaces(enlaces: list) -> None:
    if enlaces:
        _guardar_json(
            ScraperConfig.ENLACES_FILE,
            enlaces,
            f"enlaces_interes.json ({len(enlaces)} enlaces)"
        )


def guardar_estadisticas(stats: dict) -> None:
    _guardar_json(
        ScraperConfig.STATS_FILE,
        stats,
        "estadisticas.json"
    )


def imprimir_resumen(stats: dict) -> None:
    print("\n" + "=" * 70)
    print("    SCRAPING COMPLETADO")
    print("=" * 70)
    print(f"    Archivos generados en {ScraperConfig.OUTPUT_DIR}/:")
    archivos = [
        "correos_bolivia.txt", "sucursales_contacto.json",
        "secciones_home.json", "aplicativos_detalle.json",
        "aplicaciones_servicios.json", "historia_institucional.json",
        "noticias_eventos.json", "pdfs_contenido.json", "estadisticas.json",
    ]
    for a in archivos:
        ruta = os.path.join(ScraperConfig.OUTPUT_DIR, a)
        existe = " " if os.path.exists(ruta) else " "
        print(f"      {existe} {a}")
    print(f"\n    Estadísticas:")
    print(f"      Páginas exitosas    : {stats.get('paginas_exitosas', 0)}")
    print(f"      Páginas fallidas    : {stats.get('paginas_fallidas', 0)}")
    print(f"      Caracteres extraídos: {stats.get('caracteres_extraidos', 0):,}")
    print(f"      Sucursales          : {stats.get('sucursales_encontradas', 0)}")
    print(f"      Aplicativos         : {stats.get('aplicativos_encontrados', 0)}")
    print(f"      Servicios           : {stats.get('servicios_encontrados', 0)}")
    print(f"      Noticias            : {stats.get('noticias_encontradas', 0)}")
    print(f"      PDFs descargados    : {stats.get('pdfs_descargados', 0)}")
    print(f"      Historia encontrada : {'Sí' if stats.get('historia_encontrada') else 'No'}")
    print("=" * 70)
