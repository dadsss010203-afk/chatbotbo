"""
core/rag.py
Motor RAG: embeddings, indexado y búsqueda en ChromaDB.
Compartido por todos los chatbots.
"""

import os
from tqdm import tqdm
from sentence_transformers import SentenceTransformer
import chromadb

# ─────────────────────────────────────────────
#  CONFIGURACIÓN
# ─────────────────────────────────────────────
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
CHROMA_PATH     = os.environ.get("CHROMA_PATH",     "chroma_db")
CHUNK_SIZE      = int(os.environ.get("CHUNK_SIZE",   "600"))
BATCH_SIZE      = int(os.environ.get("BATCH_SIZE",   "500"))
N_RESULTADOS    = int(os.environ.get("N_RESULTADOS",  "3"))

# ─────────────────────────────────────────────
#  ESTADO GLOBAL
# ─────────────────────────────────────────────
_embedder   = None
_collection = None


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
    global _embedder, _collection

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

    client      = chromadb.PersistentClient(path=path)
    _collection = client.get_or_create_collection(name=collection_name)
    print(f" ChromaDB listo en '{path}' ({_collection.count()} chunks en '{collection_name}')")

    return _embedder, _collection


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
    size   = chunk_size or CHUNK_SIZE
    chunks = []
    ids    = []
    idx    = 0
    start  = 0

    while start < len(texto):
        chunks.append(texto[start:start + size])
        ids.append(f"{prefijo}_{idx}")
        start += size - 100
        idx   += 1

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

    chunks, ids = texto_a_chunks(texto, prefijo=prefijo)
    print(f"   → {len(chunks)} chunks de '{filepath}'")
    return chunks, ids


# ─────────────────────────────────────────────
#  INDEXADO
# ─────────────────────────────────────────────

def indexar(chunks: list, chunk_ids: list, limpiar: bool = True) -> bool:
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
        col.add(
            documents  = chunks[i:i + BATCH_SIZE],
            embeddings = embeddings[i:i + BATCH_SIZE].tolist(),
            ids        = chunk_ids[i:i + BATCH_SIZE],
        )

    print(f" {len(chunks)} chunks indexados en ChromaDB")
    return True


# ─────────────────────────────────────────────
#  BÚSQUEDA
# ─────────────────────────────────────────────

def buscar(pregunta: str, n_resultados: int = None) -> str:
    col = get_collection()
    emb = get_embedder()
    n   = n_resultados or N_RESULTADOS

    # Pre-calcular embedding para evitar timeout en ChromaDB
    vector = emb.encode([pregunta]).tolist()
    results = col.query(query_embeddings=vector, n_results=n)

    contexto = "\n\n".join(results["documents"][0])
    if len(contexto) > 800:
        contexto = contexto[:800].rsplit(" ", 1)[0]
    return contexto
