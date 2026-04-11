"""
core/rag.py
Motor RAG: embeddings, indexado y búsqueda en ChromaDB.
Compartido por todos los chatbots.
"""

import os
import re
import hashlib
from tqdm import tqdm
from sentence_transformers import SentenceTransformer

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

import chromadb
from chromadb.config import Settings

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

# ─────────────────────────────────────────────
#  ESTADO GLOBAL
# ─────────────────────────────────────────────
_embedder   = None
_client     = None
_collection = None
_collection_name = None


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
    global _embedder, _client, _collection, _collection_name

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

    client      = chromadb.PersistentClient(
        path=path,
        settings=Settings(anonymized_telemetry=False),
    )
    _client = client
    _collection_name = collection_name
    _collection = client.get_or_create_collection(name=collection_name)
    print(f" ChromaDB listo en '{path}' ({_collection.count()} chunks en '{collection_name}')")

    return _embedder, _collection


def reset_collection() -> bool:
    """Elimina y recrea la colección actual de ChromaDB."""
    global _collection

    if _client is None or not _collection_name:
        raise RuntimeError("RAG no inicializado. Llama a rag.inicializar() primero.")

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
    return get_collection().count()


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
        payload = {
            "documents": chunks[i:i + BATCH_SIZE],
            "embeddings": embeddings[i:i + BATCH_SIZE].tolist(),
            "ids": chunk_ids[i:i + BATCH_SIZE],
        }
        if metadatas:
            payload["metadatas"] = metadatas[i:i + BATCH_SIZE]
        col.add(**payload)

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
        payload = {
            "documents": dedup_chunks[i : i + BATCH_SIZE],
            "embeddings": embeddings[i : i + BATCH_SIZE].tolist(),
            "ids": dedup_ids[i : i + BATCH_SIZE],
        }
        if dedup_meta:
            payload["metadatas"] = dedup_meta[i : i + BATCH_SIZE]
        col.add(**payload)

    return {"ok": True, "removed": removed, "added": len(dedup_chunks)}


# ─────────────────────────────────────────────
#  BÚSQUEDA
# ─────────────────────────────────────────────

def _prioridad_fuente(source_type: str) -> int:
    prioridades = {
        "history": 5,
        "branch": 5,
        "section": 4,
        "web_main": 4,
        "service": 4,
        "pdf": 3,
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

    # Pre-calcular embedding para evitar timeout en ChromaDB
    vector = emb.encode([pregunta]).tolist()
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
        score = distance - (_prioridad_fuente(source_type) * 0.08) - source_bonus + length_penalty

        candidatos.append(
            {
                "texto": texto,
                "metadata": metadata or {},
                "score": score,
            }
        )

    candidatos.sort(key=lambda item: item["score"])
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

    primary_source_type = sources[0]["source_type"] if sources else None
    return {
        "context": contexto,
        "sources": sources,
        "primary_source_type": primary_source_type,
    }
