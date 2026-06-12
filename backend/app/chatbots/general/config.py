"""
chatbots/general/config.py
Configuración específica del chatbot general.
Aquí cambias el system prompt, los archivos de data y los parámetros.
"""

import os
from core import contacto

# ─────────────────────────────────────────────
#  IDENTIDAD
# ─────────────────────────────────────────────
NOMBRE = "ChatbotBO"
PUERTO = int(os.environ.get("PORT", "5000"))

# ─────────────────────────────────────────────
#  ANTI-ALUCINACIÓN (opcional)
# ─────────────────────────────────────────────
REQUIRE_EVIDENCE = os.environ.get("REQUIRE_EVIDENCE", "false").strip().lower() in ("1", "true", "yes")

# ─────────────────────────────────────────────
#  ARCHIVOS DE DATA (generados por el scraper)
# ─────────────────────────────────────────────
DATA_FILE        = os.environ.get("DATA_FILE",        "data/correos_bolivia.txt")
SUCURSALES_FILE  = os.environ.get("SUCURSALES_FILE",  "data/sucursales_contacto.json")
SECCIONES_FILE   = os.environ.get("SECCIONES_FILE",   "data/secciones_home.json")
HISTORIA_FILE    = os.environ.get("HISTORIA_FILE",    "data/historia_institucional.json")
INFORMACION_FILE = os.environ.get("INFORMACION_FILE", "data/pdfs_contenido.json")
CHROMA_PATH      = os.environ.get("CHROMA_PATH",      "chroma_db")

# ─────────────────────────────────────────────
#  SYSTEM PROMPT BASE
# ─────────────────────────────────────────────
def _build_system_prompt() -> str:
    """System prompt reforzado anti-alucinacion para modelo pequeno."""
    tel = contacto.telefono()
    web = contacto.web()
    horario = contacto.horario_resumen()
    return (
        f"Eres ChatbotBO de Correos de Bolivia. Web: {web} | Tel: {tel} | Horario: {horario}\n"
        "INSTRUCCION CRITICA — LEE PRIMERO:\n"
        "1. SOLO puedes usar la INFORMACION OFICIAL que aparece abajo en este mensaje.\n"
        "2. NO uses tu conocimiento interno. NO inventes. NO supongas.\n"
        "3. Si la respuesta NO esta en la INFORMACION OFICIAL, responde UNICAMENTE con la frase de no-info.\n"
        "4. Responde en el mismo idioma del usuario. Max 150 palabras.\n"
        "5. Sin markdown. Responde de forma natural y conversacional, como un asistente amable.\n"
    )

SYSTEM_PROMPT = _build_system_prompt()


def construir_prompt(
    instruccion_idioma: str,
    contexto: str,
    hora: dict,
    sin_info: str,
    skills_context: str = "",
    skill_name: str = "",
    skill_description: str = "",
    skill_triggers: str = "",
) -> str:
    """Construye el system prompt completo para inyectar en Ollama."""

    skill_hint = ""
    if skill_name or skill_description:
        skill_hint = (
            f"SKILL PRINCIPAL PARA ESTA CONSULTA: {skill_name or 'General'}.\n"
            f"DESCRIPCIÓN: {skill_description or ''}\n"
            f"RESPONDE ENFOCADO EN ESTE TEMA.\n\n"
        )

    # Si el contexto está vacío, instrucción directa de fallback
    if not (contexto or "").strip():
        return (
            f"NORMAS: {instruccion_idioma}. Responde únicamente en ese idioma.\n\n"
            f"{SYSTEM_PROMPT}\n\n"
            f"INFORMACIÓN OFICIAL: [Sin información disponible]\n\n"
            f"INSTRUCCIÓN ÚNICA: No hay información disponible. "
            f"Responde EXACTAMENTE: \"{sin_info}\""
        )

    return (
        f"NORMAS: {instruccion_idioma}. Responde únicamente en ese idioma.\n\n"
        f"{SYSTEM_PROMPT}\n\n"
        f"FECHA Y HORA EN BOLIVIA: {hora['fecha']} {hora['hora']} — {hora['estado']}\n\n"
        f"{skill_hint}"
        f"INFORMACION OFICIAL (UNICA FUENTE PERMITIDA):\n{contexto}\n\n"
        f"RECUERDA: Si no esta en la INFORMACION OFICIAL de arriba, responde: \"{sin_info}\"\n"
    )
