"""
core/cache.py
Caché distribuida con Redis para embeddings, búsquedas y tarifas.
"""

import os
import json
import hashlib
import pickle
from typing import Any, Optional
import redis

# ─────────────────────────────────────────────
#  CONFIGURACIÓN
# ─────────────────────────────────────────────
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
REDIS_CACHE_TTL = int(os.environ.get("REDIS_CACHE_TTL", "3600"))
REDIS_EMBEDDING_CACHE = os.environ.get("REDIS_EMBEDDING_CACHE", "true").lower() in ("1", "true", "yes")
REDIS_TARIFF_CACHE = os.environ.get("REDIS_TARIFF_CACHE", "true").lower() in ("1", "true", "yes")

try:
    _redis = redis.from_url(REDIS_URL, decode_responses=False)
    _redis.ping()
    _redis_available = True
except Exception as e:
    print(f"⚠️  Redis no disponible: {e}. Cache deshabilitada.")
    _redis = None
    _redis_available = False

# ─────────────────────────────────────────────
#  FUNCIONES HELPER
# ─────────────────────────────────────────────

def _make_key(prefix: str, text: str) -> str:
    """Genera key de caché: prefix:hash."""
    h = hashlib.sha256(text.encode()).hexdigest()[:16]
    return f"{prefix}:{h}"


def get(key: str) -> Optional[Any]:
    """Obtiene valor del cache (bytes o None)."""
    if not _redis_available:
        return None
    try:
        return _redis.get(key)
    except Exception as e:
        print(f"⚠️  Error leyendo caché {key}: {e}")
        return None


def set(key: str, value: Any, ttl: int = REDIS_CACHE_TTL) -> bool:
    """Guarda valor en caché."""
    if not _redis_available:
        return False
    try:
        _redis.setex(key, ttl, value)
        return True
    except Exception as e:
        print(f"⚠️  Error escribiendo caché {key}: {e}")
        return False


def get_json(key: str) -> Optional[dict]:
    """Obtiene y deserializa JSON del caché."""
    val = get(key)
    if val:
        try:
            return json.loads(val.decode("utf-8"))
        except Exception:
            return None
    return None


def set_json(key: str, data: dict, ttl: int = REDIS_CACHE_TTL) -> bool:
    """Serializa y guarda JSON en caché."""
    try:
        return set(key, json.dumps(data).encode("utf-8"), ttl)
    except Exception:
        return False


def get_pickle(key: str) -> Optional[Any]:
    """Obtiene y deserializa pickle del caché."""
    val = get(key)
    if val:
        try:
            return pickle.loads(val)
        except Exception:
            return None
    return None


def set_pickle(key: str, data: Any, ttl: int = REDIS_CACHE_TTL) -> bool:
    """Serializa y guarda pickle en caché."""
    try:
        return set(key, pickle.dumps(data), ttl)
    except Exception:
        return False


def delete(key: str) -> bool:
    """Elimina una clave del caché."""
    if not _redis_available:
        return False
    try:
        _redis.delete(key)
        return True
    except Exception:
        return False


def clear_pattern(pattern: str) -> int:
    """Elimina todas las claves matching un pattern."""
    if not _redis_available:
        return 0
    try:
        keys = _redis.keys(pattern)
        if keys:
            return _redis.delete(*keys)
        return 0
    except Exception:
        return 0


# ─────────────────────────────────────────────
#  CACHÉ DE EMBEDDINGS
# ─────────────────────────────────────────────

def get_embedding(text: str) -> Optional[list]:
    """Obtiene embedding cacheado."""
    if not REDIS_EMBEDDING_CACHE:
        return None
    key = _make_key("emb", text)
    return get_pickle(key)


def set_embedding(text: str, vector: list) -> bool:
    """Guarda embedding en caché."""
    if not REDIS_EMBEDDING_CACHE:
        return False
    key = _make_key("emb", text)
    return set_pickle(key, vector, ttl=86400)  # 24h para embeddings


# ─────────────────────────────────────────────
#  CACHÉ DE BÚSQUEDAS RAG
# ─────────────────────────────────────────────

def get_rag_search(pregunta: str) -> Optional[dict]:
    """Obtiene resultado de búsqueda RAG cacheado."""
    key = _make_key("rag", pregunta)
    return get_json(key)


def set_rag_search(pregunta: str, resultado: dict) -> bool:
    """Guarda resultado de búsqueda RAG."""
    key = _make_key("rag", pregunta)
    return set_json(key, resultado, ttl=3600)


def clear_rag_cache() -> int:
    """Limpia todo el caché RAG (para reindex)."""
    return clear_pattern("rag:*")


# ─────────────────────────────────────────────
#  CACHÉ DE TARIFAS
# ─────────────────────────────────────────────

def get_tariff(scope: str, peso: str, columna: str, xlsx: Optional[str] = None) -> Optional[dict]:
    """Obtiene cálculo de tarifa cacheado."""
    if not REDIS_TARIFF_CACHE:
        return None
    key = _make_key("tariff", f"{scope}:{peso}:{columna}:{xlsx or ''}")
    return get_json(key)


def set_tariff(scope: str, peso: str, columna: str, resultado: dict, xlsx: Optional[str] = None) -> bool:
    """Guarda cálculo de tarifa en caché."""
    if not REDIS_TARIFF_CACHE:
        return False
    key = _make_key("tariff", f"{scope}:{peso}:{columna}:{xlsx or ''}")
    return set_json(key, resultado, ttl=REDIS_CACHE_TTL)


def clear_tariff_cache() -> int:
    """Limpia todo el caché de tarifas."""
    return clear_pattern("tariff:*")


# ─────────────────────────────────────────────
#  INFO Y STATS
# ─────────────────────────────────────────────

def get_stats() -> dict:
    """Obtiene estadísticas del caché Redis."""
    if not _redis_available:
        return {"available": False}
    
    try:
        info = _redis.info()
        return {
            "available": True,
            "used_memory_mb": info.get("used_memory") / (1024**2),
            "keys": _redis.dbsize(),
            "evicted_keys": info.get("evicted_keys", 0),
            "expired_keys": info.get("expired_keys", 0),
        }
    except Exception as e:
        return {"available": False, "error": str(e)}


def health_check() -> bool:
    """Verifica si Redis está disponible."""
    if not _redis_available:
        return False
    try:
        _redis.ping()
        return True
    except Exception:
        return False
