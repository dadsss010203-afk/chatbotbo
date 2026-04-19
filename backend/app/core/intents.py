"""
core/intents.py
Detección de intenciones: saludo, despedida, consulta de ubicación.
Compartido por todos los chatbots.
"""

import re

# ─────────────────────────────────────────────
#  PATRONES
# ─────────────────────────────────────────────
PATRON_SALUDO = re.compile(
    r"^(hola\b|holi\b|holis\b|buenas?\b|buenas?\s+(dias?|tardes?|noches?)"
    r"|hey\b|hi\b|hello\b|saludos|que\s+tal|como\s+estas|buen\s+dia"
    r"|привет|здравствуй|добрый\s+(день|вечер|утро)"
    r"|你好|您好|嗨"
    r"|ol[aá]\b|bom\s+dia|boa\s+(tarde|noite)"
    r"|bonjour|bonsoir|salut)",
    re.IGNORECASE,
)

PALABRAS_DESPEDIDA = [
    "adios", "adiós", "chau", "chao", "hasta luego", "hasta pronto",
    "nos vemos", "gracias ya", "eso era todo", "eso es todo",
    "me voy", "hasta mañana", "ciao",
    "bye", "goodbye", "see you", "farewell", "take care",
    "tchau", "até logo", "até mais", "obrigado já",
    "пока", "до свидания", "всего хорошего", "до встречи",
    "再见", "拜拜", "谢谢了",
    "au revoir", "à bientôt", "adieu",
]

PALABRAS_UBICACION = [
    "ubicacion", "ubicación", "donde", "dónde", "direccion", "dirección",
    "sucursal", "oficina", "mapa", "maps", "coordenadas",
    "como llego", "como llegar", "donde queda", "donde se encuentra",
    "location", "address", "branch", "where is", "how to get",
    "localização", "endereço", "agência", "onde fica",
    "адрес", "где находится", "местоположение", "отделение",
    "地址", "位置", "在哪", "分支机构",
    "adresse", "succursale", "où se trouve",
]

ALIAS_CIUDADES = {
    "lpb"                    : "la paz",
    "cba"                    : "cochabamba",
    "cbba"                   : "cochabamba",
    "scz"                    : "santa cruz",
    "santa cruz de la sierra": "santa cruz",
    "trinidad"               : "beni",
    "cobija"                 : "pando",
    "potosí"                 : "potosi",
}


# ─────────────────────────────────────────────
#  FUNCIONES
# ─────────────────────────────────────────────

def es_saludo(texto: str) -> bool:
    return bool(PATRON_SALUDO.match(texto.strip()))


def es_despedida(texto: str) -> bool:
    return any(p in texto.lower().strip() for p in PALABRAS_DESPEDIDA)


def detectar_solo_ciudad(texto: str, sucursales: list) -> dict | None:
    """
    Detecta si el usuario escribió solo el nombre de una ciudad.
    Ejemplo: "la paz", "cbba", "scz"
    """
    texto_norm = ALIAS_CIUDADES.get(texto.lower().strip(), texto.lower().strip())
    for s in sucursales:
        nombre_lower    = s.get("nombre", "").lower()
        ciudad_sucursal = re.sub(
            r"^(regional|oficina\s+central)\s*:\s*", "", nombre_lower
        ).strip()
        if ciudad_sucursal and (
            texto_norm == ciudad_sucursal or texto_norm in ciudad_sucursal
        ):
            return s
    return None


def es_presentacion(texto: str) -> bool:
    """Detecta cuando el usuario pide que el bot se presente.

    Queremos capturar frases como "preséntate", "quién eres" o
    "háblame de ti" o "háblame sobre ti". No debe activarse en consultas
    genéricas como "háblame de correos" ya que allí el usuario espera
    información sobre el servicio, no una presentación del asistente.

    Usada para devolver un saludo fijo sin necesidad de buscar en los datos.
    """
    texto_lower = texto.lower()
    # coincidencias obvias
    if re.search(r'\bpresenta(te)?\b', texto_lower):
        return True
    if re.search(r'\bqu[ií]en eres\b', texto_lower):
        return True

    # "háblame" sólo nos interesa si va seguido de indicios de que se refiere
    # al propio bot (de ti, sobre ti, de ti mismo, de tu nombre, etc.)
    m = re.search(r'h[aá]blame\s+(de|sobre)\s+(.+)', texto_lower)
    if m:
        sufijo = m.group(2)
        # si el sufijo menciona "ti" o "tú" o "quién eres" etc.
        if re.search(r'\b(ti|t[úu]|tu nombre|qu[ií]en eres?)\b', sufijo):
            return True
    return False


def es_pedido_corto(texto: str) -> bool:
    """True si la consulta es un pedido escueto que probablemente se refiere a un tema anterior.

    Se usa para detectar respuestas como "dame", "da", "aver dame" o mensajes muy cortos
    que por sí solos no contienen suficiente información. En esos casos el servidor usará el
    último mensaje del usuario para completar el contexto antes de enviar la pregunta al LLM.
    """
    t = texto.strip().lower()
    if len(t) <= 3:
        return True
    if re.match(r'^(dame|da|dale|dalo|d[aá]me|av[eé]r|aver|por favor|please)$', t):
        return True
    return False


def detectar_consulta_ubicacion(texto: str, sucursales: list) -> dict | None:
    """
    Detecta si el usuario pregunta por la ubicación de una sucursal.

    Returns:
        - dict de la sucursal si encontró la ciudad
        - {"ciudad": None} si pregunta ubicación pero no especifica ciudad
        - None si no es consulta de ubicación
    """
    texto_lower = texto.lower()
    for alias, ciudad_real in ALIAS_CIUDADES.items():
        if alias in texto_lower:
            texto_lower = texto_lower.replace(alias, ciudad_real)

    if not any(p in texto_lower for p in PALABRAS_UBICACION):
        return None

    for s in sucursales:
        nombre_lower    = s.get("nombre", "").lower()
        ciudad_sucursal = re.sub(
            r"^(regional|oficina\s+central)\s*:\s*", "", nombre_lower
        ).strip()
        if ciudad_sucursal and ciudad_sucursal in texto_lower:
            return s

    return {"ciudad": None}
