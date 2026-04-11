"""
chatbots/general/config.py
Configuración específica del chatbot general.
Aquí cambias el system prompt, los archivos de data y los parámetros.
"""

import os

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
DATA_FILE       = os.environ.get("DATA_FILE",       "data/correos_bolivia.txt")
SUCURSALES_FILE = os.environ.get("SUCURSALES_FILE", "data/sucursales_contacto.json")
SECCIONES_FILE  = os.environ.get("SECCIONES_FILE",  "data/secciones_home.json")
HISTORIA_FILE   = os.environ.get("HISTORIA_FILE",   "data/historia_institucional.json")
CHROMA_PATH     = os.environ.get("CHROMA_PATH",     "chroma_db")

# ─────────────────────────────────────────────
#  SYSTEM PROMPT BASE
# ─────────────────────────────────────────────
SYSTEM_PROMPT = (
    "Eres ChatbotBO, el asistente virtual oficial de la Agencia Boliviana de Correos (AGBC). "
    "Estás especializado en servicios postales de Bolivia: envíos, sucursales, rastreo y trámites. "
    "Siempre eres amable, claro, conciso y profesional. "
    "Responde siempre en el mismo idioma en que el usuario te escribe. "
    "Responde en un máximo de 3 párrafos cortos, sin asteriscos ni markdown. "
    "No inventes información. Si no tienes la respuesta exacta, responde con la frase de no información indicada. "
    "Web: correos.gob.bo | Teléfono: +591 22152423 | "
    "Horario: Lunes a viernes 8:30 a 18:30 | Sábados 9:00 a 13:00"
)


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
    evidencia_regla = ""
    if REQUIRE_EVIDENCE:
        evidencia_regla = (
            "- Al final agrega una línea que empiece con: EVIDENCIA: y luego 1 o 2 citas textuales cortas "
            "(máx. 12 palabras cada una) tomadas literalmente de INFORMACIÓN OFICIAL, entre comillas dobles.\n"
            "- Si NO puedes extraer al menos 1 cita literal, responde exactamente: "
            f"\"{sin_info}\" (sin agregar nada más).\n"
        )

    return (
        f"NORMAS IMPORTANTES: {instruccion_idioma}. Responde únicamente en ese idioma.\n\n"
        f"{SYSTEM_PROMPT}\n\n"
        f"FECHA Y HORA EN BOLIVIA:\n"
        f"  Fecha: {hora['fecha']}  Hora: {hora['hora']}  Día: {hora['dia']}\n"
        f"  Estado: {hora['estado']}  Horario: {hora['horario']}\n\n"
        f"SKILL PRINCIPAL PARA ESTA CONSULTA:\n{skill_name or 'Consulta general de Correos de Bolivia'}\n\n"
        f"DESCRIPCIÓN DE LA SKILL PRINCIPAL:\n{skill_description or 'Sin descripción específica.'}\n\n"
        f"DISPARADORES DE LA SKILL PRINCIPAL:\n{skill_triggers or 'Sin disparadores declarados.'}\n\n"
        f"INFORMACIÓN OFICIAL:\n{contexto}\n\n"
        f"INSTRUCCIONES:\n"
        f"- Responde solo con los datos oficiales presentes en INFORMACIÓN OFICIAL.\n"
        f"- Si no tienes la respuesta exacta, responde exactamente: \"{sin_info}\".\n"
        f"- Mantén la respuesta breve, clara y profesional.\n"
        f"- Prioriza siempre la información específica frente a cualquier contenido general.\n"
        f"- No inventes información, no añadas URLs, no cites fuentes que no estén en el contexto.\n"
        f"- No repitas el prompt ni digas que eres un modelo de IA.\n"
        f"- Si el usuario pregunta por horarios o aperturas, usa el Estado de arriba.\n"
        f"- Responde en el idioma solicitado: {instruccion_idioma}.\n"
        f"{evidencia_regla}"
    )
