from celery_app import celery
from core import updater
from core.tarifas_skill import ejecutar_tarifa


@celery.task(bind=True, name="chatbotbo.rebuild_rag")
def rebuild_rag_task(self):
    """Reconstruye el índice RAG en segundo plano."""
    try:
        from chatbots.general import routes as general_routes

        success = general_routes.reindexar()
        return {"ok": bool(success), "reindexed": bool(success)}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=10, max_retries=2)


@celery.task(bind=True, name="chatbotbo.calculate_tariff")
def calculate_tariff_task(self, scope: str, peso: str, columna: str, xlsx: str | None = None):
    """Calcula una tarifa de forma asíncrona."""
    return ejecutar_tarifa(peso=peso, columna=columna, scope=scope, xlsx=xlsx)


@celery.task(bind=True, name="chatbotbo.run_update")
def run_update_task(self):
    """Dispara una actualización de datos/índice en segundo plano."""
    try:
        from chatbots.general import routes as general_routes

        updater.disparar_manual(reindexar_fn=general_routes.reindexar)
        return {"ok": True, "message": "Actualización encolada"}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=10, max_retries=2)
