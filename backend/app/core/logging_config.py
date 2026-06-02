"""
core/logging_config.py
Configuracion de logging estructurado JSON para ChatbotBO.
Reemplaza todos los print() por logging con formato JSON.
"""

import os
import json
import logging
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """
    Formateador que emite cada log como una linea JSON.
    Campos: ts, level, mod, fn, msg, + campos extra estructurados.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{record.created % 1:.3f}"[2:] + "Z",
            "level": record.levelname,
            "mod": record.module,
            "fn": record.funcName,
            "msg": record.getMessage(),
        }

        # Agregar campos extra estructurados
        if hasattr(record, "extra_fields"):
            log_entry.update(record.extra_fields)

        # Agregar exception info si existe
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exc"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False)


def init_logging(level: str = None) -> None:
    """
    Inicializa el sistema de logging con formato JSON.
    Llamar UNA SOLA VEZ al arrancar la app.
    """
    log_level = level or os.environ.get("LOG_LEVEL", "INFO").upper()
    numeric_level = getattr(logging, log_level, logging.INFO)

    # Configurar el logger raiz
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remover handlers existentes (evitar duplicados)
    root_logger.handlers.clear()

    # Handler a stdout (Docker-friendly)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(numeric_level)
    handler.setFormatter(JsonFormatter())

    root_logger.addHandler(handler)

    # Reducir verbosidad de librerias externas
    for noisy in ("urllib3", "httpx", "httpcore", "chromadb", "sentence_transformers",
                  "filelock", "transformers", "torch", "apscheduler", "celery",
                  "qdrant_client", "posthog"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Obtiene un logger hijo con el nombre dado.
    Uso: logger = get_logger("rag")
    """
    return logging.getLogger(f"chatbotbo.{name}")
