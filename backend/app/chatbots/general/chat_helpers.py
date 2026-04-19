"""
chatbots/general/chat_helpers.py
Funciones auxiliares para respuestas, evidencia y contexto local.
"""

from __future__ import annotations

import json
import os
import re


def respuesta_chat_vacio(lang: str, pregunta: str) -> str:
    texto = (pregunta or "").strip().lower()
    if any(token in texto for token in ("hola", "buenas", "hello", "bonjour", "olá", "ola", "hi")):
        if lang == "en":
            return "Hello. This chatbot has no information loaded yet."
        if lang == "fr":
            return "Bonjour. Ce chatbot n'a encore aucune information chargée."
        if lang == "pt":
            return "Olá. Este chatbot ainda não tem informações carregadas."
        if lang == "zh":
            return "您好。这个聊天机器人目前还没有加载任何信息。"
        if lang == "ru":
            return "Здравствуйте. В этом чат-боте пока не загружена информация."
        return "Hola. Este chatbot todavía no tiene información cargada."

    if lang == "en":
        return "I have no information loaded yet."
    if lang == "fr":
        return "Je n'ai encore aucune information chargée."
    if lang == "pt":
        return "Ainda não tenho nenhuma informação carregada."
    if lang == "zh":
        return "我目前还没有加载任何信息。"
    if lang == "ru":
        return "У меня пока нет загруженной информации."
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
                fuentes.append(
                    {
                        "source_type": "pdf",
                        "source_name": item.get("nombre_archivo") or "PDF",
                        "source_url": item.get("url") or "",
                        "texto": texto,
                    }
                )
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
                fuentes.append(
                    {
                        "source_type": "history",
                        "source_name": item.get("titulo") or "Historia",
                        "source_url": item.get("url") or "",
                        "texto": texto,
                    }
                )
    except Exception:
        pass

    try:
        if os.path.exists(data_file):
            with open(data_file, "r", encoding="utf-8") as fh:
                texto = fh.read().strip()
            if texto:
                fuentes.append(
                    {
                        "source_type": "web_main",
                        "source_name": "Texto base",
                        "source_url": "",
                        "texto": texto,
                    }
                )
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
        snippet = texto[max(0, inicio - 220) : inicio + 650].strip() or texto[:700].strip()
        candidatos.append(
            {
                "score": score,
                "context": snippet,
                "source_type": fuente["source_type"],
                "source_name": fuente["source_name"],
                "source_url": fuente["source_url"],
            }
        )

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
