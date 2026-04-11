"""
chatbots/general/routes.py
Rutas Flask del chatbot general. Usa el core/ para toda la lógica.

GET  /api/welcome
POST /api/chat
GET  /api/sucursales
GET  /api/idiomas
POST /api/reset
GET  /api/status
POST /api/actualizar
"""

import sys
import os
import threading
import re
import hashlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "core"))

import requests
import json
from flask import Blueprint, request, jsonify

from core import rag, ollama, session, location, idiomas, intents, updater, capabilities, observability, tarifas_skill
from chatbots.general.chat_helpers import (
    buscar_contexto_local_minimo,
    extraer_citas_evidencia,
    respuesta_chat_vacio,
    validar_evidencia_en_contexto,
)
from chatbots.general.translation_service import translate_texts
from chatbots.general.config import (
    NOMBRE, CHROMA_PATH, DATA_FILE, SUCURSALES_FILE, SECCIONES_FILE, HISTORIA_FILE,
    construir_prompt, REQUIRE_EVIDENCE,
)

# ─────────────────────────────────────────────
#  BLUEPRINT
# ─────────────────────────────────────────────
bp = Blueprint("general", __name__)   # sin prefix → rutas en /api/*

SUCURSALES: list = []
CHATBOT_GENERAL_ONLY = os.environ.get("CHATBOT_GENERAL_ONLY", "false").strip().lower() in ("1", "true", "yes")
REINDEX_DEBOUNCE_SECONDS = int(os.environ.get("REINDEX_DEBOUNCE_SECONDS", "30"))
CHAT_RESPONSE_MAX_CHARS = int(os.environ.get("CHAT_RESPONSE_MAX_CHARS", "0"))
LLM_TARIFF_ORCHESTRATOR = os.environ.get("LLM_TARIFF_ORCHESTRATOR", "true").strip().lower() in ("1", "true", "yes")
GENERAL_SYSTEM_PROMPT = (
    "Eres un asistente conversacional general, útil, claro y profesional. "
    "No afirmes tener acceso a bases de datos, documentos, skills, RAG, PDFs, scraping o contexto institucional "
    "si no aparecen explícitamente en la conversación. "
    "Responde solo con conocimiento general del modelo y con lo que diga el usuario en esta charla. "
    "Mantén respuestas breves, naturales y en el mismo idioma del usuario."
)

_reindex_timer = None
_reindex_lock = threading.Lock()
_reindex_mode = None


def _safe_json_object(text: str) -> dict | None:
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    m = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _llm_orquestar_tarifa(pregunta: str, pendiente: dict | None = None) -> dict | None:
    """
    Orquestador híbrido:
    - El LLM sugiere intención y campos detectados.
    - El backend valida y ejecuta siempre de forma determinística.
    """
    if not LLM_TARIFF_ORCHESTRATOR:
        return None
    if not ollama.ollama_disponible():
        return None

    pending = pendiente or {}
    system = (
        "Eres un clasificador de intención para tarifas postales. "
        "Devuelve SOLO un JSON válido, sin markdown.\n"
        "Campos esperados:\n"
        "- use_tarifa_flow: boolean\n"
        "- is_info_only: boolean\n"
        "- family: 'ems' | 'encomienda' | 'ems_hoja5' | 'ems_hoja6' | 'eca' | 'pliegos' | 'sacas_m' | 'ems_contratos' | 'super_express' | 'super_express_documentos' | 'super_express_paquetes' | null\n"
        "- scope: 'nacional' | 'internacional' | 'encomienda_nacional' | 'encomienda_internacional' | 'ems_hoja5_nacional' | 'ems_hoja6_internacional' | 'eca_nacional' | 'eca_internacional' | 'pliegos_nacional' | 'pliegos_internacional' | 'sacas_m_nacional' | 'sacas_m_internacional' | 'ems_contratos_nacional' | 'super_express_nacional' | 'super_express_documentos_internacional' | 'super_express_paquetes_internacional' | null\n"
        "- peso: string como '800g' o '1.2kg' o null\n"
        "- destino_servicio: string o null\n"
        "- confidence: number entre 0 y 1\n"
        "Marca is_info_only=true para preguntas informativas (ej. 'que es ems'). "
        "Si no hay intención de cotizar precio, use_tarifa_flow=false."
    )
    user = (
        f"Pregunta: {pregunta}\n"
        f"Contexto pendiente: {json.dumps(pending, ensure_ascii=False)}"
    )
    try:
        raw = ollama.llamar_ollama(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            opciones={"temperature": 0.0, "num_predict": 140},
        )
    except Exception:
        return None

    parsed = _safe_json_object(raw)
    if not parsed:
        return None

    scope = tarifas_skill.resolve_scope(parsed.get("scope"))
    family = parsed.get("family")
    if family not in {
        "ems", "encomienda", "ems_hoja5", "ems_hoja6", "eca", "pliegos", "sacas_m",
        "ems_contratos", "super_express", "super_express_documentos", "super_express_paquetes",
    }:
        family = tarifas_skill.detect_family(parsed.get("family") or parsed.get("destino_servicio") or pregunta)

    frag_peso = tarifas_skill.extract_tarifa_fragment(str(parsed.get("peso") or ""))
    peso = frag_peso.peso

    destino_servicio = (parsed.get("destino_servicio") or "").strip()
    columna = None
    if destino_servicio:
        columna = tarifas_skill.resolve_columna(destino_servicio, scope=scope) or tarifas_skill.resolve_columna(destino_servicio)

    try:
        confidence = float(parsed.get("confidence", 0) or 0)
    except Exception:
        confidence = 0.0

    return {
        "use_tarifa_flow": bool(parsed.get("use_tarifa_flow")),
        "is_info_only": bool(parsed.get("is_info_only")),
        "family": family,
        "scope": scope,
        "peso": peso,
        "columna": columna,
        "confidence": confidence,
    }


def _modo_general_only() -> bool:
    return CHATBOT_GENERAL_ONLY


def _estimate_message_tokens(message: dict) -> int:
    texto = (message.get("content") or "").strip()
    if not texto:
        return 0
    return rag.estimate_tokens(texto) + 4


def _trim_messages_to_token_budget(messages: list[dict], max_tokens: int) -> list[dict]:
    if not messages:
        return messages
    system_message = messages[0]
    remaining = messages[1:]
    current_tokens = _estimate_message_tokens(system_message)
    trimmed = []
    for message in reversed(remaining):
        tokens = _estimate_message_tokens(message)
        if current_tokens + tokens > max_tokens:
            break
        trimmed.append(message)
        current_tokens += tokens
    trimmed = list(reversed(trimmed))
    return [system_message] + trimmed


def _refresh_pdfs_after_start() -> None:
    """Revisa PDFs heredados después del arranque para no bloquear Flask."""
    try:
        pdf_refresh = capabilities.reprocesar_pdfs_pendientes()
        if pdf_refresh.get("mejorados"):
            print(
                "  PDFs heredados mejorados tras arranque "
                f"({pdf_refresh['mejorados']} mejoras) → reindexando..."
            )
            reindexar()
        elif pdf_refresh.get("reprocesados"):
            print(
                "  PDFs revisados en segundo plano: "
                f"{pdf_refresh['reprocesados']} reprocesados, "
                f"{pdf_refresh['mejorados']} mejorados."
            )
    except Exception as e:
        print(f"   Error validando PDFs tras arranque: {e}")


def _rag_chunks_seguro() -> int:
    if _modo_general_only():
        return 0
    try:
        return rag.total_chunks()
    except Exception:
        return 0


def _estado_capacidades() -> dict:
    return capabilities.get_runtime_capabilities(
        chunks=_rag_chunks_seguro(),
        embedding_model=os.environ.get("EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2"),
        chroma_path=CHROMA_PATH,
        ollama_ok=ollama.ollama_disponible(),
        modelo=os.environ.get("LLM_MODEL", "correos-bot"),
        sesiones_activas=session.total_sesiones(),
        sucursales=SUCURSALES,
        actualizacion=updater.get_estado(),
    )


def _missing_tarifa_fields(
    scope: str | None,
    peso: str | None,
    columna: str | None,
    family: str | None = None,
    level: str | None = None,
) -> list[str]:
    missing: list[str] = []
    if not scope:
        if level in {"nacional", "internacional"} and not family:
            missing.append(f"tipo_{level}")
        elif family == "ems":
            missing.append("alcance_ems")
        elif family == "encomienda":
            missing.append("alcance_encomienda")
        else:
            missing.append("alcance")
    if not peso:
        missing.append("peso")
    if not columna:
        missing.append("destino")
    return missing


