"""
core/rag.py
Motor RAG: embeddings, indexado y búsqueda en ChromaDB.
Compartido por todos los chatbots.
"""

import os
import re
import hashlib
import uuid
from collections import defaultdict
from tqdm import tqdm
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from core.cache import get_embedding, set_embedding, get_rag_search, set_rag_search

os.environ.setdefault("ANONYMIZED_TELEMETRY", "FALSE")

try:
    import posthog  # type: ignore

    _original_capture = getattr(posthog, "capture", None)

    if callable(_original_capture):
        def _safe_capture(*args, **kwargs):
            try:
                return _original_capture(*args, **kwargs)
            except TypeError:
                try:
                    distinct_id = args[0] if len(args) > 0 else kwargs.get("distinct_id")
                    event = args[1] if len(args) > 1 else kwargs.get("event")
                    properties = args[2] if len(args) > 2 else kwargs.get("properties")
                    return _original_capture(
                        distinct_id=distinct_id,
                        event=event,
                        properties=properties,
                    )
                except Exception:
                    return None
            except Exception:
                return None

        posthog.capture = _safe_capture
except Exception:
    pass

# ─────────────────────────────────────────────
#  CONFIGURACIÓN
# ─────────────────────────────────────────────
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
CHROMA_PATH     = os.environ.get("CHROMA_PATH",     "chroma_db")
CHUNK_SIZE         = int(os.environ.get("CHUNK_SIZE",   "450"))
CHUNK_OVERLAP      = int(os.environ.get("CHUNK_OVERLAP", "80"))
BATCH_SIZE         = int(os.environ.get("BATCH_SIZE",   "500"))
N_RESULTADOS       = int(os.environ.get("N_RESULTADOS",  "3"))
MAX_CONTEXT_CHARS  = int(os.environ.get("MAX_CONTEXT_CHARS", "1800"))
MAX_CONTEXT_TOKENS = int(os.environ.get("MAX_CONTEXT_TOKENS", "900"))
MIN_CHUNK_CHARS    = int(os.environ.get("MIN_CHUNK_CHARS", "40"))
RAG_VECTOR_STORE   = os.environ.get("RAG_VECTOR_STORE", "qdrant").lower()
QDRANT_URL         = os.environ.get("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION  = os.environ.get("QDRANT_COLLECTION", "correos")
USE_TRITON         = os.environ.get("USE_TRITON", "false").lower() in ("1", "true", "yes")
TRITON_URL         = os.environ.get("TRITON_URL", "http://triton:8000")
TRITON_EMBEDDING_MODEL = os.environ.get("TRITON_EMBEDDING_MODEL", "embedding_model")

# ─────────────────────────────────────────────
#  ESTADO GLOBAL
# ─────────────────────────────────────────────
_embedder   = None
_client     = None
_collection = None
_collection_name = None


def _use_qdrant() -> bool:
    return RAG_VECTOR_STORE == "qdrant"


def _use_triton() -> bool:
    return USE_TRITON and bool(TRITON_URL)


def _qdrant_client() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL, prefer_grpc=False, timeout=30)


def _qdrant_point_id(raw_id: str) -> str:
    """
    Qdrant reciente acepta IDs uint64 o UUID.
    Convertimos IDs legibles (txt_0, pdf_x_1, etc.) a UUID determinístico.
    """
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, str(raw_id)))


# ─────────────────────────────────────────────
#  INICIALIZACIÓN
# ─────────────────────────────────────────────

