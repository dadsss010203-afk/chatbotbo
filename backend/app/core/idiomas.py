"""
core/idiomas.py
Textos en 2 idiomas (ES/EN) + detección automática con langdetect.
Compartido por todos los chatbots.
Los datos de contacto (telefono, web) se leen de contacto_institucional.json
a través de core.contacto — no hardcodear aquí.
"""

from langdetect import detect, LangDetectException
from core import contacto

# ─────────────────────────────────────────────
#  MAPA langdetect → código interno
# ─────────────────────────────────────────────
LANG_MAP = {
    "es"   : "es",
    "en"   : "en",
    # Cualquier otro idioma detectado → español por defecto
}

IDIOMA_DEFAULT = "es"

# ─────────────────────────────────────────────
#  TEXTOS POR IDIOMA
# ─────────────────────────────────────────────
def _build_idiomas() -> dict:
    tel = contacto.telefono()
    web = contacto.web()
    return {
        "es": {
            "nombre"       : "Español",
            "bienvenida"   : (
                "¡Hola! Bienvenido al asistente oficial de Correos de Bolivia. "
                "Puedo ayudarte con envíos, sucursales, ubicaciones y más.\n\n"
                "• Presiona el botón TARIFAS para activar las consultas de tarifas de envío. "
                "Presiónalo de nuevo para desactivarlo.\n"
                "• Presiona el botón RASTREO para rastrear un paquete. "
                "Presiónalo de nuevo para desactivarlo.\n\n"
                "¿En qué puedo ayudarte hoy?"
            ),
            "saludo"       : (
                "¡Hola! Soy ChatbotBO, el asistente de Correos Bolivia. "
                "Puedo ayudarte con envíos, sucursales y más. ¿En qué puedo ayudarte?"
            ),
            "despedida"    : (
                f"Ha sido un placer ayudarte. Que tengas un excelente día. "
                f"Recuerda que puedes visitarnos en {web}. ¡Hasta pronto!"
            ),
            "sin_info"     : f"No tengo esa información. Visita {web} o llama al {tel}.",
            "instruccion"  : "Responde en español, de forma clara y amable.",
            "pedir_ciudad" : "Por favor indica una ciudad válida: {ciudades}",
            "no_disponible": "No disponible",
        },
        "en": {
            "nombre"       : "English",
            "bienvenida"   : (
                "Hello! Welcome to the official assistant of the Bolivian Postal. "
                "I can help you with shipments, branches, locations and more. How can I help you today?"
            ),
            "saludo"       : "Hello! I am the Correos Bolivia assistant. How can I help you?",
            "despedida"    : (
                f"It was a pleasure helping you. Have a great day. "
                f"Remember you can visit us at {web}. Goodbye!"
            ),
            "sin_info"     : f"I don't have that information. Visit {web} or call {tel}.",
            "instruccion"  : "Respond in English, clearly and politely.",
            "pedir_ciudad" : "Please specify a city among: {ciudades}",
            "no_disponible": "Not available",
        },
    }

IDIOMAS = _build_idiomas()


# ─────────────────────────────────────────────
#  DETECCIÓN AUTOMÁTICA
# ─────────────────────────────────────────────

def detectar_idioma(texto: str) -> str:
    texto_limpio = texto.strip()
    if len(texto_limpio) < 2:
        return IDIOMA_DEFAULT
    try:
        codigo = detect(texto_limpio)
        lang = LANG_MAP.get(codigo, IDIOMA_DEFAULT)
    except LangDetectException:
        return IDIOMA_DEFAULT
    return lang


def resolver_idioma(lang_forzado, texto: str) -> str:
    """
    Prioridad:
    1. lang enviado por el frontend (selector manual)
    2. Detección automática del texto
    """
    if lang_forzado and lang_forzado in IDIOMAS:
        return lang_forzado
    return detectar_idioma(texto)
