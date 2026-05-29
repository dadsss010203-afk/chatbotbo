"""
services/chat_pipeline.py
Pipeline compartido de procesamiento de mensajes para /chat y /chat/stream.
Elimina duplicacion entre ambos endpoints.
Las tarifas ahora se manejan via API externa (chatbotbo).
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Callable, Awaitable

import requests

from core import rag, ollama, session, idiomas, intents, capabilities, cache, contacto, observability
from chatbots.general.chat_helpers import (
    buscar_contexto_local_minimo, respuesta_chat_vacio, log_sin_info,
    extraer_citas_evidencia, validar_evidencia_en_contexto,
)
from chatbots.general.config import (
    construir_prompt, REQUIRE_EVIDENCE, DATA_FILE, HISTORIA_FILE,
)
from chatbots.general.services.response_utils import (
    _postprocess_llm_response, _normalize_response_text, _respuesta_incompleta,
    _limpiar_contexto_rag, _sin_info_payload, _truncate_response_safely,
    _mensaje_fuera_dominio, _respuesta_en_portugues,
)

logger = logging.getLogger("chatbotbo.pipeline")

ChatContext = dict[str, Any]
LLMCallFn = Callable[..., Awaitable[str]]


# ─────────────────────────────────────────────
#  FASE 1: PRE-CHECKS (tracking, traduccion)
# ─────────────────────────────────────────────

async def run_pre_checks(
    ctx: ChatContext,
    llm_call: LLMCallFn,
) -> dict | None:
    """Ejecuta pre-checks que pueden devolver respuesta inmediata. Retorna None para seguir al RAG."""
    pregunta = ctx["pregunta"]
    tracking_mode = ctx.get("tracking_mode", False)

    # ── Tracking mode
    if tracking_mode:
        from chatbots.general.services.tracking import _resolver_tracking_deterministico
        try:
            return _resolver_tracking_deterministico(pregunta)
        except ValueError as e:
            return {"response": str(e), "tracking": {"ok": False, "pending": False, "error": str(e)}, "quick_replies": []}

    # ── Traduccion automatica
    if pregunta.lower().startswith("traduce exactamente"):
        respuesta = await llm_call([{"role": "user", "content": pregunta}])
        return {"response": ollama.limpiar_respuesta(respuesta)}

    return None


# ─────────────────────────────────────────────
#  FASE 2: INTENTS (saludos, dominio, inyeccion)
# ─────────────────────────────────────────────

def check_intents(ctx: ChatContext) -> dict | None:
    """Saludos, despedidas, prompt injection, fuera de dominio."""
    sid = ctx["sid"]
    pregunta = ctx["pregunta"]
    lang = ctx["lang"]
    t = idiomas.IDIOMAS[lang]

    if intents.es_prompt_injection(pregunta):
        logger.warning("PROMPT_INJECTION | pregunta='%s'", pregunta[:100])
        return {"response": t["sin_info"]}

    if intents.es_pregunta_fuera_dominio(pregunta):
        logger.warning("FUERA_DOMINIO | pregunta='%s'", pregunta[:100])
        return {"response": _mensaje_fuera_dominio(pregunta, lang)}

    if intents.es_saludo(pregunta):
        return {"response": t["saludo"]}

    if intents.es_presentacion(pregunta):
        return {"response": "Soy ChatbotBO, el asistente virtual de la Agencia Boliviana de Correos. En que puedo ayudarte?"}

    if intents.es_despedida(pregunta):
        session.limpiar_historial(sid)
        return {"response": t["despedida"], "despedida": True}

    return None


# ─────────────────────────────────────────────
#  FASE 3: RAG + LLM (pipeline principal)
# ─────────────────────────────────────────────

async def run_rag_llm_pipeline(
    ctx: ChatContext,
    llm_call: LLMCallFn,
) -> dict:
    """Pipeline completo: RAG -> construir prompt -> LLM -> validar."""
    sid = ctx["sid"]
    pregunta = ctx["pregunta"]
    pregunta_llm = ctx.get("pregunta_llm", pregunta)
    lang = ctx["lang"]
    t = idiomas.IDIOMAS[lang]
    skill_resolution = ctx["skill_resolution"]
    general_only = ctx.get("general_only", False)

    # ── Modo general only (sin RAG)
    if general_only:
        local_result = buscar_contexto_local_minimo(pregunta, DATA_FILE, HISTORIA_FILE)
        contexto = local_result.get("context", "").strip()
        sistema = (
            f"CRITICAL LANGUAGE RULE: {t['instruccion']} You MUST respond ONLY in that language.\n\n"
            "Eres un asistente que razona SOLO con el CONTEXTO LOCAL proporcionado.\n"
            f"Si el contexto no alcanza, di: \"{respuesta_chat_vacio(lang, pregunta)}\"\n\n"
            f"CONTEXTO LOCAL:\n{contexto}\n"
        )
        mensajes = [{"role": "system", "content": sistema}, {"role": "user", "content": pregunta}]
        respuesta = await llm_call(mensajes)
        respuesta = ollama.limpiar_respuesta(respuesta)
        respuesta = _postprocess_llm_response(respuesta, respuesta_chat_vacio(lang, pregunta))
        respuesta = _normalize_response_text(respuesta)
        return {
            "response": respuesta, "general_only": True,
            "skill_resolution": {"in_scope": None, "primary_skill": None, "matched_skills": []},
            "sources": local_result.get("sources", []),
            "primary_source_type": local_result.get("primary_source_type"),
        }

    primary_skill = skill_resolution.get("primary_skill") or {}
    primary_skill_id = primary_skill.get("id", "")

    # Cache check
    cached_response = cache.get_response(
        pregunta=pregunta, lang=lang, skill_id=primary_skill_id,
        model=os.environ.get("LLM_MODEL", "correos-bot"), require_evidence=REQUIRE_EVIDENCE,
    )
    if cached_response and (cached_response.get("response") or "").strip():
        observability.log_event("cache.response_hit", lang=lang, primary_skill=primary_skill_id)
        return {
            "response": cached_response["response"].strip(),
            "skill_resolution": {"in_scope": skill_resolution["in_scope"],
                "primary_skill": primary_skill_id, "matched_skills": skill_resolution.get("skill_ids", [])},
            "sources": cached_response.get("sources", []),
            "primary_source_type": cached_response.get("primary_source_type"),
            "cache_hit": True,
        }

    # RAG search
    loop = asyncio.get_running_loop()
    rag_result = await loop.run_in_executor(None, lambda: rag.buscar(
        pregunta, preferred_source_types=capabilities.preferred_sources_for_skill(primary_skill),
        skill_id=primary_skill_id if primary_skill_id else None,
        strict_preferred_sources=(primary_skill_id == "historia_correos_bolivia"),
    ))
    contexto = rag_result.get("context", "")
    sources = rag_result.get("sources", [])
    valid_sources = [s for s in sources if s.get("source_type") and s.get("source_type") != "unknown"]

    # Fallback historia
    if (not contexto.strip() or not valid_sources) and primary_skill_id == "historia_correos_bolivia":
        from chatbots.general.routes import _cargar_historia_directamente
        contexto_historia = _cargar_historia_directamente()
        if contexto_historia:
            contexto = contexto_historia
            valid_sources = [{"source_type": "history", "source_name": "historia_institucional.json"}]

    # Sin contexto
    if not contexto.strip() or not valid_sources:
        log_sin_info(pregunta, lang, primary_skill_id)
        from chatbots.general.routes import _registrar_sin_respuesta
        _registrar_sin_respuesta(pregunta, lang, primary_skill_id)
        fallback = _sin_info_payload(lang, t)
        return {
            "response": _truncate_response_safely(fallback["response"]),
            "skill_resolution": {"in_scope": skill_resolution["in_scope"],
                "primary_skill": primary_skill_id, "matched_skills": skill_resolution.get("skill_ids", [])},
            "sources": sources, "primary_source_type": rag_result.get("primary_source_type"),
            "quick_replies": fallback.get("quick_replies", []),
        }

    # Construir prompt
    from chatbots.general.routes import _trim_messages_to_token_budget, _estimate_message_tokens
    hora = session.get_hora_bolivia()
    sistema = construir_prompt(
        t["instruccion"], _limpiar_contexto_rag(contexto), hora, t["sin_info"],
        skill_name=primary_skill.get("nombre", ""),
        skill_description=primary_skill.get("descripcion", ""),
        skill_triggers=primary_skill.get("trigger", ""),
    )
    mensajes = [
        {"role": "system", "content": sistema},
        *session.historial_reciente(sid),
        {"role": "user", "content": pregunta_llm},
    ]
    mensajes = _trim_messages_to_token_budget(mensajes, ollama.OLLAMA_PROMPT_MAX_TOKENS)
    prompt_tokens = sum(_estimate_message_tokens(m) for m in mensajes)

    observability.log_event("llm.request", lang=lang, model=ollama.LLM_MODEL,
        primary_skill=primary_skill.get("id"), prompt_tokens=prompt_tokens,
        source_type=rag_result.get("primary_source_type"), source_count=len(sources))

    # Llamar LLM
    try:
        respuesta = await asyncio.wait_for(llm_call(mensajes), timeout=float(ollama.LLM_RESPONSE_TIMEOUT))
    except asyncio.TimeoutError:
        return {"response": f"Lo siento, el sistema esta tardando mas de lo normal. Por favor llamanos al {contacto.telefono()} o visita {contacto.web()}", "timeout": True}

    # Post-procesar
    respuesta = ollama.limpiar_respuesta(respuesta)
    respuesta = _postprocess_llm_response(respuesta, t["sin_info"])
    respuesta = _normalize_response_text(respuesta)

    # Completar si quedo cortada
    if respuesta and respuesta != t["sin_info"] and _respuesta_incompleta(respuesta):
        logger.info("RESPUESTA_INCOMPLETA detectada")
        from chatbots.general.routes import _completar_respuesta_incompleta
        respuesta = await _completar_respuesta_incompleta(ctx["request"], ctx["request_id"], respuesta, pregunta, lang)
        respuesta = ollama.limpiar_respuesta(respuesta)
        respuesta = _normalize_response_text(respuesta)

    # Guardias anti-alucinacion
    if _respuesta_en_portugues(respuesta):
        logger.warning("RESPUESTA_PORTUGUES detectada")
        respuesta = t["sin_info"]

    from core.intents import detectar_alucinacion, respuesta_fuera_de_dominio, datos_inventados
    if detectar_alucinacion(respuesta):
        logger.warning("ALUCINACION detectada")
        respuesta = t["sin_info"]
    if respuesta and respuesta != t["sin_info"] and respuesta_fuera_de_dominio(pregunta, respuesta):
        logger.warning("CONFUSION detectada")
        respuesta = t["sin_info"]
    if respuesta and respuesta != t["sin_info"] and capabilities.skill_requiere_guardia_numerica(primary_skill_id):
        if datos_inventados(respuesta, contexto):
            logger.warning("DATOS_INVENTADOS")
            respuesta = t["sin_info"]

    if REQUIRE_EVIDENCE:
        citas = extraer_citas_evidencia(respuesta)
        if not validar_evidencia_en_contexto(citas, contexto):
            respuesta = t["sin_info"]

    presentacion = "Soy ChatbotBO, el asistente virtual de la Agencia Boliviana de Correos. En que puedo ayudarte?"
    if respuesta.startswith("Eres ChatbotBO") or respuesta.strip().startswith(presentacion):
        respuesta = t["sin_info"]

    _es_sin_info = respuesta == t["sin_info"]
    quick_replies = []
    if _es_sin_info:
        from chatbots.general.routes import _registrar_sin_respuesta
        fallback = _sin_info_payload(lang, t)
        respuesta = fallback["response"]
        quick_replies = fallback.get("quick_replies", [])
        _registrar_sin_respuesta(pregunta, lang, primary_skill_id)

    respuesta = _truncate_response_safely(respuesta)

    should_cache = (not _es_sin_info and bool(valid_sources) and len(respuesta) >= 40)
    if should_cache:
        cache.set_response(pregunta=pregunta, lang=lang, skill_id=primary_skill_id,
            model=os.environ.get("LLM_MODEL", "correos-bot"), require_evidence=REQUIRE_EVIDENCE,
            payload={"response": respuesta, "sources": rag_result.get("sources", []),
                     "primary_source_type": rag_result.get("primary_source_type")})

    observability.log_event("llm.response", lang=lang, model=ollama.LLM_MODEL,
        primary_skill=primary_skill.get("id"), response_chars=len(respuesta), prompt_tokens=prompt_tokens)

    return {
        "response": respuesta,
        "skill_resolution": {"in_scope": skill_resolution["in_scope"],
            "primary_skill": primary_skill_id, "matched_skills": skill_resolution.get("skill_ids", [])},
        "sources": rag_result.get("sources", []),
        "primary_source_type": rag_result.get("primary_source_type"),
        "quick_replies": quick_replies,
    }