def _wants_reset_tarifa(texto: str) -> bool:
    t = (texto or "").strip().lower()
    if not t:
        return False
    keywords = (
        "cancelar", "cancela", "olvida", "reiniciar", "reinicia",
        "empezar de nuevo", "comenzar de nuevo", "borrar",
    )
    return any(k in t for k in keywords)


def _is_service_selection_only(texto: str) -> bool:
    t = " ".join((texto or "").strip().lower().split())
    options = {
        "ems",
        "encomienda",
        "prioritario",
        "encomiendas postales",
        "correo prioritario lc/ao nacional",
        "correo prioritario lc ao nacional",
        "correo prioritario lc/ao internacional",
        "correo prioritario lc ao internacional",
        "eca nacional",
        "eca internacional",
        "pliegos oficiales nacional",
        "pliegos oficiales internacional",
        "sacas m nacional",
        "sacas m internacional",
        "ems contratos nacional",
        "super express nacional",
        "super express documentos internacional",
        "super express paquetes internacional",
    }
    return t in options


def _extract_geo_level_choice(texto: str) -> str | None:
    t = (texto or "").strip().lower()
    if t in {"nacional", "nacional.", "nacional!", "nacional?"}:
        return "nacional"
    if t in {"internacional", "internacional.", "internacional!", "internacional?"}:
        return "internacional"
    return None


def _scope_from_family_and_level(family: str | None, level: str | None) -> str | None:
    if family not in {
        "ems", "encomienda", "ems_hoja5", "ems_hoja6", "eca", "pliegos", "sacas_m",
        "ems_contratos", "super_express", "super_express_documentos", "super_express_paquetes",
    }:
        return None
    if family == "ems_contratos":
        return "ems_contratos_nacional"
    if family == "super_express":
        return "super_express_nacional"
    if family == "super_express_documentos":
        return "super_express_documentos_internacional"
    if family == "super_express_paquetes":
        return "super_express_paquetes_internacional"
    if level not in {"nacional", "internacional"}:
        return None
    if family == "ems":
        return "nacional" if level == "nacional" else "internacional"
    if family == "ems_hoja5":
        return "ems_hoja5_nacional" if level == "nacional" else None
    if family == "ems_hoja6":
        return "ems_hoja6_internacional" if level == "internacional" else None
    if family == "eca":
        return "eca_nacional" if level == "nacional" else "eca_internacional"
    if family == "pliegos":
        return "pliegos_nacional" if level == "nacional" else "pliegos_internacional"
    if family == "sacas_m":
        return "sacas_m_nacional" if level == "nacional" else "sacas_m_internacional"
    return "encomienda_nacional" if level == "nacional" else "encomienda_internacional"


def _family_for_scope(scope: str | None) -> str | None:
    sc = (scope or "").strip().lower()
    if sc in {"nacional", "internacional"}:
        return "ems"
    if sc in {"encomienda_nacional", "encomienda_internacional"}:
        return "encomienda"
    if sc == "ems_hoja5_nacional":
        return "ems_hoja5"
    if sc == "ems_hoja6_internacional":
        return "ems_hoja6"
    if sc in {"eca_nacional", "eca_internacional"}:
        return "eca"
    if sc in {"pliegos_nacional", "pliegos_internacional"}:
        return "pliegos"
    if sc in {"sacas_m_nacional", "sacas_m_internacional"}:
        return "sacas_m"
    if sc == "ems_contratos_nacional":
        return "ems_contratos"
    if sc == "super_express_nacional":
        return "super_express"
    if sc == "super_express_documentos_internacional":
        return "super_express_documentos"
    if sc == "super_express_paquetes_internacional":
        return "super_express_paquetes"
    return None


def _level_for_scope(scope: str | None) -> str | None:
    sc = (scope or "").strip().lower()
    if sc in {
        "nacional", "encomienda_nacional", "ems_hoja5_nacional", "eca_nacional",
        "pliegos_nacional", "sacas_m_nacional", "ems_contratos_nacional", "super_express_nacional",
    }:
        return "nacional"
    if sc in {
        "internacional", "encomienda_internacional", "ems_hoja6_internacional", "eca_internacional",
        "pliegos_internacional", "sacas_m_internacional",
        "super_express_documentos_internacional", "super_express_paquetes_internacional",
    }:
        return "internacional"
    return None


def _scopes_for_level(level: str | None) -> list[str]:
    lv = (level or "").strip().lower()
    if lv == "nacional":
        return [
            "nacional", "encomienda_nacional", "ems_hoja5_nacional", "eca_nacional",
            "pliegos_nacional", "sacas_m_nacional", "ems_contratos_nacional", "super_express_nacional",
        ]
    if lv == "internacional":
        return [
            "internacional", "encomienda_internacional", "ems_hoja6_internacional", "eca_internacional",
            "pliegos_internacional", "sacas_m_internacional",
            "super_express_documentos_internacional", "super_express_paquetes_internacional",
        ]
    return []


def _service_button_for_scope(scope: str) -> dict | None:
    if scope == "nacional":
        return {"label": "Express Mail Service (EMS)", "value": "ems"}
    if scope == "encomienda_nacional":
        return {"label": "Prioritario", "value": "encomienda"}
    if scope == "ems_hoja5_nacional":
        return {"label": "Correo Prioritario LC/AO", "value": "correo prioritario lc/ao nacional"}
    if scope == "internacional":
        return {"label": "Express Mail Service (EMS)", "value": "ems"}
    if scope == "encomienda_internacional":
        return {"label": "Encomiendas Postales", "value": "encomienda"}
    if scope == "ems_hoja6_internacional":
        return {"label": "Correo Prioritario LC/AO", "value": "correo prioritario lc/ao internacional"}
    if scope == "eca_nacional":
        return {"label": "Correspondencia Agrupada (ECA)", "value": "eca nacional"}
    if scope == "eca_internacional":
        return {"label": "Correspondencia Agrupada (ECA)", "value": "eca internacional"}
    if scope == "pliegos_nacional":
        return {"label": "Pliegos Oficiales", "value": "pliegos oficiales nacional"}
    if scope == "pliegos_internacional":
        return {"label": "Pliegos Oficiales", "value": "pliegos oficiales internacional"}
    if scope == "sacas_m_nacional":
        return {"label": "Sacas M", "value": "sacas m nacional"}
    if scope == "sacas_m_internacional":
        return {"label": "Sacas M", "value": "sacas m internacional"}
    if scope == "ems_contratos_nacional":
        return {"label": "EMS Contratos", "value": "ems contratos nacional"}
    if scope == "super_express_nacional":
        return {"label": "Super Express", "value": "super express nacional"}
    if scope == "super_express_documentos_internacional":
        return {"label": "Super Express Documentos", "value": "super express documentos internacional"}
    if scope == "super_express_paquetes_internacional":
        return {"label": "Super Express Paquetes", "value": "super express paquetes internacional"}
    return None


def _out_of_range_alternatives(
    peso: str,
    pregunta: str,
    current_scope: str,
    current_columna: str | None,
) -> list[dict]:
    level = _level_for_scope(current_scope)
    if not level:
        return []

    buttons: list[dict] = []
    seen: set[str] = set()
    for scope in _scopes_for_level(level):
        if scope == current_scope:
            continue

        col = None
        if current_columna and tarifas_skill.columna_valida_para_scope(current_columna, scope):
            col = current_columna
        if not col:
            col = tarifas_skill.resolve_columna(pregunta, scope=scope)
        if not col:
            continue

        intento = tarifas_skill.ejecutar_tarifa(peso=peso, columna=col, scope=scope)
        if not intento.get("ok"):
            continue

        btn = _service_button_for_scope(scope)
        if not btn:
            continue
        if btn["value"] in seen:
            continue
        seen.add(btn["value"])
        buttons.append(btn)

    return buttons


