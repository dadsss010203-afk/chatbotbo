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
#  ARCHIVOS DE DATA (generados por el scraper)
# ─────────────────────────────────────────────
DATA_FILE       = os.environ.get("DATA_FILE",       "data/correos_bolivia.txt")
SUCURSALES_FILE = os.environ.get("SUCURSALES_FILE", "data/sucursales_contacto.json")
SECCIONES_FILE  = os.environ.get("SECCIONES_FILE",  "data/secciones_home.json")
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


def construir_prompt(instruccion_idioma: str, contexto: str, hora: dict, sin_info: str) -> str:
    """Construye el system prompt completo para inyectar en Ollama."""
    return (
        f" CRITICAL LANGUAGE RULE: {instruccion_idioma} "
        f"You MUST respond ONLY in that language. NEVER switch to Spanish or any other language.\n\n"
        f"{SYSTEM_PROMPT}\n\n"
        f"FECHA Y HORA EN BOLIVIA:\n"
        f"  Fecha: {hora['fecha']}  Hora: {hora['hora']}  Día: {hora['dia']}\n"
        f"  Estado: {hora['estado']}  Horario: {hora['horario']}\n\n"
        f"INFORMACIÓN OFICIAL:\n{contexto}\n\n"
        f"INSTRUCCIONES:\n"
        f"- Responde SOLO con la información del texto\n"
        f"- Si preguntan si está abierto, usa el Estado de arriba\n"
        f"- Máximo 3 párrafos cortos, sin asteriscos ni markdown\n"
        f"- Si no tienes la info di: \"{sin_info}\"\n"
        f"- IDIOMA OBLIGATORIO: {instruccion_idioma} NO uses otro idioma bajo ninguna circunstancia.\n"
    )