def inicializar(chroma_path: str = None, embedding_model: str = None, collection_name: str = "correos"):
    """
    Carga el modelo de embeddings y conecta a ChromaDB.
    Llamar UNA SOLA VEZ al arrancar el chatbot.

    Args:
        chroma_path      : ruta donde guardar la BD vectorial
        embedding_model  : nombre del modelo sentence-transformers
        collection_name  : nombre de la colección en ChromaDB (uno por chatbot)
    """
    global _embedder, _client, _collection, _collection_name, RAG_VECTOR_STORE, _chroma_path

    modelo = embedding_model or EMBEDDING_MODEL
    path   = chroma_path     or CHROMA_PATH

    print(f"  Cargando modelo de embeddings: {modelo}")
    # si hay token de HF en el entorno, pásalo para evitar límites de descarga
    hf_token = os.environ.get("HF_TOKEN")
    kwargs = {}
    if hf_token:
        kwargs["use_auth_token"] = hf_token
    # evitar advertencias si el checkpoint no coincide exactamente
    # SentenceTransformer constructor usa `model_kwargs`, no `auto_model_kwargs`.
    kwargs["model_kwargs"] = {"ignore_mismatched_sizes": True}

    _embedder = SentenceTransformer(modelo, **kwargs)
    print(" Modelo de embeddings cargado (con ignore_mismatched_sizes)")

    if _use_qdrant():
        try:
            # Intentar conectar a Qdrant con timeout corto
            import socket
            host = QDRANT_URL.replace("http://", "").replace("https://", "").split(":")[0]
            port = int(QDRANT_URL.replace("http://", "").replace("https://", "").split(":")[1]) if ":" in QDRANT_URL else 6333
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)  # 2 segundos timeout
            result = sock.connect_ex((host, port))
            sock.close()
            
            if result != 0:
                raise Exception(f"Qdrant no responde en {QDRANT_URL}")
            
            client = QdrantClient(url=QDRANT_URL, timeout=30)
            collections = client.get_collections().collections
            collection_names = [c.name for c in collections]
            if collection_name not in collection_names:
                client.create_collection(
                    collection_name=collection_name,
                    vectors_config=qmodels.VectorParams(
                        size=_embedder.encode([""], show_progress_bar=False).shape[1],
                        distance=qmodels.Distance.COSINE
                    )
                )
                print(f" Qdrant collection '{collection_name}' creada con vector_size={_embedder.encode([''], show_progress_bar=False).shape[1]}")
            _collection = collection_name
            _collection_name = collection_name
            _client = client
            count = client.count(collection_name=collection_name).count
            print(f" Qdrant listo en '{QDRANT_URL}' ({count} chunks en '{collection_name}')")
        except Exception as e:
            print(f" ⚠️  Qdrant no disponible ({e}), usando ChromaDB local")
            RAG_VECTOR_STORE = "chroma"
            import chromadb
            from chromadb.config import Settings
            client      = chromadb.PersistentClient(
                path=path,
                settings=Settings(anonymized_telemetry=False),
            )
            _client = client
            _collection_name = collection_name
            def embed_function(texts):
                return _embedder.encode(texts, show_progress_bar=False).tolist()
            _collection = client.get_or_create_collection(name=collection_name, embedding_function=embed_function)
            print(f" ChromaDB listo en '{path}' ({_collection.count()} chunks en '{collection_name}')")
    else:
        import chromadb
        from chromadb.config import Settings
        client      = chromadb.PersistentClient(
            path=path,
            settings=Settings(anonymized_telemetry=False),
        )
        _client = client
        _collection_name = collection_name
        def embed_function(texts):
            return _embedder.encode(texts, show_progress_bar=False).tolist()
        _collection = client.get_or_create_collection(name=collection_name, embedding_function=embed_function)
        print(f" ChromaDB listo en '{path}' ({_collection.count()} chunks en '{collection_name}')")

    return _embedder, _collection


def reset_collection() -> bool:
    """Elimina y recrea la colección actual del store de vectores."""
    global _collection

    if _client is None or not _collection_name:
        raise RuntimeError("RAG no inicializado. Llama a rag.inicializar() primero.")

    if _use_qdrant():
        try:
            _client.delete_collection(collection_name=_collection_name)
        except Exception:
            pass
        vector_size = _embedder.encode([""], show_progress_bar=False).shape[1]
        _client.recreate_collection(
            collection_name=_collection_name,
            vectors_config=qmodels.VectorParams(size=vector_size, distance=qmodels.Distance.COSINE),
        )
        _collection = _collection_name
    else:
        try:
            _client.delete_collection(name=_collection_name)
        except Exception:
            pass
        _collection = _client.get_or_create_collection(name=_collection_name)
    return True


def get_collection():
    if _collection is None:
        raise RuntimeError("RAG no inicializado. Llama a rag.inicializar() primero.")
    return _collection


def get_embedder():
    if _embedder is None:
        raise RuntimeError("RAG no inicializado. Llama a rag.inicializar() primero.")
    return _embedder


def total_chunks() -> int:
    """Devuelve la cantidad de chunks indexados actualmente."""
    if _use_qdrant():
        return _client.count(collection_name=_collection_name).count
    return get_collection().count()


