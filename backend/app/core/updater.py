"""
core/updater.py
Scheduler de reindexado periodico.
Sin scraper: solo reindexa los JSONs/PDFs existentes en data/.
"""
import os
import sys
import threading
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.background import BackgroundScheduler

_lock = threading.Lock()

estado = {
    "en_proceso": False,
    "ultima_vez": "Nunca",
    "proxima_vez": "—",
    "ultimo_resultado": "Sin ejecucion",
    "scraper_disponible": False,
}

_scheduler = None


def reindexar_desde_json(reindexar_fn=None) -> None:
    """Reconstruye Qdrant desde los JSONs/PDFs en data/."""
    global estado

    if not _lock.acquire(blocking=False):
        print("  Reindexado ya en proceso")
        return

    bolivia = timezone(timedelta(hours=-4))
    estado["en_proceso"] = True

    try:
        print("  Reindexando datos en Qdrant...")
        exito = reindexar_fn() if reindexar_fn else False
        ahora = datetime.now(bolivia)

        if exito:
            estado["ultima_vez"] = ahora.strftime("%d/%m/%Y %H:%M")
            estado["ultimo_resultado"] = "Exitosa"
            print(f"  Reindexado OK — {estado['ultima_vez']}")
        else:
            estado["ultimo_resultado"] = "Reindex fallo"

    except Exception as e:
        estado["ultimo_resultado"] = f"Error: {e}"
        print(f"  Error en reindexado: {e}")
    finally:
        estado["en_proceso"] = False
        _lock.release()


def disparar_manual(reindexar_fn=None) -> None:
    """Lanza reindexado en un hilo separado."""
    threading.Thread(target=reindexar_desde_json, args=(reindexar_fn,), daemon=True).start()


def iniciar_scheduler(reindexar_fn=None, horas: int = None) -> BackgroundScheduler:
    """Inicia scheduler que reindexa cada N horas (default 24)."""
    global _scheduler, estado

    if _scheduler is not None:
        return _scheduler

    intervalo = int(horas or int(os.environ.get("UPDATE_HORAS", "24")))
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        lambda: reindexar_desde_json(reindexar_fn),
        "interval",
        hours=intervalo,
        id="reindex_job",
    )

    job = _scheduler.get_job("reindex_job")
    if job:
        try:
            next_run = getattr(job, "next_run_time", None)
            if next_run:
                bolivia = timezone(timedelta(hours=-4))
                estado["proxima_vez"] = next_run.astimezone(bolivia).strftime("%d/%m/%Y %H:%M")
        except Exception:
            pass

    print(f"  Scheduler reindexado cada {intervalo}h iniciado")
    _scheduler.start()
    return _scheduler


def get_estado() -> dict:
    return dict(estado)
