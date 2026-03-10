"""
core/idiomas.py
Textos en 6 idiomas (ES/EN/FR/PT/ZH/RU) + detección automática con langdetect.
Compartido por todos los chatbots.
"""

from langdetect import detect, LangDetectException

# ─────────────────────────────────────────────
#  MAPA langdetect → código interno
# ─────────────────────────────────────────────
LANG_MAP = {
    "es"   : "es",
    "en"   : "en",
    "pt"   : "pt",
    "fr"   : "fr",
    "zh-cn": "zh",
    "zh-tw": "zh",
    "ko"   : "zh",   # langdetect confunde chino/coreano en textos cortos
    "ru"   : "ru",
}

IDIOMA_DEFAULT = "es"

# ─────────────────────────────────────────────
#  TEXTOS POR IDIOMA
# ─────────────────────────────────────────────
IDIOMAS = {
    "es": {
        "nombre"       : "Español",
        "bienvenida"   : (
            "¡Hola! Bienvenido al asistente oficial de la Agencia Boliviana de Correos (AGBC). "
            "Puedo ayudarte con envíos, tarifas, sucursales, ubicaciones y más. ¿En qué puedo ayudarte hoy?"
        ),
        "saludo"       : (
            "¡Hola! Soy ChatbotBO, el asistente de Correos Bolivia. "
            "Puedo ayudarte con envíos, tarifas, sucursales y más. ¿En qué puedo ayudarte?"
        ),
        "despedida"    : (
            "Ha sido un placer ayudarte. Que tengas un excelente día. "
            "Recuerda que puedes visitarnos en correos.gob.bo. ¡Hasta pronto!"
        ),
        "sin_info"     : "No tengo esa información. Visita correos.gob.bo o llama al +591 22152423.",
        "instruccion"  : "Responde en español, de forma clara y amable.",
        "pedir_ciudad" : "Por favor indica una ciudad válida: {ciudades}",
        "no_disponible": "No disponible",
    },
    "en": {
        "nombre"       : "English",
        "bienvenida"   : (
            "Hello! Welcome to the official assistant of the Bolivian Postal Agency (AGBC). "
            "I can help you with shipments, rates, branches, locations and more. How can I help you today?"
        ),
        "saludo"       : "Hello! I am the Correos Bolivia assistant. How can I help you?",
        "despedida"    : (
            "It was a pleasure helping you. Have a great day. "
            "Remember you can visit us at correos.gob.bo. Goodbye!"
        ),
        "sin_info"     : "I don't have that information. Visit correos.gob.bo or call +591 22152423.",
        "instruccion"  : "Respond in English, clearly and politely.",
        "pedir_ciudad" : "Please specify a city among: {ciudades}",
        "no_disponible": "Not available",
    },
    "fr": {
        "nombre"       : "Français",
        "bienvenida"   : (
            "Bonjour! Bienvenue chez l'assistant officiel de l'Agence Bolivienne des Postes (AGBC). "
            "Je peux vous aider avec les envois, les tarifs, les succursales et plus encore. "
            "Comment puis-je vous aider?"
        ),
        "saludo"       : "Bonjour! Je suis l'assistant de Correos Bolivia. Comment puis-je vous aider?",
        "despedida"    : (
            "Ce fut un plaisir de vous aider. Bonne journée. "
            "N'oubliez pas de visiter correos.gob.bo. Au revoir!"
        ),
        "sin_info"     : "Je n'ai pas cette information. Visitez correos.gob.bo ou appelez le +591 22152423.",
        "instruccion"  : "Répondez en français, clairement et poliment.",
        "pedir_ciudad" : "Veuillez indiquer une ville parmi : {ciudades}",
        "no_disponible": "Non disponible",
    },
    "pt": {
        "nombre"       : "Português",
        "bienvenida"   : (
            "Olá! Bem-vindo ao assistente oficial da Agência Boliviana de Correios (AGBC). "
            "Posso ajudá-lo com envios, tarifas, agências, localizações e mais. Como posso ajudá-lo hoje?"
        ),
        "saludo"       : "Olá! Sou o assistente de Correos Bolivia. Como posso ajudá-lo?",
        "despedida"    : (
            "Foi um prazer ajudá-lo. Tenha um ótimo dia. "
            "Lembre-se de visitar correos.gob.bo. Até logo!"
        ),
        "sin_info"     : "Não tenho essa informação. Visite correos.gob.bo ou ligue para +591 22152423.",
        "instruccion"  : "Responda em português, de forma clara e amigável.",
        "pedir_ciudad" : "Por favor, especifique uma cidade entre: {ciudades}",
        "no_disponible": "Não disponível",
    },
    "zh": {
        "nombre"       : "中文",
        "bienvenida"   : (
            "您好！欢迎使用玻利维亚邮政局（AGBC）官方助手。"
            "我可以帮助您了解邮寄、费率、分支机构、位置等信息。请问有什么可以帮助您？"
        ),
        "saludo"       : "您好！我是玻利维亚邮政助手。有什么可以帮助您？",
        "despedida"    : (
            "很高兴为您服务。祝您有美好的一天。"
            "请记得访问 correos.gob.bo。再见！"
        ),
        "sin_info"     : "我没有该信息。请访问 correos.gob.bo 或致电 +591 22152423。",
        "instruccion"  : "请用中文回答，清晰友好。",
        "pedir_ciudad" : "请在以下城市中指定一个：{ciudades}",
         "no_disponible": "不可用",
    },
    "ru": {
        "nombre"       : "Русский",
        "bienvenida"   : (
            "Здравствуйте! Добро пожаловать в официальный помощник "
            "Боливийского почтового агентства (AGBC). "
            "Я могу помочь вам с отправлениями, тарифами, отделениями и местоположениями. "
            "Чем могу помочь?"
        ),
        "saludo"       : "Здравствуйте! Я помощник Correos Bolivia. Чем могу помочь?",
        "despedida"    : (
            "Был рад помочь. Хорошего дня! "
            "Не забудьте посетить наш сайт correos.gob.bo. До свидания!"
        ),
        "sin_info"     : "У меня нет этой информации. Посетите correos.gob.bo или позвоните +591 22152423.",
        "instruccion"  : "Отвечай на русском языке, чётко и вежливо.",
        "pedir_ciudad" : "Пожалуйста, укажите город из списка: {ciudades}",
         "no_disponible": "Недоступно",
    },
}


# ─────────────────────────────────────────────
#  DETECCIÓN AUTOMÁTICA
# ─────────────────────────────────────────────

def detectar_idioma(texto: str) -> str:
    texto_limpio = texto.strip()
    if len(texto_limpio) < 4:
        return IDIOMA_DEFAULT
    try:
        codigo = detect(texto_limpio)
        return LANG_MAP.get(codigo, IDIOMA_DEFAULT)
    except LangDetectException:
        return IDIOMA_DEFAULT


def resolver_idioma(lang_forzado, texto: str) -> str:
    """
    Prioridad:
    1. lang enviado por el frontend (selector manual)
    2. Detección automática del texto
    """
    if lang_forzado and lang_forzado in IDIOMAS:
        return lang_forzado
    return detectar_idioma(texto)