def pdf_chunk_counts() -> dict:
    """
    Devuelve conteos exactos de chunks PDF actualmente indexados en el vector store.

    Retorna:
      {
        "by_pdf_key": { "<pdf_key>": int, ... },
        "by_source_name": { "<nombre_pdf>": int, ... },
      }
    """
    by_pdf_key = defaultdict(int)
    by_source_name = defaultdict(int)

    try:
        if _use_qdrant():
            if _client is None or not _collection_name:
                return {"by_pdf_key": {}, "by_source_name": {}}

            filtro_pdf = qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="source_type",
                        match=qmodels.MatchValue(value="pdf"),
                    )
                ]
            )
            offset = None
            while True:
                points, next_offset = _client.scroll(
                    collection_name=_collection_name,
                    scroll_filter=filtro_pdf,
                    limit=1000,
                    with_payload=True,
                    with_vectors=False,
                    offset=offset,
                )
                if not points:
                    break

                for point in points:
                    payload = point.payload or {}
                    pdf_key = str(payload.get("pdf_key") or "").strip()
                    source_name = str(payload.get("source_name") or payload.get("source_label") or "").strip()
                    if pdf_key:
                        by_pdf_key[pdf_key] += 1
                    if source_name:
                        by_source_name[source_name] += 1

                if next_offset is None:
                    break
                offset = next_offset
        else:
            existentes = get_collection().get(include=["metadatas"])
            metas = existentes.get("metadatas") or []
            for meta in metas:
                if not isinstance(meta, dict):
                    continue
                if str(meta.get("source_type") or "").strip() != "pdf":
                    continue
                pdf_key = str(meta.get("pdf_key") or "").strip()
                source_name = str(meta.get("source_name") or meta.get("source_label") or "").strip()
                if pdf_key:
                    by_pdf_key[pdf_key] += 1
                if source_name:
                    by_source_name[source_name] += 1
    except Exception:
        return {"by_pdf_key": {}, "by_source_name": {}}

    return {
        "by_pdf_key": dict(by_pdf_key),
        "by_source_name": dict(by_source_name),
    }


# ─────────────────────────────────────────────
#  CHUNKING
# ─────────────────────────────────────────────

def _normalizar_texto(texto: str) -> str:
    texto = (texto or "").replace("\r\n", "\n").replace("\r", "\n")
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    # limpiar ruido típico de scraping/PDF para mejorar recuperación semántica
    lineas_limpias = []
    noise_exact = {
        "comparte",
        "compartir",
        "menu",
        "inicio",
        "home",
        "leer mas",
        "leer más",
    }
    for linea in texto.splitlines():
        l = linea.strip()
        if not l:
            continue
        l_norm = re.sub(r"\s+", " ", l.lower())
        if l_norm in noise_exact:
            continue
        if re.fullmatch(r"[#@|/\\\-\_=*.,:;~\[\](){}0-9\s]+", l):
            continue
        if re.fullmatch(r"p[áa]gina\s+\d+", l_norm):
            continue
        if l_norm.startswith("http://") or l_norm.startswith("https://"):
            continue
        if len(l_norm) <= 2:
            continue
        lineas_limpias.append(l)
    texto = "\n".join(lineas_limpias)
    return texto.strip()


def _dividir_bloque_largo(texto: str, size: int, overlap: int) -> list[str]:
    partes = []
    resto = texto.strip()

    while resto:
        if len(resto) <= size:
            partes.append(resto)
            break

        ventana = resto[:size]
        corte = max(
            ventana.rfind("\n"),
            ventana.rfind(". "),
            ventana.rfind("; "),
            ventana.rfind(", "),
            ventana.rfind(" "),
        )

        if corte < size * 0.45:
            corte = size

        chunk = resto[:corte].strip()
        if chunk:
            partes.append(chunk)

        siguiente = max(corte - overlap, 1)
        resto = resto[siguiente:].strip()

    return partes


