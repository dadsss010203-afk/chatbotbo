"""
tasks.py — Tareas de mantenimiento (threads locales, sin Celery).
"""
import threading
from core import updater


def rebuild_rag():
    """Reconstruye el indice RAG en un thread separado."""
    def _run():
        from chatbots.general import routes as general_routes
        from core import rag
        rag.inicializar(collection_name="general")
        general_routes.reindexar()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return {"ok": True, "message": "Reindexado iniciado en segundo plano"}


def run_update():
    """Dispara actualizacion de datos en segundo plano."""
    def _run():
        from chatbots.general import routes as general_routes
        updater.disparar_manual(reindexar_fn=general_routes.reindexar)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return {"ok": True, "message": "Actualizacion encolada"}
