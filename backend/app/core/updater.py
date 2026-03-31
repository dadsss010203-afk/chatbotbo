"""
core/updater.py
Actualización automática: llama a scraper/runner.py y reindexea ChromaDB.
Compartido por todos los chatbots.
"""

import os
import sys
import threading
from datetime import datetime, timezone, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

# ─────────────────────────────────────────────
#  CONFIGURACIÓN
# ─────────────────────────────────────────────
HORAS_ACTUALIZACION = int(os.environ.get("HORAS_ACTUALIZACION", "24"))

# ─────────────────────────────────────────────
#  ESTADO GLOBAL
# ─────────────────────────────────────────────
estado = {
    "en_proceso"      : False,
    "ultima_vez"      : None,
    "proxima_vez"     : None,
    "ultimo_resultado": "Pendiente",
}

_lock      = threading.Lock()
_scheduler = None


# ─────────────────────────────────────────────
#  ACTUALIZACIÓN
# ─────────────────────────────────────────────

def actualizar_bd(reindexar_fn=None) -> None:
    """
    Ejecuta scraper/runner.py → ScraperRunner.run()
    que genera: correos_bolivia.txt, sucursales_contacto.json, secciones_home.json
    Luego llama a reindexar_fn() para actualizar ChromaDB.
    """
    global estado

    if not _lock.acquire(blocking=False):
        print("  Actualización ya en proceso")
        return

    bolivia = timezone(timedelta(hours=-4))
    estado["en_proceso"] = True

    try:
        print("  Ejecutando scraper...")

        # Agregar scraper/ al path
        scraper_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "scraper")
        )
        if scraper_path not in sys.path:
            sys.path.insert(0, scraper_path)

        from runner import ScraperRunner
        ScraperRunner().run()
        print("  Scraper completado")

        if reindexar_fn:
            print("  Reindexando en ChromaDB...")
            exito = reindexar_fn()
            ahora = datetime.now(bolivia)
            if exito:
                estado["ultima_vez"]       = ahora.strftime("%d/%m/%Y %H:%M")
                estado["ultimo_resultado"] = "  Exitosa"
                print(f"  Reindexado OK — {estado['ultima_vez']}")
            else:
                estado["ultimo_resultado"] = "  Reindex falló"
        else:
            ahora = datetime.now(bolivia)
            estado["ultima_vez"]       = ahora.strftime("%d/%m/%Y %H:%M")
            estado["ultimo_resultado"] = "  Scraper OK"

    except ImportError as e:
        estado["ultimo_resultado"] = f"  Scraper no encontrado: {e}"
        print(f"  {e} — verifica que exista scraper/runner.py")
    except Exception as e:
        estado["ultimo_resultado"] = f"  {e}"
        print(f"  Error en actualización: {e}")
    finally:
        estado["en_proceso"] = False
        _lock.release()


def disparar_manual(reindexar_fn=None) -> None:
    """Lanza la actualización en un hilo separado. Usar desde /api/actualizar"""
    threading.Thread(target=actualizar_bd, args=(reindexar_fn,), daemon=True).start()


# ─────────────────────────────────────────────
#  SCHEDULER
# ─────────────────────────────────────────────

def iniciar_scheduler(reindexar_fn=None, horas: int = None) -> BackgroundScheduler:
    """Inicia el scheduler que actualiza cada N horas."""
    global _scheduler

    intervalo  = horas or HORAS_ACTUALIZACION
    _scheduler = BackgroundScheduler(timezone="America/La_Paz")
    _scheduler.add_job(
        func          = lambda: actualizar_bd(reindexar_fn),
        trigger       = "interval",
        hours         = intervalo,
        id            = "actualizar_bd",
        max_instances = 1,
    )
    _scheduler.start()

    prox = _scheduler.get_job("actualizar_bd").next_run_time
    estado["proxima_vez"] = prox.strftime("%d/%m/%Y %H:%M") if prox else "—"
    print(f"⏰ Scheduler: cada {intervalo}h | próxima: {estado['proxima_vez']}")
    return _scheduler


def detener_scheduler() -> None:
    """Detiene el scheduler al cerrar la app."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown()
        print("   Scheduler detenido")


def get_estado() -> dict:
    """Devuelve el estado para /api/status"""
    return {
        "en_proceso"      : estado["en_proceso"],
        "ultima_vez"      : estado["ultima_vez"]       or "Nunca",
        "proxima_vez"     : estado["proxima_vez"]      or "—",
        "ultimo_resultado": estado["ultimo_resultado"],
        "cada_horas"      : HORAS_ACTUALIZACION,
    }