def _segmentar_texto(texto: str, size: int, overlap: int) -> list[str]:
    texto_norm = _normalizar_texto(texto)
    # separar por saltos de párrafo y por encabezados estructurales para evitar
    # mezclar demasiados temas en un único chunk.
    bloques = [
        b.strip()
        for b in re.split(
            r"\n\s*\n|(?=^#{1,3}\s)|(?=^FUENTE:)|(?=^TITULO:)|(?=^TIPOS:)|(?=^\[Fuente:)",
            texto_norm,
            flags=re.MULTILINE,
        )
        if b.strip()
    ]
    segmentos = []

    for bloque in bloques:
        if len(bloque) <= size:
            segmentos.append(bloque)
        else:
            segmentos.extend(_dividir_bloque_largo(bloque, size=size, overlap=overlap))

    if not segmentos and texto_norm.strip():
        segmentos = _dividir_bloque_largo(texto_norm.strip(), size=size, overlap=overlap)

    return segmentos


def _normalizar_metadata(metadata_base: dict | None, prefijo: str) -> dict:
    meta = dict(metadata_base or {})
    # metadatos mínimos obligatorios para trazabilidad homogénea
    meta.setdefault("source_type", "unknown")
    meta.setdefault("source_name", meta.get("source_label") or prefijo)
    meta.setdefault("source_label", meta.get("source_name") or prefijo)
    meta.setdefault("source_url", "")
    meta.setdefault("source_path", "")
    meta.setdefault("source_page", "")
    return meta


def _approximate_tokens(texto: str) -> int:
    """Estimación rápida de tokens a partir de palabras y puntuación."""
    if not texto:
        return 0
    return len(re.findall(r"\w+|[^\s\w]", texto))


def _truncate_context_by_tokens(contexto_partes: list[str], max_tokens: int) -> str:
    contexto = []
    total = 0
    for parte in contexto_partes:
        tokens = _approximate_tokens(parte)
        if total + tokens > max_tokens:
            break
        contexto.append(parte)
        total += tokens
    if not contexto and contexto_partes:
        # Si una sola parte excede el límite, recortamos el texto directamente.
        texto = contexto_partes[0]
        palabras = texto.split()
        limite = max(1, int(len(palabras) * max_tokens / max(1, _approximate_tokens(texto))))
        return " ".join(palabras[:limite])
    return "\n\n".join(contexto)


def estimate_tokens(texto: str) -> int:
    """Estimación rápida de tokens para texto compartido por el backend."""
    return _approximate_tokens(texto)


