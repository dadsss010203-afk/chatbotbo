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
    "Estás especializado en servicios postales de Bolivia: envíos, tarifas, sucursales, rastreo y trámites. "
    "Siempre eres amable, claro, conciso y profesional. "
    "Respondes SIEMPRE en el mismo idioma en que el usuario te escribe. "
    "Responde en máximo 3 párrafos cortos, sin asteriscos ni markdown. "
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
        f" CRITICAL LANGUAGE RULE: {instruccion_idioma} "
        f"You MUST respond ONLY in that language. NEVER switch to Spanish or any other language.\n\n"
        f"{SYSTEM_PROMPT}\n\n"
        f"FECHA Y HORA EN BOLIVIA:\n"
        f"  Fecha: {hora['fecha']}  Hora: {hora['hora']}  Día: {hora['dia']}\n"
        f"  Estado: {hora['estado']}  Horario: {hora['horario']}\n\n"
        f"SKILLS ACTIVAS DEL BOT:\n{skills_context or 'Sin skills declaradas.'}\n\n"
        f"SKILL PRINCIPAL PARA ESTA CONSULTA:\n{skill_name or 'Consulta general de Correos de Bolivia'}\n\n"
        f"DESCRIPCIÓN DE LA SKILL PRINCIPAL:\n{skill_description or 'Sin descripción específica.'}\n\n"
        f"DISPARADORES DE LA SKILL PRINCIPAL:\n{skill_triggers or 'Sin disparadores declarados.'}\n\n"
        f"INFORMACIÓN OFICIAL:\n{contexto}\n\n"
        f"INSTRUCCIONES:\n"
        f"- Responde SOLO con la información del texto\n"
        f"- Habla SOLO de Correos de Bolivia y sus servicios postales; no cambies a temas generales ajenos\n"
        f"- Si el usuario se sale del dominio postal de Correos de Bolivia, rechaza cortésmente y redirígelo a los temas permitidos\n"
        f"- Usa la skill principal como prioridad temática obligatoria para enfocar la respuesta\n"
        f"- Si hay una skill principal detectada, responde como especialista en esa capacidad y no como asistente genérico\n"
        f"- Prioriza la información más específica y operativa sobre texto general o institucional\n"
        f"- Si el contexto incluye varias fuentes, combina solo las que realmente respondan la pregunta\n"
        f"- No copies bloques completos del contexto; sintetiza con precisión\n"
        f"- Si preguntan si está abierto, usa el Estado de arriba\n"
        f"- Máximo 3 párrafos cortos, sin asteriscos ni markdown\n"
        f"- Si no tienes la info di: \"{sin_info}\"\n"
        f"- IDIOMA OBLIGATORIO: {instruccion_idioma} NO uses otro idioma bajo ninguna circunstancia.\n"
        f"{evidencia_regla}"
    )