def _tarifa_quick_replies(
    missing: list[str],
    scope: str | None = None,
    family: str | None = None,
) -> list[dict]:
    if not missing:
        return []
    if "alcance" in missing:
        return [
            {"label": "Nacional", "value": "nacional"},
            {"label": "Internacional", "value": "internacional"},
        ]
    if "tipo_nacional" in missing:
        return [
            {"label": "Express Mail Service (EMS)", "value": "ems"},
            {"label": "Prioritario", "value": "encomienda"},
            {"label": "Correo Prioritario LC/AO", "value": "correo prioritario lc/ao nacional"},
            {"label": "Correspondencia Agrupada (ECA)", "value": "eca nacional"},
            {"label": "Pliegos Oficiales", "value": "pliegos oficiales nacional"},
            {"label": "Sacas M", "value": "sacas m nacional"},
            {"label": "EMS Contratos", "value": "ems contratos nacional"},
            {"label": "Super Express", "value": "super express nacional"},
        ]
    if "tipo_internacional" in missing:
        return [
            {"label": "Express Mail Service (EMS)", "value": "ems"},
            {"label": "Encomiendas Postales", "value": "encomienda"},
            {"label": "Correo Prioritario LC/AO", "value": "correo prioritario lc/ao internacional"},
            {"label": "Correspondencia Agrupada (ECA)", "value": "eca internacional"},
            {"label": "Pliegos Oficiales", "value": "pliegos oficiales internacional"},
            {"label": "Sacas M", "value": "sacas m internacional"},
            {"label": "Super Express Documentos", "value": "super express documentos internacional"},
            {"label": "Super Express Paquetes", "value": "super express paquetes internacional"},
        ]
    if "alcance_ems" in missing:
        return [
            {"label": "Nacional", "value": "nacional"},
            {"label": "Internacional", "value": "internacional"},
        ]
    if "alcance_encomienda" in missing:
        return [
            {"label": "Nacional", "value": "nacional"},
            {"label": "Internacional", "value": "internacional"},
        ]
    if "peso" in missing:
        return [
            {"label": "500g", "value": "500g"},
            {"label": "800g", "value": "800g"},
            {"label": "1kg", "value": "1kg"},
        ]
    # Primera fase robusta: sugerencias de destino para EMS Nacional (skill1).
    if "destino" in missing and scope == "nacional" and (family in {None, "ems"}):
        return [
            {"label": "Cobija", "value": "cobija"},
            {"label": "Trinidad", "value": "trinidad"},
            {"label": "Riberalta", "value": "riberalta"},
            {"label": "Ciudades intermedias", "value": "ciudades intermedias"},
            {"label": "Cobertura 1", "value": "cobertura 1"},
            {"label": "Cobertura 2", "value": "cobertura 2"},
            {"label": "Cobertura 3", "value": "cobertura 3"},
            {"label": "Cobertura 4", "value": "cobertura 4"},
        ]
    # Segunda fase robusta: sugerencias de destino para EMS Internacional (skill2).
    if "destino" in missing and scope == "internacional" and (family in {None, "ems"}):
        return [
            {"label": "América del Sur", "value": "america del sur"},
            {"label": "América Central y Caribe", "value": "america central y caribe"},
            {"label": "América del Norte", "value": "america del norte"},
            {"label": "Europa", "value": "europa"},
            {"label": "África / Asia / Oceanía", "value": "africa asia oceania"},
        ]
    # Tercera fase robusta: sugerencias para Mi Encomienda Prioritario Nacional (skill3).
    if "destino" in missing and scope == "encomienda_nacional" and (family in {None, "encomienda"}):
        return [
            {"label": "Ciudades Capitales", "value": "ciudades capitales"},
            {"label": "Destinos Especiales (Trinidad-Cobija)", "value": "destinos especiales"},
            {"label": "Prov. Dentro Depto.", "value": "prov dentro depto"},
            {"label": "Prov. En Otro Depto.", "value": "prov en otro depto"},
        ]
    # Cuarta fase robusta: sugerencias para Encomiendas Postales Internacional (skill4).
    if "destino" in missing and scope == "encomienda_internacional" and (family in {None, "encomienda"}):
        return [
            {"label": "América del Sur", "value": "america del sur"},
            {"label": "América Central y Caribe", "value": "america central y caribe"},
            {"label": "América del Norte", "value": "america del norte"},
            {"label": "Europa y Medio Oriente", "value": "europa y medio oriente"},
            {"label": "África / Asia / Oceanía", "value": "africa asia oceania"},
        ]
    if "destino" in missing and scope == "ems_hoja5_nacional" and (family in {None, "ems_hoja5"}):
        return [
            {"label": "Local", "value": "local"},
            {"label": "Nacional", "value": "nacional"},
            {"label": "Depto.", "value": "depto"},
            {"label": "Prov.", "value": "prov"},
            {"label": "Trinidad - Cobija", "value": "trinidad cobija"},
            {"label": "Riberalta - Guayaramerín", "value": "riberalta guayaramerin"},
        ]
    if "destino" in missing and scope == "ems_hoja6_internacional" and (family in {None, "ems_hoja6"}):
        return [
            {"label": "América del Sur", "value": "america del sur"},
            {"label": "América Central y el Caribe", "value": "america central y el caribe"},
            {"label": "América del Norte", "value": "america del norte"},
            {"label": "Europa y Medio Oriente", "value": "europa y medio oriente"},
            {"label": "África, Asia y Oceanía", "value": "africa asia y oceania"},
        ]
    if "destino" in missing and scope == "eca_nacional" and (family in {None, "eca"}):
        return [
            {"label": "Local", "value": "local"},
            {"label": "Nacional", "value": "nacional"},
            {"label": "Prov. Dentro Depto.", "value": "prov dentro depto"},
            {"label": "Prov. Depto. Prov.", "value": "prov depto prov"},
            {"label": "Trinidad - Cobija", "value": "trinidad cobija"},
            {"label": "Riberalta - Guayaramerín", "value": "riberalta guayaramerin"},
        ]
    if "destino" in missing and scope == "eca_internacional" and (family in {None, "eca"}):
        return [
            {"label": "América del Sur", "value": "america del sur"},
            {"label": "América Central y el Caribe", "value": "america central y el caribe"},
            {"label": "América del Norte", "value": "america del norte"},
            {"label": "Europa y Medio Oriente", "value": "europa y medio oriente"},
            {"label": "África, Asia y Oceanía", "value": "africa asia y oceania"},
        ]
    if "destino" in missing and scope == "pliegos_nacional" and (family in {None, "pliegos"}):
        return [
            {"label": "Local", "value": "local"},
            {"label": "Nacional", "value": "nacional"},
            {"label": "Prov. Dentro Depto.", "value": "prov dentro depto"},
            {"label": "Prov. Depto. Prov.", "value": "prov depto prov"},
        ]
    if "destino" in missing and scope == "pliegos_internacional" and (family in {None, "pliegos"}):
        return [
            {"label": "América del Sur", "value": "america del sur"},
            {"label": "América Central y el Caribe", "value": "america central y el caribe"},
            {"label": "América del Norte", "value": "america del norte"},
            {"label": "Europa y Medio Oriente", "value": "europa y medio oriente"},
            {"label": "África, Asia y Oceanía", "value": "africa asia y oceania"},
        ]
    if "destino" in missing and scope == "sacas_m_nacional" and (family in {None, "sacas_m"}):
        return [
            {"label": "Nacional", "value": "nacional"},
            {"label": "Provincial", "value": "provincial"},
        ]
    if "destino" in missing and scope == "sacas_m_internacional" and (family in {None, "sacas_m"}):
        return [
            {"label": "América del Sur", "value": "america del sur"},
            {"label": "América Central y el Caribe", "value": "america central y el caribe"},
            {"label": "América del Norte", "value": "america del norte"},
            {"label": "Europa y Medio Oriente", "value": "europa y medio oriente"},
            {"label": "África, Asia y Oceanía", "value": "africa asia y oceania"},
        ]
    if "destino" in missing and scope == "ems_contratos_nacional" and (family in {None, "ems_contratos"}):
        return [
            {"label": "EMS Nacional", "value": "ems nacional"},
            {"label": "Ciudades Intermedias", "value": "ciudades intermedias"},
            {"label": "Trinidad - Cobija", "value": "trinidad cobija"},
        ]
    if "destino" in missing and scope == "super_express_documentos_internacional" and (family in {None, "super_express_documentos"}):
        return [
            {"label": "Sudamérica (Tarifa 1)", "value": "sud america"},
            {"label": "Centroamérica/Florida (Tarifa 2)", "value": "centro america florida"},
            {"label": "Resto de EEUU (Tarifa 3)", "value": "resto de eeuu"},
            {"label": "Caribe (Tarifa 4)", "value": "caribe"},
            {"label": "Europa (Tarifa 5)", "value": "europa"},
            {"label": "Medio Oriente (Tarifa 6)", "value": "medio oriente"},
            {"label": "África y Asia (Tarifa 7)", "value": "africa y asia"},
        ]
    if "destino" in missing and scope == "super_express_paquetes_internacional" and (family in {None, "super_express_paquetes"}):
        return [
            {"label": "Sudamérica (Tarifa 1)", "value": "sud america"},
            {"label": "Centroamérica/Florida (Tarifa 2)", "value": "centro america florida"},
            {"label": "Resto de EEUU (Tarifa 3)", "value": "resto de eeuu"},
            {"label": "Caribe (Tarifa 4)", "value": "caribe"},
            {"label": "Europa (Tarifa 5)", "value": "europa"},
            {"label": "Medio Oriente (Tarifa 6)", "value": "medio oriente"},
            {"label": "África y Asia (Tarifa 7)", "value": "africa y asia"},
        ]
    return []


