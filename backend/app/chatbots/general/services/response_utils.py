"""
services/response_utils.py
Utilidades de post-procesamiento de respuestas LLM.
Extraidas de routes.py para evitar imports circulares con chat_pipeline.
"""

from __future__ import annotations

import re
from typing import Any

from core import ollama
from chatbots.general.chat_helpers import respuesta_chat_vacio


def _postprocess_llm_response(texto: str, sin_info: str) -> str:
    respuesta = (texto or "").strip()
    if not respuesta:
        return sin_info

    bloqueados = (
        "SKILL PRINCIPAL PARA ESTA CONSULTA",
        "DESCRIPCION DE LA SKILL PRINCIPAL",
        "DISPARADORES DE LA SKILL PRINCIPAL",
        "INFORMACION OFICIAL",
        "INSTRUCCIONES:",
        "Desciende a continuacion la informacion",
    )
    lineas = [ln.strip() for ln in respuesta.splitlines() if ln.strip()]
    lineas = [ln for ln in lineas if not any(ln.lower().startswith(tag.lower()) for tag in bloqueados)]
    if not lineas:
        return sin_info
    return "\n".join(lineas).strip() or sin_info


def _normalize_response_text(texto: str) -> str:
    raw = (texto or "").replace("\r\n", "\n").replace("\r", "\n")
    raw = re.sub(r'\n{2,}', '\u0000PARA\u0000', raw)
    raw = re.sub(r'\n(?=[ \t]*[-*•][ \t]|\d+[.)]\s)', '\u0000ITEM\u0000', raw)
    raw = raw.replace('\n', ' ')
    raw = re.sub(r'[ \t]{2,}', ' ', raw)
    raw = raw.replace('\u0000PARA\u0000', '\n\n')
    raw = raw.replace('\u0000ITEM\u0000', '\n')

    normalized_lines: list[str] = []
    previous_blank = False
    for line in raw.split("\n"):
        stripped = line.strip()
        if not stripped:
            if normalized_lines and not previous_blank:
                normalized_lines.append("")
            previous_blank = True
            continue
        compact = re.sub(r"[ \t]+", " ", stripped)
        normalized_lines.append(compact)
        previous_blank = False

    while normalized_lines and normalized_lines[-1] == "":
        normalized_lines.pop()
    return "\n".join(normalized_lines).strip()


def _respuesta_incompleta(texto: str) -> bool:
    if not texto or len(texto.strip()) < 20:
        return False
    ultimo = texto.rstrip()

    if ultimo[-1] in ".!?…":
        lineas = [l.strip() for l in ultimo.splitlines() if l.strip()]
        items_lista = [l for l in lineas if re.match(r'^[-*•]?\s*\w[^:]{1,40}:\s*.+', l)]
        if len(items_lista) >= 2:
            ultimo_item = items_lista[-1]
            partes = ultimo_item.split(':', 1)
            if len(partes) == 2 and len(partes[1].strip()) < 8:
                return True
        return False

    if ultimo[-1] in ",:;-–—(":
        return True

    palabras_incompletas = {
        "y", "o", "e", "u", "ni", "pero", "sino", "aunque", "porque",
        "que", "con", "sin", "de", "del", "la", "el", "los", "las",
        "un", "una", "su", "sus", "en", "a", "al", "por", "para",
        "como", "si", "se", "le", "lo", "tambien", "ademas",
        "and", "or", "but", "with", "the", "a", "an", "of", "in",
    }
    ultima_palabra = ultimo.split()[-1].lower().rstrip(".,;:")
    if ultima_palabra in palabras_incompletas:
        return True

    if len(ultimo) > 80 and ultimo[-1].isalpha():
        return True

    return False


def _limpiar_contexto_rag(contexto: str) -> str:
    if not contexto:
        return contexto
    lineas = contexto.splitlines()
    resultado = []
    for linea in lineas:
        limpia = re.sub(r"^(\s*)[●•▪▸►]\s*", r"\1- ", linea)
        resultado.append(limpia)
    return "\n".join(resultado)


def _sin_info_payload(lang: str, textos: dict) -> dict:
    return {"response": textos["sin_info"], "quick_replies": []}


def _truncate_response_safely(respuesta: str, max_chars: int = 0) -> str:
    if max_chars <= 0 or len(respuesta) <= max_chars:
        return respuesta
    if _looks_structured_response(respuesta):
        return respuesta
    safe = respuesta[:max_chars]
    cut = max(safe.rfind("."), safe.rfind("!"), safe.rfind("?"))
    if cut > 30:
        return safe[:cut + 1].strip()
    return safe.rsplit(" ", 1)[0].strip() + "..."


def _looks_structured_response(texto: str) -> bool:
    raw = (texto or "").strip()
    if not raw:
        return False
    if raw.startswith("```"):
        return True
    if raw[0] in "{[":
        return True
    if raw.startswith(("dict(", "json", "python")):
        return True
    if "\n" in raw:
        return True
    if re.search(r"(^|\s)(?:\d+\.\s|[•\-]\s)", raw):
        return True
    return False


def _stream_preview_text(texto: str) -> str:
    preview = ollama.limpiar_respuesta(texto or "")
    preview = _normalize_response_text(preview)
    return preview


def _mensaje_fuera_dominio(pregunta: str, lang: str) -> str:
    _PATRON_CONSULTA_TECNICA_RED = re.compile(
        r'\b(?:ip|dns|servidor|host|puerto|firewall|subred|gateway|mac\s+address)\b'
        r'|\bscan\s+(?:de\s+)?(?:red|puertos?|vulnerabilidades?)\b',
        re.IGNORECASE,
    )
    if _PATRON_CONSULTA_TECNICA_RED.search(pregunta or ""):
        msgs = {"es": "No puedo proporcionar esa informacion.", "en": "I cannot provide that information."}
        return msgs.get(lang, msgs["es"])
    msgs = {
        "es": "Solo puedo ayudarte con temas de Correos Bolivia. Tienes alguna consulta sobre envios, rastreo o servicios postales?",
        "en": "I can only help you with Correos Bolivia topics. Do you have any questions about shipping, tracking, or postal services?",
    }
    return msgs.get(lang, msgs["es"])


def _respuesta_en_portugues(texto: str) -> bool:
    if not texto or len(texto) < 20:
        return False
    t = texto.lower()
    marcadores_pt = [
        "voce", "nao ", "tambem", "entao", "esta ", "estao", "sao ",
        "isso ", "esse ", "essa ", "aqui ", "aquele", "posso ", "pode ",
        "podem ", "temos ", "nosso ", "nossa ", "obrigado", "obrigada",
        "envio ", "envios ", "rastreamento", "agencia ", "correios",
        "servico", "servicos", "informacao", "informacoes", "visite ",
        "ligue ", "ate logo", "ate mais",
    ]
    hits = sum(1 for m in marcadores_pt if m in t)
    return hits >= 2
