"""
core/cache.py
Caché distribuida con Redis para embeddings, búsquedas y tarifas.
"""

import os
import json
import hashlib
import pickle
import re
from datetime import datetime, timezone
from typing import Any, Optional
import redis

# ─────────────────────────────────────────────
#  CONFIGURACIÓN
# ─────────────────────────────────────────────
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
REDIS_CACHE_TTL = int(os.environ.get("REDIS_CACHE_TTL", "3600"))
REDIS_EMBEDDING_CACHE = os.environ.get("REDIS_EMBEDDING_CACHE", "true").lower() in ("1", "true", "yes")
REDIS_TARIFF_CACHE = os.environ.get("REDIS_TARIFF_CACHE", "true").lower() in ("1", "true", "yes")
REDIS_RESPONSE_CACHE = os.environ.get("REDIS_RESPONSE_CACHE", "true").lower() in ("1", "true", "yes")
REDIS_RESPONSE_CACHE_TTL = int(os.environ.get("REDIS_RESPONSE_CACHE_TTL", "900"))

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

def _make_key(prefix: str, *parts: str) -> str:
    """Genera key de caché: prefix:hash."""
    material = "||".join(str(p) for p in parts)
    h = hashlib.sha256(material.encode()).hexdigest()[:16]
    return f"{prefix}:{h}"


def _normalize_question(text: str) -> str:
    texto = (text or "").strip().lower()
    texto = re.sub(r"\s+", " ", texto)
    return texto


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
    """Elimina todas las claves matching un pattern usando SCAN."""
    if not _redis_available:
        return 0
    try:
        keys = []
        cursor = 0
        while True:
            cursor, batch = _redis.scan(cursor=cursor, match=pattern, count=1000)
            keys.extend(batch)
            if cursor == 0:
                break
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

def get_rag_search(pregunta: str, preferred_source_types: Optional[list] = None) -> Optional[dict]:
    """Obtiene resultado de búsqueda RAG cacheado."""
    key = _make_key("rag", pregunta, str(sorted(preferred_source_types or [])))
    return get_json(key)


def set_rag_search(pregunta: str, resultado: dict, preferred_source_types: list[str] | None = None) -> bool:
    """Guarda resultado de búsqueda RAG."""
    key = _make_key("rag", pregunta, str(sorted(preferred_source_types or [])))
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
#  CACHÉ DE RESPUESTAS FINALES
# ─────────────────────────────────────────────

def _response_key(pregunta: str, lang: str, skill_id: str, model: str, require_evidence: bool) -> str:
    normalized = _normalize_question(pregunta)
    return _make_key(
        "resp",
        normalized,
        (lang or "").strip().lower(),
        (skill_id or "").strip().lower(),
        (model or "").strip().lower(),
        "evidence_on" if require_evidence else "evidence_off",
    )


def get_response(
    *,
    pregunta: str,
    lang: str,
    skill_id: str = "",
    model: str = "",
    require_evidence: bool = False,
) -> Optional[dict]:
    """Obtiene una respuesta final cacheada por pregunta normalizada."""
    if not REDIS_RESPONSE_CACHE:
        return None
    key = _response_key(pregunta, lang, skill_id, model, require_evidence)
    data = get_json(key)
    if not isinstance(data, dict):
        return None
    return data


def set_response(
    *,
    pregunta: str,
    lang: str,
    skill_id: str = "",
    model: str = "",
    require_evidence: bool = False,
    payload: dict,
    ttl: int = REDIS_RESPONSE_CACHE_TTL,
) -> bool:
    """Guarda respuesta final cacheada para preguntas repetidas."""
    if not REDIS_RESPONSE_CACHE:
        return False
    key = _response_key(pregunta, lang, skill_id, model, require_evidence)
    record = dict(payload or {})
    record["cache_key"] = key
    record["cache_id"] = key.split(":", 1)[1]
    record["question"] = (pregunta or "").strip()
    record["lang"] = (lang or "").strip().lower()
    record["skill_id"] = (skill_id or "").strip()
    record["model"] = (model or "").strip()
    record["require_evidence"] = bool(require_evidence)
    record["created_at"] = datetime.now(timezone.utc).isoformat()
    return set_json(key, record, ttl=max(int(ttl or 0), 60))