def _resolver_tarifa_en_turno(sid: str, pregunta: str, req: tarifas_skill.TarifaRequest) -> dict | None:
    """
    Completa consultas de tarifa en varios turnos usando estado temporal de sesión.
    Retorna un payload listo para jsonify() cuando corresponde interceptar el turno;
    en caso contrario retorna None para seguir flujo normal.
    """
    pendiente = session.get_pendiente_tarifa(sid) or {}
    if pendiente and _wants_reset_tarifa(pregunta):
        session.clear_pendiente_tarifa(sid)
        msg = "Listo, reinicié el cálculo de tarifa. Indícame peso y destino/servicio."
        session.agregar_turno(sid, pregunta, msg)
        return {"response": msg, "tarifa": {"ok": False, "pending": False, "reset": True}}

    fragment = tarifas_skill.extract_tarifa_fragment(
        pregunta,
        prefer_scope=pendiente.get("scope"),
        prefer_family=pendiente.get("family"),
    )
    level_choice = _extract_geo_level_choice(pregunta)
    scope_msg = req.scope or fragment.scope
    col_msg = req.columna or fragment.columna

    # Si el usuario responde solo "nacional/internacional", lo tratamos como paso
    # de navegación (nivel) y no como selección final de scope.
    if pendiente and level_choice and not (req.family or fragment.family):
        scope_msg = None
        col_msg = None

    should_resume_pending = bool(pendiente) and bool(
        req.is_tarifa or scope_msg or req.peso or col_msg or req.family or fragment.family or level_choice
    )
    if not req.is_tarifa and not should_resume_pending:
        return None

    pending_scope = pendiente.get("scope")
    pending_family = pendiente.get("family")
    pending_level = pendiente.get("level")
    family = req.family or fragment.family or pending_family
    scope = scope_msg or pending_scope
    peso = req.peso or fragment.peso or pendiente.get("peso")
    columna = col_msg or pendiente.get("columna")

    # Si el usuario está eligiendo servicio (y solo servicio), forzamos siguiente paso:
    # pedir destino en vez de inferir columna por palabras como "nacional".
    if pendiente and not pending_family and family and _is_service_selection_only(pregunta):
        columna = None

    level = pending_level or level_choice

    if scope in {
        "nacional", "encomienda_nacional", "ems_hoja5_nacional", "eca_nacional",
        "pliegos_nacional", "sacas_m_nacional", "ems_contratos_nacional", "super_express_nacional",
    }:
        level = "nacional"
    elif scope in {
        "internacional", "encomienda_internacional", "ems_hoja6_internacional", "eca_internacional",
        "pliegos_internacional", "sacas_m_internacional",
        "super_express_documentos_internacional", "super_express_paquetes_internacional",
    }:
        level = "internacional"
    if scope in {"nacional", "internacional"} and not family:
        scope = None

    forced_scope = _scope_from_family_and_level(family, level)
    if forced_scope:
        scope = forced_scope
    elif not scope:
        scope = _scope_from_family_and_level(family, level)

    # Si llega un destino que sugiere otro alcance, priorizamos la intención más reciente.
    fragment_scope = fragment.columna_scope
    if not family:
        if fragment_scope and pending_scope and fragment_scope != pending_scope and not scope_msg:
            scope = fragment_scope
        if scope_msg and pending_scope and scope_msg != pending_scope:
            scope = scope_msg
    else:
        # Con familia elegida, no permitimos saltar de EMS<->Encomienda por alias sueltos.
        scope_family = _family_for_scope(scope)
        if scope_family and scope_family != family:
            scope = forced_scope or pending_scope or scope

    if not scope and columna:
        scope = tarifas_skill.infer_scope_from_columna(columna)
    if scope in {
        "nacional", "encomienda_nacional", "ems_hoja5_nacional", "eca_nacional",
        "pliegos_nacional", "sacas_m_nacional", "ems_contratos_nacional", "super_express_nacional",
    }:
        level = "nacional"
    elif scope in {
        "internacional", "encomienda_internacional", "ems_hoja6_internacional", "eca_internacional",
        "pliegos_internacional", "sacas_m_internacional",
        "super_express_documentos_internacional", "super_express_paquetes_internacional",
    }:
        level = "internacional"
    if scope and not columna:
        columna = tarifas_skill.resolve_columna(pregunta, scope=scope) or tarifas_skill.default_columna_for_scope(scope)
    # Si la columna quedó incompatible con el alcance actual, pedimos nuevo destino/servicio.
    if columna and scope and not tarifas_skill.columna_valida_para_scope(columna, scope):
        columna = tarifas_skill.resolve_columna(pregunta, scope=scope)

    missing = _missing_tarifa_fields(scope, peso, columna, family=family, level=level)
    if missing:
        quick_replies = _tarifa_quick_replies(missing, scope=scope, family=family)
        session.set_pendiente_tarifa(
            sid,
            {
                "scope": scope,
                "family": family,
                "level": level,
                "peso": peso,
                "columna": columna,
            },
        )
        msg = tarifas_skill.missing_message(missing)
        session.agregar_turno(sid, pregunta, msg)
        return {
            "response": msg,
            "tarifa": {
                "ok": False,
                "missing": missing,
                "pending": True,
                "scope": scope,
                "family": family,
                "level": level,
                "peso": peso,
                "columna": columna,
            },
            "quick_replies": quick_replies,
        }

    resultado_tarifa = tarifas_skill.ejecutar_tarifa(
        peso=peso or "",
        columna=(columna or "").upper(),
        scope=scope or "",
    )
    if not resultado_tarifa.get("ok") and resultado_tarifa.get("error_code") == "out_of_range":
        alternativas = _out_of_range_alternatives(
            peso=peso or "",
            pregunta=pregunta,
            current_scope=scope or "",
            current_columna=(columna or "").upper() or None,
        )
        msg = "Peso fuera de rango para este tarifario."
        if alternativas:
            msg += " Puedes probar otro servicio del mismo alcance."
        session.set_pendiente_tarifa(
            sid,
            {
                "scope": scope,
                "family": family,
                "level": level,
                "peso": peso,
                "columna": None,
            },
        )
        session.agregar_turno(sid, pregunta, msg)
        return {
            "response": msg,
            "tarifa": {
                **resultado_tarifa,
                "scope": scope,
                "family": family,
                "level": level,
                "peso": peso,
            },
            "quick_replies": alternativas,
        }

    respuesta_tarifa = tarifas_skill.format_tarifa_response(resultado_tarifa)
    primary_skill = resultado_tarifa.get("skill_id") or "tarifa_ems"
    session.clear_pendiente_tarifa(sid)
    session.agregar_turno(sid, pregunta, respuesta_tarifa)
    return {
        "response": respuesta_tarifa,
        "tarifa": resultado_tarifa,
        "skill_resolution": {
            "in_scope": True,
            "primary_skill": primary_skill,
            "matched_skills": [primary_skill],
        },
    }


def _disparar_reindex_async(origen: str) -> bool:
    """
    Lanza reindexado en segundo plano para que cambios en Capacidades
    impacten en RAG sin acción manual posterior.
    """
    if _modo_general_only():
        return False

    def _run():
        try:
            observability.log_event("rag.reindex.auto_start", source=origen)
            reindexar()
            observability.log_event("rag.reindex.auto_done", source=origen)
        except Exception as exc:
            observability.log_event("rag.reindex.auto_error", source=origen, error=str(exc))

    threading.Thread(target=_run, daemon=True).start()
    return True


def _pdf_source_key(item: dict, idx: int) -> str:
    base = "||".join(
        [
            str(item.get("nombre_archivo") or f"pdf_{idx}"),
            str(item.get("url") or ""),
            str(item.get("pagina_fuente") or ""),
        ]
    )
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]