def documento_a_chunks(
    texto: str,
    prefijo: str = "txt",
    chunk_size: int = None,
    metadata_base: dict | None = None,
) -> tuple[list, list, list]:
    """
    Convierte un documento en chunks más estables semánticamente y con metadatos.

    Returns:
        (chunks, chunk_ids, metadatas)
    """
    size = chunk_size or CHUNK_SIZE
    overlap = min(CHUNK_OVERLAP, max(size // 3, 40))
    metadata_base = _normalizar_metadata(metadata_base, prefijo)

    chunks = []
    ids = []
    metadatas = []

    for idx, chunk in enumerate(_segmentar_texto(texto, size=size, overlap=overlap)):
        limpio = chunk.strip()
        if len(limpio) < MIN_CHUNK_CHARS:
            continue

        chunk_id = f"{prefijo}_{idx}"
        meta = dict(metadata_base)
        meta.update(
            {
                "chunk_index": idx,
                "chunk_chars": len(limpio),
                "source_id": prefijo,
                "content_hash": hashlib.sha1(limpio.encode("utf-8")).hexdigest()[:16],
            }
        )
        chunks.append(limpio)
        ids.append(chunk_id)
        metadatas.append(meta)

    return chunks, ids, metadatas


def texto_a_chunks(texto: str, prefijo: str = "txt", chunk_size: int = None) -> tuple[list, list]:
    """
    Divide un texto largo en chunks con solapamiento de 100 chars.

    Args:
        texto      : texto completo a dividir
        prefijo    : prefijo para los IDs (ej: "txt", "suc")
        chunk_size : tamaño de cada chunk (por defecto CHUNK_SIZE del .env)

    Returns:
        (chunks, chunk_ids)
    """
    chunks, ids, _ = documento_a_chunks(texto, prefijo=prefijo, chunk_size=chunk_size)
    return chunks, ids


def archivo_a_chunks(filepath: str, prefijo: str = "txt") -> tuple[list, list]:
    """
    Lee un archivo .txt y lo convierte en chunks listos para indexar.

    Returns:
        (chunks, chunk_ids) o ([], []) si el archivo no existe.
    """
    if not os.path.exists(filepath):
        print(f"   Archivo no encontrado: {filepath}")
        return [], []

    with open(filepath, "r", encoding="utf-8") as f:
        texto = f.read()

    chunks, ids, _ = documento_a_chunks(
        texto,
        prefijo=prefijo,
        metadata_base={"source_type": "file", "source_path": filepath},
    )
    print(f"   → {len(chunks)} chunks de '{filepath}'")
    return chunks, ids


def archivo_a_documentos(
    filepath: str,
    prefijo: str = "txt",
    metadata_base: dict | None = None,
) -> tuple[list, list, list]:
    """
    Lee un archivo y devuelve chunks con metadatos listos para indexación.
    """
    if not os.path.exists(filepath):
        print(f"   Archivo no encontrado: {filepath}")
        return [], [], []

    with open(filepath, "r", encoding="utf-8") as f:
        texto = f.read()

    metadatos = {"source_type": "file", "source_path": filepath}
    if metadata_base:
        metadatos.update(metadata_base)

    chunks, ids, docs_meta = documento_a_chunks(texto, prefijo=prefijo, metadata_base=metadatos)
    print(f"   → {len(chunks)} chunks de '{filepath}'")
    return chunks, ids, docs_meta


# ─────────────────────────────────────────────
#  INDEXADO
# ─────────────────────────────────────────────

def indexar(chunks: list, chunk_ids: list, metadatas: list | None = None, limpiar: bool = True) -> bool:
    """
    Indexa una lista de chunks en ChromaDB.

    Args:
        chunks     : lista de textos a indexar
        chunk_ids  : lista de IDs únicos para cada chunk
        limpiar    : si True, borra los chunks anteriores primero

    Returns:
        True si el indexado fue exitoso, False si no había chunks.
    """
    col = get_collection()
    emb = get_embedder()

    if not chunks:
        print("   Sin chunks para indexar")
        return False

    # deduplicar por huella de contenido para evitar sobreindexar texto repetido
    dedup_chunks = []
    dedup_ids = []
    dedup_meta = [] if metadatas else None
    seen_hashes = set()
    for idx, chunk in enumerate(chunks):
        texto = _normalizar_texto(chunk)
        if not texto:
            continue
        c_hash = hashlib.sha1(texto.lower().encode("utf-8")).hexdigest()[:16]
        if c_hash in seen_hashes:
            continue
        seen_hashes.add(c_hash)
        dedup_chunks.append(texto)
        dedup_ids.append(chunk_ids[idx] if idx < len(chunk_ids) else f"chunk_{len(dedup_ids)}")
        if dedup_meta is not None:
            meta = metadatas[idx] if idx < len(metadatas) else {}
            meta = _normalizar_metadata(meta, dedup_ids[-1])
            meta["content_hash"] = c_hash
            dedup_meta.append(meta)

    if len(dedup_chunks) != len(chunks):
        print(f"   🔁 Dedupe de indexación: {len(chunks)} → {len(dedup_chunks)} chunks únicos")

    chunks = dedup_chunks
    chunk_ids = dedup_ids
    metadatas = dedup_meta

    if not chunks:
        print("   Sin chunks útiles después de deduplicar")
        return False

    # Limpiar BD anterior
    if limpiar:
        if _use_qdrant():
            try:
                reset_collection()
                print("   🗑️  Colección Qdrant reiniciada")
            except Exception as e:
                print(f"      Error al reiniciar Qdrant: {e}")
        else:
            try:
                todos = col.get()
                if todos and todos.get("ids"):
                    col.delete(ids=todos["ids"])
                    print(f"   🗑️  {len(todos['ids'])} chunks anteriores eliminados")
            except Exception as e:
                print(f"      Error al limpiar: {e}")

    # Calcular embeddings
    print(f"  {len(chunks)} chunks — calculando embeddings...")
    embeddings  = emb.encode(chunks, show_progress_bar=False, batch_size=64)
    total_lotes = (len(chunks) + BATCH_SIZE - 1) // BATCH_SIZE

    # Insertar en lotes
    for i in tqdm(range(0, len(chunks), BATCH_SIZE), total=total_lotes, desc="Indexando"):
        batch_chunks = chunks[i:i + BATCH_SIZE]
        batch_ids = chunk_ids[i:i + BATCH_SIZE]
        batch_embeddings = embeddings[i:i + BATCH_SIZE].tolist()
        batch_metadata = metadatas[i:i + BATCH_SIZE] if metadatas else None

        if _use_qdrant():
            points = []
            for idx_chunk, chunk_id in enumerate(batch_ids):
                payload = {"text": batch_chunks[idx_chunk]}
                if batch_metadata:
                    payload.update(batch_metadata[idx_chunk] or {})
                points.append(
                    qmodels.PointStruct(
                        id=_qdrant_point_id(chunk_id),
                        vector=batch_embeddings[idx_chunk],
                        payload=payload,
                    )
                )
            _client.upsert(collection_name=_collection_name, points=points)
        else:
            payload = {
                "documents": batch_chunks,
                "embeddings": batch_embeddings,
                "ids": batch_ids,
            }
            if batch_metadata:
                payload["metadatas"] = batch_metadata
            col.add(**payload)

    if _use_qdrant():
        print(f" {len(chunks)} chunks indexados en Qdrant")
    else:
        print(f" {len(chunks)} chunks indexados en ChromaDB")
    return True


def reemplazar_por_source_type(
    source_type: str,
    chunks: list,
    chunk_ids: list,
    metadatas: list | None = None,
) -> dict:
    """
    Reemplaza de forma incremental todos los documentos de un source_type.
    Útil para reindexar solo PDFs sin reconstruir todo el RAG.
    """
    col = get_collection()
    emb = get_embedder()

    # 1) localizar y eliminar IDs existentes del source_type
    removed = 0
    try:
        if _use_qdrant():
            filter_expr = qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="source_type",
                        match=qmodels.MatchValue(value=source_type),
                    )
                ]
            )
            _client.delete(collection_name=_collection_name, filter=filter_expr)
            removed = -1
        else:
            existentes = col.get(include=["metadatas"])
            ids = existentes.get("ids") or []
            metas = existentes.get("metadatas") or []
            ids_a_borrar = []
            for idx, item_id in enumerate(ids):
                meta = metas[idx] if idx < len(metas) else {}
                if (meta or {}).get("source_type") == source_type:
                    ids_a_borrar.append(item_id)
            if ids_a_borrar:
                col.delete(ids=ids_a_borrar)
                removed = len(ids_a_borrar)
    except Exception as exc:
        print(f"   Error eliminando subset '{source_type}': {exc}")

    # 2) insertar subset nuevo
    if not chunks:
        return {"ok": True, "removed": removed, "added": 0}

    dedup_chunks = []
    dedup_ids = []
    dedup_meta = [] if metadatas else None
    seen_hashes = set()
    for idx, chunk in enumerate(chunks):
        texto = _normalizar_texto(chunk)
        if not texto:
            continue
        c_hash = hashlib.sha1(texto.lower().encode("utf-8")).hexdigest()[:16]
        if c_hash in seen_hashes:
            continue
        seen_hashes.add(c_hash)
        dedup_chunks.append(texto)
        dedup_ids.append(chunk_ids[idx] if idx < len(chunk_ids) else f"{source_type}_{len(dedup_ids)}")
        if dedup_meta is not None:
            meta = metadatas[idx] if idx < len(metadatas) else {}
            meta = _normalizar_metadata(meta, dedup_ids[-1])
            meta["content_hash"] = c_hash
            dedup_meta.append(meta)

    if not dedup_chunks:
        return {"ok": True, "removed": removed, "added": 0}

    print(f"  Subset '{source_type}': insertando {len(dedup_chunks)} chunks...")
    embeddings = emb.encode(dedup_chunks, show_progress_bar=False, batch_size=64)
    total_lotes = (len(dedup_chunks) + BATCH_SIZE - 1) // BATCH_SIZE
    for i in tqdm(range(0, len(dedup_chunks), BATCH_SIZE), total=total_lotes, desc=f"Indexando {source_type}"):
        batch_chunks = dedup_chunks[i : i + BATCH_SIZE]
        batch_ids = dedup_ids[i : i + BATCH_SIZE]
        batch_embeddings = embeddings[i : i + BATCH_SIZE].tolist()
        batch_meta = dedup_meta[i : i + BATCH_SIZE] if dedup_meta else None

        if _use_qdrant():
            points = []
            for idx_chunk, chunk_id in enumerate(batch_ids):
                payload = {"text": batch_chunks[idx_chunk]}
                if batch_meta:
                    payload.update(batch_meta[idx_chunk] or {})
                points.append(
                    qmodels.PointStruct(
                        id=_qdrant_point_id(chunk_id),
                        vector=batch_embeddings[idx_chunk],
                        payload=payload,
                    )
                )
            _client.upsert(collection_name=_collection_name, points=points)
        else:
            payload = {
                "documents": batch_chunks,
                "embeddings": batch_embeddings,
                "ids": batch_ids,
            }
            if batch_meta:
                payload["metadatas"] = batch_meta
            col.add(**payload)

    return {"ok": True, "removed": removed, "added": len(dedup_chunks)}


