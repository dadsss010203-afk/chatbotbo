from celery_app import celery
from core import updater


@celery.task(bind=True, name="chatbotbo.rebuild_rag")
def rebuild_rag_task(self):
    """Reconstruye el índice RAG en segundo plano."""
    try:
        from chatbots.general import routes as general_routes
        from core import rag

        # Initialize RAG before reindexing
        rag.inicializar(collection_name="general")

        success = general_routes.reindexar()
        return {"ok": bool(success), "reindexed": bool(success)}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=10, max_retries=2)


@celery.task(bind=True, name="chatbotbo.run_update")
def run_update_task(self):
    """Dispara una actualización de datos/índice en segundo plano."""
    try:
        from chatbots.general import routes as general_routes

        updater.disparar_manual(reindexar_fn=general_routes.reindexar)
        return {"ok": True, "message": "Actualización encolada"}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=10, max_retries=2)