def _reindexar_pdfs_incremental() -> bool:
    if _modo_general_only():
        return False

    try:
        pdf_refresh = capabilities.reprocesar_pdfs_pendientes()
        if pdf_refresh.get("reprocesados"):
            print(
                "   PDFs reprocesados antes de indexado incremental: "
                f"{pdf_refresh['reprocesados']} | mejorados: {pdf_refresh['mejorados']} | "
                f"fallidos: {pdf_refresh['fallidos']}"
            )
    except Exception as e:
        print(f"   Error refrescando PDFs antes del indexado incremental: {e}")

    chunks, ids, metadatas = [], [], []
    try:
        pdf_path = os.path.join(os.path.dirname(DATA_FILE), "pdfs_contenido.json")
        if os.path.exists(pdf_path):
            with open(pdf_path, "r", encoding="utf-8") as f:
                pdfs = json.load(f)
            for idx, p in enumerate(pdfs):
                texto = p.get("texto_extraido") or ""
                if not texto:
                    continue
                nombre_pdf = p.get("nombre_archivo") or f"PDF {idx + 1}"
                key = _pdf_source_key(p, idx)
                pdf_chunks, pdf_ids, pdf_meta = rag.documento_a_chunks(
                    texto,
                    prefijo=f"pdf_{key}",
                    metadata_base={
                        "source_type": "pdf",
                        "source_name": nombre_pdf,
                        "source_label": nombre_pdf,
                        "source_url": p.get("url", ""),
                        "source_page": p.get("pagina_fuente", ""),
                        "extraction_method": p.get("metodo_extraccion", ""),
                        "pdf_key": key,
                    },
                )
                chunks += pdf_chunks
                ids += pdf_ids
                metadatas += pdf_meta
    except Exception as e:
        print(f"   Error leyendo PDF JSON en incremental: {e}")
        return False

    resultado = rag.reemplazar_por_source_type("pdf", chunks, ids, metadatas)
    print(
        "   Indexado incremental PDFs completado "
        f"(eliminados: {resultado.get('removed', 0)} | agregados: {resultado.get('added', 0)})"
    )
    return bool(resultado.get("ok"))


def _run_debounced_reindex(origen: str) -> None:
    global _reindex_mode
    modo = None
    with _reindex_lock:
        modo = _reindex_mode
        _reindex_mode = None
    if not modo:
        return
    try:
        observability.log_event("rag.reindex.debounce_start", source=origen, mode=modo)
        if modo == "full":
            reindexar()
        elif modo == "pdf_only":
            _reindexar_pdfs_incremental()
        observability.log_event("rag.reindex.debounce_done", source=origen, mode=modo)
    except Exception as exc:
        observability.log_event("rag.reindex.debounce_error", source=origen, mode=modo, error=str(exc))


def _programar_reindex_debounced(origen: str, mode: str = "full") -> bool:
    """
    Programa reindex con debounce para evitar rebuilds consecutivos.
    mode:
      - full: rebuild completo
      - pdf_only: reindex incremental de PDFs
    """
    global _reindex_timer, _reindex_mode
    if _modo_general_only():
        return False
    if mode not in {"full", "pdf_only"}:
        mode = "full"

    with _reindex_lock:
        # full tiene prioridad sobre incremental
        if _reindex_mode == "full" or mode == "full":
            _reindex_mode = "full"
        else:
            _reindex_mode = "pdf_only"

        if _reindex_timer is not None:
            _reindex_timer.cancel()

        _reindex_timer = threading.Timer(
            REINDEX_DEBOUNCE_SECONDS,
            lambda: _run_debounced_reindex(origen),
        )
        _reindex_timer.daemon = True
        _reindex_timer.start()

    observability.log_event(
        "rag.reindex.debounce_scheduled",
        source=origen,
        mode=mode,
        debounce_seconds=REINDEX_DEBOUNCE_SECONDS,
    )
    return True


# ─────────────────────────────────────────────
#  REINDEXADO
# ─────────────────────────────────────────────

def reindexar() -> bool:
    """Indexa en ChromaDB los datos generados por el scraper.

    Además del texto principal y las sucursales/secciones, incorpora los
    textos extraídos de los PDF que el scraper descargó. El JSON
    `pdfs_contenido.json` está situado en el mismo directorio de datos.
    """
    global SUCURSALES
    chunks, ids, metadatas = [], [], []

    try:
        pdf_refresh = capabilities.reprocesar_pdfs_pendientes()
        if pdf_refresh.get("reprocesados"):
            print(
                "   PDFs reprocesados antes de indexar: "
                f"{pdf_refresh['reprocesados']} | mejorados: {pdf_refresh['mejorados']} | "
                f"fallidos: {pdf_refresh['fallidos']}"
            )
    except Exception as e:
        print(f"   Error refrescando PDFs antes del RAG: {e}")

    # 1. Texto principal (HTML plano acumulado)
    c, i, m = rag.archivo_a_documentos(
        DATA_FILE,
        prefijo="txt",
        metadata_base={
            "source_type": "web_main",
            "source_label": "Sitio principal de Correos de Bolivia",
            "source_path": DATA_FILE,
        },
    )
    chunks += c; ids += i; metadatas += m

    # 2. Sucursales
    SUCURSALES = location.cargar_sucursales(SUCURSALES_FILE)
    for idx, s in enumerate(SUCURSALES):
        nombre = s.get("nombre", f"Sucursal {idx + 1}")
        c, i, m = rag.documento_a_chunks(
            location.sucursal_a_texto(s),
            prefijo=f"suc_{idx}",
            metadata_base={
                "source_type": "branch",
                "source_name": nombre,
                "source_label": nombre,
                "city": nombre,
            },
        )
        chunks += c; ids += i; metadatas += m

    # 3. Secciones del home
    c, i = location.cargar_secciones(SECCIONES_FILE)
    for idx, texto in enumerate(c):
        source_name = i[idx] if idx < len(i) else f"seccion_{idx}"
        sec_chunks, sec_ids, sec_meta = rag.documento_a_chunks(
            texto,
            prefijo=source_name,
            metadata_base={
                "source_type": "section",
                "source_name": source_name,
                "source_label": source_name.replace("sec_", "").replace("_", " "),
            },
        )
        chunks += sec_chunks; ids += sec_ids; metadatas += sec_meta

    # 4. Contenido de PDFs (si existe el JSON generado por el scraper)
    try:
        pdf_path = os.path.join(os.path.dirname(DATA_FILE), "pdfs_contenido.json")
        if os.path.exists(pdf_path):
            with open(pdf_path, "r", encoding="utf-8") as f:
                pdfs = json.load(f)
            for idx, p in enumerate(pdfs):
                texto = p.get("texto_extraido") or ""
                if texto:
                    nombre_pdf = p.get("nombre_archivo") or f"PDF {idx + 1}"
                    pdf_chunks, pdf_ids, pdf_meta = rag.documento_a_chunks(
                        texto,
                        prefijo=f"pdf_{idx}",
                        metadata_base={
                            "source_type": "pdf",
                            "source_name": nombre_pdf,
                            "source_label": nombre_pdf,
                            "source_url": p.get("url", ""),
                            "source_page": p.get("pagina_fuente", ""),
                            "extraction_method": p.get("metodo_extraccion", ""),
                        },
                    )
                    chunks += pdf_chunks; ids += pdf_ids; metadatas += pdf_meta
    except Exception as e:
        print(f"   Error leyendo PDF JSON: {e}")

    # 5. Historia institucional (si existe el JSON generado por el scraper)
    try:
        historia_path = HISTORIA_FILE
        if historia_path and not os.path.isabs(historia_path):
            historia_path = os.path.join(os.path.dirname(DATA_FILE), os.path.basename(historia_path))
        if os.path.exists(historia_path):
            with open(historia_path, "r", encoding="utf-8") as f:
                historia = json.load(f)
            for idx, item in enumerate(historia):
                if not isinstance(item, dict):
                    continue
                contenido = (item.get("contenido") or "").strip()
                if not contenido:
                    continue
                titulo = item.get("titulo") or f"Historia {idx + 1}"
                hist_chunks, hist_ids, hist_meta = rag.documento_a_chunks(
                    contenido,
                    prefijo=f"hist_{idx}",
                    metadata_base={
                        "source_type": "history",
                        "source_name": titulo,
                        "source_label": titulo,
                        "source_url": item.get("url", ""),
                        "years": ", ".join(str(y) for y in item.get("anos_mencionados", [])[:12]),
                    },
                )
                chunks += hist_chunks; ids += hist_ids; metadatas += hist_meta
    except Exception as e:
        print(f"   Error leyendo historia institucional: {e}")

    return rag.indexar(chunks, ids, metadatas=metadatas)


# ─────────────────────────────────────────────
#  INICIALIZACIÓN
# ─────────────────────────────────────────────

def inicializar():
    """Llamar desde main.py al arrancar la app."""
    global SUCURSALES
    print(f"\n🤖 Iniciando {NOMBRE}...")

    SUCURSALES = location.cargar_sucursales(SUCURSALES_FILE)

    if _modo_general_only():
        print("  Modo general activo → sin embeddings, sin ChromaDB y sin RAG al arranque")
        updater.iniciar_scheduler(reindexar_fn=reindexar)
        print(f" {NOMBRE} listo en http://localhost:5000\n")
        return

    rag.inicializar(chroma_path=CHROMA_PATH, collection_name="general")

    if rag.total_chunks() == 0:
        print("  BD vacía → indexando datos del scraper...")
        reindexar()
    else:
        print(f" BD lista ({rag.total_chunks()} chunks)")
        SUCURSALES = location.cargar_sucursales(SUCURSALES_FILE)
        threading.Thread(target=_refresh_pdfs_after_start, daemon=True).start()

    updater.iniciar_scheduler(reindexar_fn=reindexar)
    print(f" {NOMBRE} listo en http://localhost:5000\n")


