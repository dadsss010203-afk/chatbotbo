"""
chatbots/general/chat_helpers.py
Funciones auxiliares para respuestas, evidencia y contexto local.
"""

from __future__ import annotations

import json
import logging as _logging
import os
import re


def respuesta_chat_vacio(lang: str, pregunta: str) -> str:
    texto = (pregunta or "").strip().lower()
    if any(token in texto for token in ("hola", "buenas", "hello", "hi")):
        if lang == "en":
            return "Hello. This chatbot has no information loaded yet."
        return "Hola. Este chatbot todavía no tiene información cargada."
    if lang == "en":
        return "I have no information loaded yet."
    return "No tengo información cargada todavía."


def _normalizar_busqueda_local(texto: str) -> str:
    texto = (texto or "").lower().strip()
    texto = re.sub(r"[^a-z0-9áéíóúñü\s]", " ", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def _cargar_contexto_local_minimo(data_file: str, historia_file: str) -> list[dict]:
    fuentes = []

    try:
        pdfs_path = os.path.join(os.path.dirname(data_file), "pdfs_contenido.json")
        if os.path.exists(pdfs_path):
            with open(pdfs_path, "r", encoding="utf-8") as fh:
                pdfs = json.load(fh)
            for item in pdfs:
                texto = (item.get("texto_extraido") or "").strip()
                if not texto:
                    continue
                fuentes.append({
                    "source_type": "pdf",
                    "source_name": item.get("nombre_archivo") or "PDF",
                    "source_url": item.get("url") or "",
                    "texto": texto,
                })
    except Exception:
        pass

    try:
        historia_path = historia_file
        if historia_path and not os.path.isabs(historia_path):
            historia_path = os.path.join(os.path.dirname(data_file), os.path.basename(historia_path))
        if os.path.exists(historia_path):
            with open(historia_path, "r", encoding="utf-8") as fh:
                historia = json.load(fh)
            for item in historia if isinstance(historia, list) else []:
                texto = (item.get("contenido") or "").strip()
                if not texto:
                    continue
                fuentes.append({
                    "source_type": "history",
                    "source_name": item.get("titulo") or "Historia",
                    "source_url": item.get("url") or "",
                    "texto": texto,
                })
    except Exception:
        pass

    try:
        if os.path.exists(data_file):
            with open(data_file, "r", encoding="utf-8") as fh:
                texto = fh.read().strip()
            if texto:
                fuentes.append({
                    "source_type": "web_main",
                    "source_name": "Texto base",
                    "source_url": "",
                    "texto": texto,
                })
    except Exception:
        pass

    return fuentes


def buscar_contexto_local_minimo(pregunta: str, data_file: str, historia_file: str) -> dict:
    consulta = _normalizar_busqueda_local(pregunta)
    palabras = [w for w in consulta.split() if len(w) >= 4]
    if not palabras:
        palabras = consulta.split()

    candidatos = []
    for fuente in _cargar_contexto_local_minimo(data_file, historia_file):
        texto = fuente["texto"]
        texto_norm = _normalizar_busqueda_local(texto)
        score = 0
        for palabra in palabras:
            if palabra and palabra in texto_norm:
                score += 2
        if consulta and consulta in texto_norm:
            score += 4
        if score <= 0:
            continue

        inicio = 0
        for palabra in palabras:
            pos = texto_norm.find(palabra)
            if pos >= 0:
                inicio = pos
                break
        snippet = texto[max(0, inicio - 220): inicio + 650].strip() or texto[:700].strip()
        candidatos.append({
            "score": score,
            "context": snippet,
            "source_type": fuente["source_type"],
            "source_name": fuente["source_name"],
            "source_url": fuente["source_url"],
        })

    candidatos.sort(key=lambda item: (-item["score"], item["source_name"]))
    if not candidatos:
        return {"context": "", "sources": [], "primary_source_type": None}

    top = candidatos[:2]
    context = "\n\n".join(item["context"] for item in top if item["context"])
    sources = [
        {
            "label": f"{item['source_type']}: {item['source_name']}",
            "source_name": item["source_name"],
            "source_page": "",
            "source_path": "",
            "source_type": item["source_type"],
            "source_url": item["source_url"],
        }
        for item in top
    ]
    return {
        "context": context,
        "sources": sources,
        "primary_source_type": top[0]["source_type"],
    }


def extraer_citas_evidencia(respuesta: str) -> list[str]:
    if not respuesta:
        return []
    for line in (respuesta or "").splitlines():
        if line.strip().lower().startswith("evidencia:"):
            return [q.strip() for q in re.findall(r"\"([^\"]+)\"", line) if q.strip()]
    return []


def validar_evidencia_en_contexto(citas: list[str], contexto: str) -> bool:
    if not citas:
        return False
    ctx = contexto or ""
    return all(cita in ctx for cita in citas)


_EVIDENCE_STOPWORDS = {
    "para", "como", "cuando", "donde", "dónde", "que", "qué", "cual", "cuál",
    "con", "sin", "por", "sobre", "este", "esta", "estos", "estas", "desde",
    "hasta", "entre", "solo",
    "the", "and", "with", "from", "this", "that", "there", "where", "what",
    "pero", "porque", "cuanto", "cuánto", "tengo",
}


def _tokenizar_evidencia(texto: str) -> list[str]:
    tokens = re.findall(r"[a-záéíóúñü0-9]+", (texto or "").lower())
    return [t for t in tokens if len(t) >= 4 and t not in _EVIDENCE_STOPWORDS]


def respuesta_respaldada(respuesta: str, contexto: str, min_hits: int = 2) -> bool:
    """
    Verifica si la respuesta está respaldada por el contexto RAG.
    Acepta citas explícitas (Evidencia: "...") o coincidencia léxica mínima.
    """
    if not respuesta or not contexto:
        return False

    citas = extraer_citas_evidencia(respuesta)
    if citas and validar_evidencia_en_contexto(citas, contexto):
        return True

    ctx = _normalizar_busqueda_local(contexto)
    tokens = _tokenizar_evidencia(respuesta)
    if not tokens:
        return False

    hits = sum(1 for t in set(tokens) if t in ctx)
    if hits < min_hits:
        return False

    # Si hay números en la respuesta, deben existir en el contexto.
    numeros = re.findall(r"\b\d+[.,]?\d*\b", respuesta)
    if numeros and not all(num in contexto for num in numeros):
        return False

    return True


# ─────────────────────────────────────────────
#  RERANKING DE RESULTADOS RAG
# ─────────────────────────────────────────────

def rerank_rag_results(pregunta: str, resultados: list[dict]) -> list[dict]:
    """
    Reordena los resultados RAG por relevancia exacta de palabras clave
    de la pregunta. Mejora la calidad del contexto enviado al LLM.
    """
    if not resultados:
        return resultados

    consulta = _normalizar_busqueda_local(pregunta)
    palabras = [w for w in consulta.split() if len(w) >= 3]
    if not palabras:
        return resultados

    for r in resultados:
        texto = _normalizar_busqueda_local(r.get("text", "") or r.get("context", "") or "")
        score_exacto = sum(1 for p in palabras if p in texto)
        score_frase = 3 if consulta in texto else 0
        r["_rerank_score"] = score_exacto + score_frase

    return sorted(resultados, key=lambda x: x.get("_rerank_score", 0), reverse=True)


# ─────────────────────────────────────────────
#  LOGGING DE PREGUNTAS SIN RESPUESTA
# ─────────────────────────────────────────────

_sin_info_logger = _logging.getLogger("chatbotbo.sin_info")


def log_sin_info(pregunta: str, lang: str, skill_id: str) -> None:
    """
    Registra preguntas donde el bot no encontró información.
    Útil para identificar gaps en el RAG y mejorar el contenido.
    """
    _sin_info_logger.warning(
        "SIN_INFO | pregunta='%s' | lang=%s | skill=%s",
        (pregunta or "").strip()[:200],
        lang or "?",
        skill_id or "?",
    )