# ─────────────────────────────────────────────
#  BÚSQUEDA
# ─────────────────────────────────────────────

def _prioridad_fuente(source_type: str) -> int:
    prioridades = {
        "pdf": 6,
        "history": 5,
        "branch": 5,
        "section": 4,
        "web_main": 4,
        "service": 4,
        "json_data": 3,
        "file": 2,
    }
    return prioridades.get(source_type or "", 1)


def _formatear_fuente(metadata: dict | None) -> str:
    metadata = metadata or {}
    source_type = metadata.get("source_type")
    label = metadata.get("source_label") or metadata.get("source_name") or metadata.get("source_path")

    tipo = {
        "history": "Historia",
        "branch": "Sucursal",
        "section": "Seccion",
        "web_main": "Sitio web",
        "json_data": "Datos JSON",
        "pdf": "PDF",
        "file": "Archivo",
    }.get(source_type, "Fuente")

    if label:
        return f"{tipo}: {label}"
    return tipo


def _source_preference_bonus(source_type: str, preferred_source_types: list[str] | None) -> float:
    if not preferred_source_types:
        return 0.0
    try:
        idx = preferred_source_types.index(source_type or "")
    except ValueError:
        return 0.0
    return max(0.22 - (idx * 0.06), 0.04)


def buscar(
    pregunta: str,
    n_resultados: int = None,
    preferred_source_types: list[str] | None = None,
) -> dict:
    col = get_collection()
    emb = get_embedder()
    n = n_resultados or N_RESULTADOS
    n_query = min(max(n * 5, 8), 24)

    # Cache de búsqueda RAG completa para preguntas repetidas
    cached_search = get_rag_search(pregunta, preferred_source_types)
    if cached_search is not None:
        return cached_search

    # Pre-calcular embedding para evitar timeout en ChromaDB
    cached_vector = get_embedding(pregunta)
    if cached_vector is not None:
        vector = cached_vector
    else:
        vector = emb.encode([pregunta]).tolist()
        set_embedding(pregunta, vector)

    if _use_qdrant():
        qdrant_limit = min(n_query, max(_client.count(collection_name=_collection_name).count, 1))

        def _qdrant_search_by_type(source_type: str | None = None):
            kwargs = {
                "collection_name": _collection_name,
                "query_vector": vector[0],
                "limit": qdrant_limit,
                "with_payload": True,
            }
            if source_type:
                kwargs["query_filter"] = qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="source_type",
                            match=qmodels.MatchValue(value=source_type),
                        )
                    ]
                )
            return _client.search(**kwargs)

        search_results = []
        seen_ids = set()
        # 1) Traer primero candidatos de fuentes preferidas (si hay)
        if preferred_source_types:
            for st in preferred_source_types:
                try:
                    for hit in _qdrant_search_by_type(st):
                        hit_id = str(getattr(hit, "id", ""))
                        if hit_id and hit_id in seen_ids:
                            continue
                        if hit_id:
                            seen_ids.add(hit_id)
                        search_results.append(hit)
                except Exception:
                    continue

        # 2) Completar con búsqueda global para no perder cobertura
        for hit in _qdrant_search_by_type(None):
            hit_id = str(getattr(hit, "id", ""))
            if hit_id and hit_id in seen_ids:
                continue
            if hit_id:
                seen_ids.add(hit_id)
            search_results.append(hit)
            if len(search_results) >= qdrant_limit:
                break

        documents = []
        metadatas = []
        distances = []
        for hit in search_results:
            payload = hit.payload or {}
            documents.append(payload.get("text", ""))
            metadatas.append(payload)
            distances.append(getattr(hit, "score", 0.0) or 0.0)
    else:
        results = col.query(
            query_embeddings=vector,
            n_results=min(n_query, max(col.count(), 1)),
            include=["documents", "metadatas", "distances"],
        )

        documents = (results.get("documents") or [[]])[0]
        metadatas = (results.get("metadatas") or [[]])[0]
        distances = (results.get("distances") or [[]])[0]

    candidatos = []
    vistos = set()
    for idx, doc in enumerate(documents):
        texto = _normalizar_texto(doc)
        if not texto:
            continue

        firma = hashlib.sha1(texto[:300].lower().encode("utf-8")).hexdigest()[:16]
        if firma in vistos:
            continue
        vistos.add(firma)

        metadata = metadatas[idx] if idx < len(metadatas) else {}
        distance = distances[idx] if idx < len(distances) else 99
        source_type = (metadata or {}).get("source_type")
        length_penalty = 0.3 if len(texto) > CHUNK_SIZE * 1.2 else 0
        source_bonus = _source_preference_bonus(source_type, preferred_source_types)
        if _use_qdrant():
            # En Qdrant, score mayor significa mejor similitud.
            score = distance + (_prioridad_fuente(source_type) * 0.08) + source_bonus - length_penalty
        else:
            # En Chroma, distance menor significa mejor similitud.
            score = distance - (_prioridad_fuente(source_type) * 0.08) - source_bonus + length_penalty

        candidatos.append(
            {
                "texto": texto,
                "metadata": metadata or {},
                "score": score,
            }
        )

    if _use_qdrant():
        candidatos.sort(key=lambda item: item["score"], reverse=True)  # Mayor score = mejor similitud
    else:
        candidatos.sort(key=lambda item: item["score"])  # Menor score = mejor (distancia)

    # Si hay tipos preferidos, priorizamos de forma fuerte esos source_type
    # antes de completar con el resto. Esto evita que, por ejemplo, una skill
    # de historia termine respondiendo solo con PDFs genéricos.
    seleccionados = []
    if preferred_source_types:
        usados = set()
        for st in preferred_source_types:
            for idx, item in enumerate(candidatos):
                if idx in usados:
                    continue
                if (item.get("metadata") or {}).get("source_type") != st:
                    continue
                seleccionados.append(item)
                usados.add(idx)
                if len(seleccionados) >= n:
                    break
            if len(seleccionados) >= n:
                break
        if len(seleccionados) < n:
            for idx, item in enumerate(candidatos):
                if idx in usados:
                    continue
                seleccionados.append(item)
                if len(seleccionados) >= n:
                    break
    else:
        seleccionados = candidatos[:n]

    contexto_partes = []
    for item in seleccionados:
        bloque = f"[Fuente: {_formatear_fuente(item['metadata'])}]\n{item['texto']}"
        contexto_partes.append(bloque)

    contexto = _truncate_context_by_tokens(contexto_partes, MAX_CONTEXT_TOKENS)
    if len(contexto) > MAX_CONTEXT_CHARS:
        contexto = contexto[:MAX_CONTEXT_CHARS].rsplit(" ", 1)[0]

    sources = []
    seen_sources = set()
    for item in seleccionados:
        metadata = item["metadata"] or {}
        label = _formatear_fuente(metadata)
        source_key = (
            metadata.get("source_type"),
            metadata.get("source_name"),
            metadata.get("source_path"),
            metadata.get("source_url"),
        )
        if source_key in seen_sources:
            continue
        seen_sources.add(source_key)
        sources.append(
            {
                "label": label,
                "source_type": metadata.get("source_type", "unknown"),
                "source_name": metadata.get("source_name") or metadata.get("source_label") or metadata.get("source_path") or "",
                "source_path": metadata.get("source_path", ""),
                "source_url": metadata.get("source_url", ""),
                "source_page": metadata.get("source_page", ""),
            }
        )

    primary_source_type = seleccionados[0]["metadata"].get("source_type", "unknown") if seleccionados else "unknown"
    result = {
        "context": contexto,
        "sources": sources,
        "primary_source_type": primary_source_type,
    }
    set_rag_search(pregunta, result, preferred_source_types)
    return result