# ─────────────────────────────────────────────
#  RUTAS
# ─────────────────────────────────────────────

@bp.route("/api/welcome", methods=["GET"])
def welcome():
    lang = request.args.get("lang", idiomas.IDIOMA_DEFAULT)
    if lang not in idiomas.IDIOMAS:
        lang = idiomas.IDIOMA_DEFAULT
    return jsonify({"response": idiomas.IDIOMAS[lang]["bienvenida"], "lang": lang})


@bp.route("/api/chat", methods=["POST"])
def chat():
    sid = session.get_sid()

    data     = request.get_json(silent=True) or {}
    pregunta = data.get("message", "").strip()

    if not pregunta:
        return jsonify({"error": "Pregunta vacía"}), 400

    # resolver el idioma lo antes posible para usarlo también en respuestas
    lang = idiomas.resolver_idioma(data.get("lang"), pregunta)

    pendiente_tarifa = session.get_pendiente_tarifa(sid) or {}
    level_choice = _extract_geo_level_choice(pregunta)
    explicit_family = tarifas_skill.detect_family(pregunta)
    only_level_choice = bool(
        pendiente_tarifa
        and level_choice in {"nacional", "internacional"}
        and not pendiente_tarifa.get("family")
    )
    llm_hint = _llm_orquestar_tarifa(pregunta, pendiente_tarifa) if not pendiente_tarifa else None

    # ── Consulta de tarifas (skill externa)
    tarifa_req = tarifas_skill.parse_tarifa_request(pregunta)
    if llm_hint and llm_hint.get("is_info_only"):
        tarifa_req.is_tarifa = False
    elif llm_hint and llm_hint.get("use_tarifa_flow") and llm_hint.get("confidence", 0.0) >= 0.55:
        tarifa_req.is_tarifa = True
        if explicit_family and not tarifa_req.family:
            tarifa_req.family = explicit_family
        allow_family_hint = bool(explicit_family or pendiente_tarifa.get("family"))
        if (
            not only_level_choice
            and not tarifa_req.family
            and llm_hint.get("family")
            and allow_family_hint
        ):
            tarifa_req.family = llm_hint.get("family")
        if not only_level_choice and not tarifa_req.scope and llm_hint.get("scope"):
            tarifa_req.scope = llm_hint.get("scope")
        if not tarifa_req.peso and llm_hint.get("peso"):
            tarifa_req.peso = llm_hint.get("peso")
        if not tarifa_req.columna and llm_hint.get("columna"):
            tarifa_req.columna = llm_hint.get("columna")

    tarifa_payload = _resolver_tarifa_en_turno(sid, pregunta, tarifa_req)
    if tarifa_payload is not None:
        tarifa_payload["lang"] = lang
        return jsonify(tarifa_payload)

    # traducción automática: el frontend envía un mensaje como
    # "Traduce EXACTAMENTE este texto al <idioma>...". No queremos aplicar
    # la detección de intenciones ni devolver la lista de sucursales.
    # Simplemente reenviamos la petición al modelo y devolvemos lo que diga.
    if pregunta.lower().startswith("traduce exactamente"):
        try:
            # construimos mensajes mínimos para Ollama
            respuesta = ollama.llamar_ollama([
                {"role": "user", "content": pregunta}
            ])
            respuesta = ollama.limpiar_respuesta(respuesta)
            return jsonify({"response": respuesta, "lang": lang})
        except Exception as e:
            return jsonify({"error": f"Error traduciéndose: {e}"}), 500

    if _modo_general_only():
        local_result = buscar_contexto_local_minimo(pregunta, DATA_FILE, HISTORIA_FILE)
        contexto = local_result.get("context", "").strip()
        sistema = (
            f"CRITICAL LANGUAGE RULE: {idiomas.IDIOMAS[lang]['instruccion']} "
            f"You MUST respond ONLY in that language.\n\n"
            "Eres un asistente que razona SOLO con el CONTEXTO LOCAL proporcionado.\n"
            "Tu tarea es interpretar, resumir y responder con claridad usando exclusivamente ese contenido.\n"
            "Responde de forma breve, puntual y útil. Prioriza la respuesta directa antes que la explicación larga.\n"
            "Si la pregunta pide un dato puntual, responde primero con ese dato en una o dos frases.\n"
            "Solo añade una breve aclaración extra si realmente mejora la comprensión.\n"
            "No inventes datos, no completes huecos con conocimiento externo y no afirmes nada que no esté sustentado en el contexto.\n"
            f"Si el contexto no alcanza para responder, di exactamente: \"{respuesta_chat_vacio(lang, pregunta)}\"\n"
            "Si el usuario pide una explicación, puedes reorganizar la información y redactarla de forma más clara, "
            "pero sin salirte del contenido disponible.\n\n"
            f"CONTEXTO LOCAL:\n{contexto}\n"
        )
        mensajes = [
            {"role": "system", "content": sistema},
            {"role": "user", "content": pregunta},
        ]

        try:
            respuesta = ollama.limpiar_respuesta(ollama.llamar_ollama(mensajes))
            respuesta_limpia = (respuesta or "").strip()
            if not respuesta_limpia:
                respuesta = respuesta_chat_vacio(lang, pregunta)
        except Exception:
            return jsonify({"error": "Error razonando con la IA sobre el contexto local."}), 500

        # conservar saltos de línea para que el frontend pueda mostrar la
        # respuesta completa con mejor legibilidad.
        respuesta = (respuesta or "").strip()
        if CHAT_RESPONSE_MAX_CHARS > 0 and len(respuesta) > CHAT_RESPONSE_MAX_CHARS:
            respuesta = respuesta[:CHAT_RESPONSE_MAX_CHARS].rsplit(" ", 1)[0].strip() + "..."

        session.agregar_turno(sid, pregunta, respuesta)
        return jsonify({
            "response": respuesta,
            "lang": lang,
            "general_only": True,
            "skill_resolution": {
                "in_scope": None,
                "primary_skill": None,
                "matched_skills": [],
            },
            "sources": local_result.get("sources", []),
            "primary_source_type": local_result.get("primary_source_type"),
        })

    # si el usuario responde con un pedido corto, reorganizamos la pregunta para
    # no perder el tema anterior. La función `es_pedido_corto` revisa comandos
    # como "dame" o mensajes muy breves.
    if intents.es_pedido_corto(pregunta):
        hist = session.get_historial(session.get_sid())
        # buscar el último mensaje del propio usuario en el historial
        last_user = None
        for entry in reversed(hist):
            if entry.get("role") == "user":
                last_user = entry.get("content")
                break
        if last_user:
            nueva = f"{last_user} {pregunta}"
            print(f" Follow‑up detectado, reescribiendo pregunta: '{pregunta}' → '{nueva}'")
            pregunta = nueva  # añade contexto

    t    = idiomas.IDIOMAS[lang]
    skill_resolution = capabilities.resolve_skills_for_query(pregunta)

    consulta_especial = capabilities.detectar_consulta_especial(pregunta)
    if consulta_especial is not None:
        estado = _estado_capacidades()
        resultado = capabilities.execute_special_query(consulta_especial, estado)
        respuesta = resultado["response"]
        session.agregar_turno(sid, pregunta, respuesta)
        return jsonify(
            {
                "response": respuesta,
                "lang": lang,
                "capabilities": estado,
                "tool_result": resultado,
            }
        )

    # ── 1. Saludo → sin Ollama
    if intents.es_saludo(pregunta):
        return jsonify({"response": t["saludo"], "lang": lang})

    # ── 1.5 Presentación
    if intents.es_presentacion(pregunta):
        return jsonify({
            "response": (
                "Soy ChatbotBO, el asistente virtual de la Agencia Boliviana de "
                "Correos. ¿En qué puedo ayudarte?"
            ),
            "lang": lang,
        })

    # ── 2. Despedida
    if intents.es_despedida(pregunta):
        session.limpiar_historial(sid)
        return jsonify({"response": t["despedida"], "despedida": True, "lang": lang})

    # ── 3. ¿Solo nombre de ciudad?
    geo = intents.detectar_solo_ciudad(pregunta, SUCURSALES)

    # ── 4. ¿Consulta de ubicación con palabras clave?
    if geo is None:
        geo = intents.detectar_consulta_ubicacion(pregunta, SUCURSALES)

    # ── 5. Responder con tarjeta de sucursal
    if geo is not None:
        if "nombre" not in geo:
            nombres = " | ".join(s.get("nombre", "") for s in SUCURSALES)
            # usar .get para evitar KeyError si la traducción falta en caliente
            mensaje = t.get("pedir_ciudad")
            if mensaje is None:
                # el servidor puede estar ejecutándose con una versión antigua de
                # idiomas.py; reiniciar lo recargará y evitará este error.
                mensaje = f"Por favor indica una ciudad válida: {nombres}"
            else:
                mensaje = mensaje.format(ciudades=nombres)

            return jsonify({
                "response": mensaje,
                "lang"    : lang,
                "no_translate": True,   # no traducir esta frase cuando el usuario cambie idioma
            })

        lat      = geo.get("lat")
        lng      = geo.get("lng")
        maps_url = location.generar_maps_url(lat, lng) if lat and lng else None
        nd       = t["no_disponible"]

        texto_resp = (
            f" {geo.get('nombre', '')}\n"
            f"Dirección : {geo.get('direccion') or nd}\n"
            f"Teléfono  : {geo.get('telefono') or nd}\n"
            f"Email     : {geo.get('email') or nd}\n"
            f"Horario   : {geo.get('horario') or nd}"
        )
        if maps_url:
            texto_resp += f"\nVer en mapa: {maps_url}"

        session.agregar_turno(sid, pregunta, texto_resp)

        resp_json = {"response": texto_resp, "lang": lang}
        if lat and lng:
            resp_json["ubicacion"] = {
                "nombre"   : geo.get("nombre",    ""),
                "direccion": geo.get("direccion", ""),
                "telefono" : geo.get("telefono",  ""),
                "email"    : geo.get("email",     ""),
                "horario"  : geo.get("horario",   ""),
                "lat"      : lat,
                "lng"      : lng,
                "maps_url" : maps_url,
            }
        return jsonify(resp_json)

    if not skill_resolution["in_scope"]:
        respuesta = capabilities.out_of_scope_response()
        session.agregar_turno(sid, pregunta, respuesta)
        return jsonify({
            "response": respuesta,
            "lang": lang,
            "skill_resolution": {
                "in_scope": False,
                "primary_skill": None,
                "matched_skills": [],
            },
        })

    # ── 6. Consulta general → RAG + Ollama
    try:
        rag_result = rag.buscar(
            pregunta,
            preferred_source_types=capabilities.preferred_sources_for_skill(
                skill_resolution.get("primary_skill")
            ),
        )
        contexto = rag_result.get("context", "")
    except Exception as e:
        return jsonify({"error": f"Error en búsqueda RAG: {e}"}), 500

    sources = rag_result.get("sources", [])
    valid_sources = [s for s in sources if s.get("source_type") and s.get("source_type") != "unknown"]
    if not contexto.strip() or not valid_sources:
        respuesta = t["sin_info"]
        session.agregar_turno(sid, pregunta, respuesta)
        return jsonify({
            "response": respuesta,
            "lang": lang,
            "skill_resolution": {
                "in_scope": skill_resolution["in_scope"],
                "primary_skill": (skill_resolution.get("primary_skill") or {}).get("id"),
                "matched_skills": skill_resolution.get("skill_ids", []),
            },
            "sources": sources,
            "primary_source_type": rag_result.get("primary_source_type"),
        })

    hora     = session.get_hora_bolivia()
    primary_skill = skill_resolution.get("primary_skill") or {}
    sistema  = construir_prompt(
        t["instruccion"],
        contexto,
        hora,
        t["sin_info"],
        skills_context="",
        skill_name=primary_skill.get("nombre", ""),
        skill_description=primary_skill.get("descripcion", ""),
        skill_triggers=primary_skill.get("trigger", ""),
    )
    mensajes = [
        {"role": "system", "content": sistema},
        *session.historial_reciente(sid),
        {"role": "user",   "content": pregunta},
    ]
    mensajes = _trim_messages_to_token_budget(mensajes, ollama.OLLAMA_PROMPT_MAX_TOKENS)
    prompt_tokens = sum(_estimate_message_tokens(m) for m in mensajes)
    observability.log_event(
        "llm.request",
        lang=lang,
        model=ollama.LLM_MODEL,
        primary_skill=primary_skill.get("id"),
        prompt_tokens=prompt_tokens,
        source_type=rag_result.get("primary_source_type"),
        source_count=len(sources),
    )

    try:
        print(f" [{lang}] {pregunta[:60]}")
        respuesta = ollama.llamar_ollama(mensajes)
        respuesta = ollama.limpiar_respuesta(respuesta)
        observability.log_event(
            "llm.response",
            lang=lang,
            model=ollama.LLM_MODEL,
            primary_skill=primary_skill.get("id"),
            response_chars=len(respuesta),
            prompt_tokens=prompt_tokens,
        )

        # Guardia anti-alucinación: si se exige evidencia, solo aceptamos la
        # respuesta si trae 1-2 citas literales que existan en el contexto RAG.
        if REQUIRE_EVIDENCE:
            citas = extraer_citas_evidencia(respuesta)
            if not validar_evidencia_en_contexto(citas, contexto):
                respuesta = t["sin_info"]

        # si el modelo no encontró nada relevante a partir del contexto, a
        # veces devuelve simplemente el system prompt o la frase de
        # presentación. Detectamos esa situación y devolvemos el texto de
        # "sin_info" en lugar de repetir el saludo.
        presentacion_corta = (
            "Soy ChatbotBO, el asistente virtual de la Agencia Boliviana de "
            "Correos. ¿En qué puedo ayudarte?"
        )
        if respuesta.startswith("Eres ChatbotBO") or respuesta.strip().startswith(presentacion_corta):
            respuesta = t["sin_info"]

        session.agregar_turno(sid, pregunta, respuesta)
        print(f" [{lang}] {len(respuesta)} chars")
        return jsonify({
            "response": respuesta,
            "lang": lang,
            "skill_resolution": {
                "in_scope": skill_resolution["in_scope"],
                "primary_skill": primary_skill.get("id"),
                "matched_skills": skill_resolution.get("skill_ids", []),
            },
            "sources": rag_result.get("sources", []),
            "primary_source_type": rag_result.get("primary_source_type"),
        })

    except requests.exceptions.Timeout:
        return jsonify({"error": "El modelo tardó demasiado. Intenta de nuevo."}), 504
    except Exception as e:
        return jsonify({"error": f"Error generando respuesta: {e}"}), 500