def _ttl_seconds(key: str) -> int:
    if not _redis_available:
        return -1
    try:
        return int(_redis.ttl(key))
    except Exception:
        return -1


def list_response_cache(limit: int = 200, q: str = "") -> list[dict]:
    """Lista respuestas cacheadas para auditoría en panel."""
    if not _redis_available:
        return []
    items: list[dict] = []
    query = _normalize_question(q)
    cursor = 0
    max_items = max(1, min(int(limit or 200), 1000))
    try:
        while True:
            cursor, batch = _redis.scan(cursor=cursor, match="resp:*", count=500)
            for raw_key in batch:
                key = raw_key.decode("utf-8") if isinstance(raw_key, bytes) else str(raw_key)
                payload = get_json(key)
                if not isinstance(payload, dict):
                    continue
                question = str(payload.get("question") or "")
                response = str(payload.get("response") or "")
                haystack = _normalize_question(f"{question} {response}")
                if query and query not in haystack:
                    continue
                cache_id = key.split(":", 1)[1] if ":" in key else key
                item = {
                    "cache_id": cache_id,
                    "question": question,
                    "response": response,
                    "lang": payload.get("lang") or "",
                    "skill_id": payload.get("skill_id") or "",
                    "primary_source_type": payload.get("primary_source_type") or "",
                    "created_at": payload.get("created_at") or "",
                    "ttl_seconds": _ttl_seconds(key),
                }
                items.append(item)
                if len(items) >= max_items:
                    break
            if len(items) >= max_items or cursor == 0:
                break
    except Exception:
        return []

    items.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return items


def delete_response_cache(cache_id: str) -> bool:
    """Elimina una respuesta cacheada por id corto."""
    token = (cache_id or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{16}", token):
        return False
    return delete(f"resp:{token}")


def clear_response_cache() -> int:
    """Limpia toda la caché de respuestas finales."""
    return clear_pattern("resp:*")


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


def count_pattern(pattern: str) -> int:
    """Cuenta claves por patrón sin eliminarlas."""
    if not _redis_available:
        return 0
    try:
        total = 0
        cursor = 0
        while True:
            cursor, batch = _redis.scan(cursor=cursor, match=pattern, count=1000)
            total += len(batch)
            if cursor == 0:
                break
        return total
    except Exception:
        return 0


def get_namespace_stats() -> dict:
    """Resumen de caché total y por namespaces usados por el proyecto."""
    stats = get_stats()
    if not stats.get("available"):
        return stats

    rag_keys = count_pattern("rag:*")
    emb_keys = count_pattern("emb:*")
    tariff_keys = count_pattern("tariff:*")
    response_keys = count_pattern("resp:*")
    total_keys = int(stats.get("keys") or 0)
    known_keys = rag_keys + emb_keys + tariff_keys + response_keys

    return {
        **stats,
        "namespaces": {
            "rag": rag_keys,
            "embeddings": emb_keys,
            "tarifas": tariff_keys,
            "respuestas": response_keys,
            "otros": max(total_keys - known_keys, 0),
        },
        "features": {
            "embedding_cache_enabled": REDIS_EMBEDDING_CACHE,
            "tariff_cache_enabled": REDIS_TARIFF_CACHE,
            "response_cache_enabled": REDIS_RESPONSE_CACHE,
            "response_cache_ttl_seconds": REDIS_RESPONSE_CACHE_TTL,
            "default_ttl_seconds": REDIS_CACHE_TTL,
        },
    }


def health_check() -> bool:
    """Verifica si Redis está disponible."""
    if not _redis_available:
        return False
    try:
        _redis.ping()
        return True
    except Exception:
        return False
