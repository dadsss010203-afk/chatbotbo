"""
core/idiomas.py
Textos en 2 idiomas (ES/EN) + deteccion automatica ligera.
Compartido por todos los chatbots.
Los datos de contacto (telefono, web) se leen de contacto_institucional.json
a traves de core.contacto — no hardcodear aqui.
"""

from core import contacto

IDIOMA_DEFAULT = "es"

# ─────────────────────────────────────────────
#  TEXTOS POR IDIOMA
# ─────────────────────────────────────────────
def _build_idiomas() -> dict:
    tel = contacto.telefono()
    web = contacto.web()
    return {
        "es": {
            "nombre"       : "Espanol",
            "bienvenida"   : (
                "Hola! Bienvenido al asistente oficial de Correos de Bolivia. "
                "Puedo ayudarte con envios, sucursales, ubicaciones y mas.\n\n"
                "  Presiona el boton TARIFAS para activar las consultas de tarifas de envio. "
                "Presionalo de nuevo para desactivarlo.\n"
                "  Presiona el boton RASTREO para rastrear un paquete. "
                "Presionalo de nuevo para desactivarlo.\n\n"
                "En que puedo ayudarte hoy?"
            ),
            "saludo"       : (
                "Hola! Soy ChatbotBO, el asistente de Correos Bolivia. "
                "Puedo ayudarte con envios, sucursales y mas. En que puedo ayudarte?"
            ),
            "despedida"    : (
                f"Ha sido un placer ayudarte. Que tengas un excelente dia. "
                f"Recuerda que puedes visitarnos en {web}. Hasta pronto!"
            ),
            "sin_info"     : f"No tengo esa informacion. Visita {web} o llama al {tel}.",
            "instruccion"  : "Responde en espanol, de forma clara y amable.",
            "pedir_ciudad" : "Por favor indica una ciudad valida: {ciudades}",
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
#  DETECCION AUTOMATICA (ligera, sin langdetect)
# ─────────────────────────────────────────────

# Palabras de alta frecuencia exclusivas de cada idioma
_EN_MARKERS = frozenset({
    "the", "is", "are", "was", "were", "have", "has", "had",
    "what", "when", "where", "who", "how", "why", "which",
    "can", "will", "would", "should", "could", "do", "does",
    "tracking", "ship", "package", "mail", "help", "please",
    "office", "branch", "rate", "price", "hello", "thanks",
    "your", "you", "this", "that", "with", "from", "about",
    "need", "send", "delivery", "code", "number", "status",
})
_ES_MARKERS = frozenset({
    "que", "los", "las", "del", "por", "para", "como", "una",
    "con", "mas", "pero", "muy", "este", "esta", "entre",
    "envio", "rastreo", "paquete", "sucursal", "tarifa",
    "tienes", "puedo", "ayuda", "gracias", "hola", "buenas",
    "necesito", "saber", "donde", "cuanto", "cuando", "cual",
    "correos", "bolivia", "envios", "servicio", "horario",
    "codigo", "numero", "estado", "telefono", "direccion",
})


def detectar_idioma(texto: str) -> str:
    """Detecta ES o EN usando conteo de palabras marcadoras frecuentes."""
    texto_limpio = texto.strip().lower()
    if len(texto_limpio) < 3:
        return IDIOMA_DEFAULT

    # Normalizar: solo letras y espacios
    import re
    palabras = set(re.findall(r"[a-z]+", texto_limpio))

    en_hits = len(palabras & _EN_MARKERS)
    es_hits = len(palabras & _ES_MARKERS)

    # Umbral: se necesita al menos 2 hits mas que el otro idioma
    if en_hits > es_hits + 1:
        return "en"
    if es_hits > en_hits + 1:
        return "es"

    # Empate o pocos hits: default espanol (idioma principal de Correos Bolivia)
    return IDIOMA_DEFAULT


def resolver_idioma(lang_forzado: str | None, texto: str) -> str:
    """
    Prioridad:
    1. lang enviado por el frontend (selector manual)
    2. Deteccion automatica del texto
    """
    if lang_forzado and lang_forzado in IDIOMAS:
        return lang_forzado
    return detectar_idioma(texto)