# ─────────────────────────────────────────────
#  TRADUCCIÓN POR LOTES
# ─────────────────────────────────────────────

@bp.route("/api/translate", methods=["POST"])
def translate_bulk():
    """
    Traduce texto(s) a un idioma objetivo.

    Se espera un JSON con al menos:
      { "lang": "en" }
    Opcionalmente el cliente puede pasar un array de textos explícitos:
      { "texts": ["hola", "adios"], "lang": "en" }
    Si `texts` no está presente, la función usa el historial de la sesión
    para reconstruir los textos.

    Devuelve: { "translations": ["texto1", "texto2", ...], "lang": lang }
    """
    data = request.get_json(silent=True) or {}
    lang = data.get("lang", idiomas.IDIOMA_DEFAULT)

    # 1. Preparar lista inicial de textos a traducir. El frontend puede
    #    proporcionar el array directamente, lo cual evita discrepancias
    #    entre lo que el usuario ve y lo que el servidor guarda en sesión.
    textos_a_traducir = data.get("texts")

    if textos_a_traducir is None:
        # No se enviaron textos explícitos: reconstruimos a partir del
        # historial de la sesión, como antes.
        sid = session.get_sid()
        historial = session.get_historial(sid)
        if not historial:
            return jsonify({"translations": [], "lang": lang})

        textos_a_traducir = []
        for entry in historial:
            content = entry.get("content", "")
            if " " in content or "Ver en mapa:" in content or entry.get("role") == "system":
                continue
            textos_a_traducir.append(content)

        if not textos_a_traducir:
            return jsonify({"translations": [], "lang": lang})

    print(f"🔤 Traducción solicitada ({lang}) para {len(textos_a_traducir)} textos")
    try:
        traducciones, backend = translate_texts(textos_a_traducir, lang, ollama)
        observability.log_event(
            "translation.bulk",
            lang=lang,
            texts=len(textos_a_traducir),
            backend=backend,
        )
        return jsonify({"translations": traducciones, "lang": lang, "backend": backend})
    except Exception as e:
        print(f"  Error en traducción por lotes: {e}")
        return jsonify({"error": f"Error en traducción: {e}"}), 500


@bp.route("/api/sucursales", methods=["GET"])
def listar_sucursales():
    return jsonify({"sucursales": [location.sucursal_a_dict(s) for s in SUCURSALES]})


@bp.route("/api/idiomas", methods=["GET"])
def listar_idiomas():
    return jsonify({
        "idiomas": [{"code": c, "nombre": d["nombre"]} for c, d in idiomas.IDIOMAS.items()]
    })


@bp.route("/api/reset", methods=["POST"])
def reset():
    session.limpiar_historial(session.get_sid())
    return jsonify({"ok": True})


@bp.route("/api/status", methods=["GET"])
def status():
    estado_cap = _estado_capacidades()
    return jsonify({
        "status"          : "ok",
        "chunks"          : _rag_chunks_seguro(),
        "modelo"          : os.environ.get("LLM_MODEL", "correos-bot"),
        "ollama"          : ollama.ollama_disponible(),
        "sesiones_activas": session.total_sesiones(),
        "sucursales"      : len(SUCURSALES),
        "idiomas"         : list(idiomas.IDIOMAS.keys()),
        "actualizacion"   : updater.get_estado(),
        "skills"          : estado_cap["skills"],
        "rag"             : estado_cap["rag"],
        "general_only"    : _modo_general_only(),
    })


@bp.route("/api/metrics", methods=["GET"])
def metrics():
    return jsonify(observability.get_observability_snapshot())


@bp.route("/api/capabilities", methods=["GET"])
def listar_capacidades():
    return jsonify(_estado_capacidades())


@bp.route("/api/capabilities/options", methods=["GET"])
def listar_opciones_capacidades():
    return jsonify(capabilities.management_options())


@bp.route("/api/pdfs", methods=["GET"])
def listar_pdfs():
    return jsonify({
        "pdfs": capabilities.listar_pdfs(),
        "resumen": capabilities.resumen_pdfs(),
    })


@bp.route("/api/scraping", methods=["GET"])
def scraping_info():
    return jsonify(capabilities.get_scraping_summary())


@bp.route("/api/pdfs/upload", methods=["POST"])
def subir_pdf():
    archivo = request.files.get("file")
    fuente_url = request.form.get("fuente_url", "")
    pagina_fuente = request.form.get("pagina_fuente", "")
    clean_mode = request.form.get("clean_mode", "")
    try:
        resultado = capabilities.guardar_pdf_subido(
            archivo,
            fuente_url=fuente_url,
            pagina_fuente=pagina_fuente,
            clean_mode=clean_mode,
        )
        resultado["reindex_started"] = _programar_reindex_debounced("pdf_upload", mode="pdf_only")
        return jsonify(resultado), 201 if resultado.get("created") else 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Error subiendo PDF: {e}"}), 500


@bp.route("/api/pdfs/<path:nombre_archivo>", methods=["DELETE"])
def eliminar_pdf(nombre_archivo: str):
    try:
        resultado = capabilities.eliminar_pdf(nombre_archivo)
        resultado["reindex_started"] = _programar_reindex_debounced("pdf_delete", mode="pdf_only")
        return jsonify(resultado)
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": f"Error eliminando PDF: {e}"}), 500


@bp.route("/api/pdfs/<path:nombre_archivo>", methods=["PUT"])
def editar_pdf_texto(nombre_archivo: str):
    data = request.get_json(silent=True) or {}
    texto_extraido = data.get("texto_extraido", "")
    if texto_extraido is not None and not isinstance(texto_extraido, str):
        return jsonify({"error": "texto_extraido debe ser string"}), 400
    try:
        resultado = capabilities.actualizar_texto_pdf(nombre_archivo, texto_extraido)
        resultado["reindex_started"] = _programar_reindex_debounced("pdf_manual_edit", mode="pdf_only")
        return jsonify(resultado)
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": f"Error editando PDF: {e}"}), 500


@bp.route("/api/skills", methods=["GET"])
def listar_skills():
    return jsonify({"skills": _estado_capacidades()["skills"]})


@bp.route("/api/skills", methods=["POST"])
def guardar_skill():
    data = request.get_json(silent=True) or {}
    try:
        resultado = capabilities.guardar_skill(data)
        # skills afectan resolución/prompt, no requieren reindex vectorial
        resultado["reindex_started"] = False
        return jsonify(resultado), 201 if resultado["created"] else 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Error guardando skill: {e}"}), 500


@bp.route("/api/skills/<skill_id>", methods=["DELETE"])
def eliminar_skill(skill_id: str):
    if capabilities.eliminar_skill(skill_id):
        return jsonify({
            "ok": True,
            "id": skill_id,
            "reindex_started": False,
        })
    return jsonify({"error": "Skill no encontrada"}), 404


@bp.route("/api/actualizar", methods=["POST"])
def actualizar():
    if updater.estado["en_proceso"]:
        return jsonify({"ok": False, "mensaje": "  Actualización ya en proceso."}), 409
    updater.disparar_manual(reindexar_fn=reindexar)
    return jsonify({"ok": True, "mensaje": "  Actualización iniciada."})


@bp.route("/api/tarifa", methods=["POST"])
def calcular_tarifa():
    data = request.get_json(silent=True) or {}
    peso = (data.get("peso") or "").strip()
    scope = tarifas_skill.resolve_scope(data.get("scope") or data.get("alcance") or data.get("tipo"))
    columna = tarifas_skill.resolve_columna(data.get("columna"), scope=scope) or ""
    destino = (data.get("destino") or "").strip()
    servicio = (data.get("servicio") or "").strip()
    pregunta = (data.get("message") or "").strip()

    if not columna and destino:
        columna = tarifas_skill.resolve_columna(destino, scope=scope) or ""
    if not columna and servicio:
        columna = tarifas_skill.resolve_columna(servicio, scope=scope) or ""
    if not scope and columna:
        scope = tarifas_skill.infer_scope_from_columna(columna)

    if not peso or not columna or not scope:
        req = tarifas_skill.parse_tarifa_request(pregunta)
        if not scope:
            scope = req.scope
        if not peso:
            peso = req.peso or ""
        if not columna:
            columna = (req.columna or "").upper()

    if not scope:
        return jsonify({"ok": False, "error": tarifas_skill.missing_message(["alcance"])}), 400

    if not peso:
        return jsonify({"ok": False, "error": tarifas_skill.missing_message(["peso"])}), 400
    if not columna:
        return jsonify({"ok": False, "error": tarifas_skill.missing_message(["destino"])}), 400

    resultado = tarifas_skill.ejecutar_tarifa(
        peso=peso,
        columna=columna,
        scope=scope,
        xlsx=(data.get("xlsx") or "").strip() or None,
    )
    status = 200 if resultado.get("ok") else 422
    return jsonify(resultado), status


@bp.route("/api/rag/rebuild", methods=["POST"])
def rebuild_rag():
    try:
        print("  Iniciando rebuild limpio del RAG...")
        exito = reindexar()
        if not exito:
            return jsonify({"ok": False, "error": "No se pudieron indexar documentos en el rebuild limpio del RAG."}), 500
        print(f"  Rebuild limpio del RAG completado ({rag.total_chunks()} chunks).")
        return jsonify({
            "ok": True,
            "mensaje": "Rebuild limpio del RAG completado.",
            "chunks": rag.total_chunks(),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": f"Error en rebuild limpio del RAG: {e}"}), 500


# ─────────────────────────────────────────────
#  COMPATIBILIDAD / API GENÉRICA
# ─────────────────────────────────────────────
# El widget original usaba un único endpoint `/api` con campos
# `action` o `message` para decidir qué hacer. La implementación actual
# ha dividido esto en rutas REST más explícitas, pero mantener un
# manejador genérico ayuda a que integraciones existentes no se rompan.

@bp.route("/api", methods=["GET", "POST"])
def api_root():
    """Ruteador ligero para compatibilidad con versiones antiguas del
    widget y otros clientes que envían `action` en vez de llamar a
    subrutas específicas.

    - GET  /api?action=sucursales  → lista sucursales
    - GET  /api?action=idiomas     → lista de idiomas
    - POST /api {"action":"translate", ...} → translate_bulk
    - POST /api {"action":"reset"}        → reset
    - POST /api {"action":"rebuild_rag"}  → rebuild_rag
    - POST /api {"message":...}            → chat
    """
    if request.method == "GET":
        act = request.args.get("action")
        if act == "sucursales":
            return listar_sucursales()
        if act == "idiomas":
            return listar_idiomas()
        return jsonify({"error": "action no soportada"}), 400

    # POST
    data = request.get_json(silent=True) or {}
    act = data.get("action")
    if act == "translate":
        # el método translate_bulk espera 'lang' y 'texts' opcionales
        return translate_bulk()
    if act == "reset":
        return reset()
    if act == "rebuild_rag":
        return rebuild_rag()
    # si el cuerpo contiene 'message' asumimos chat
    if "message" in data:
        return chat()
    return jsonify({"error": "requisição inválida"}), 400
