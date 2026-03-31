"""
core/ollama.py
Cliente del modelo Ollama: llamadas, limpieza y verificación.
Compartido por todos los chatbots.
"""

import os
import re
import requests

# ─────────────────────────────────────────────
#  CONFIGURACIÓN
# ─────────────────────────────────────────────
LLM_MODEL      = os.environ.get("LLM_MODEL",         "correos-bot")
OLLAMA_URL     = os.environ.get("OLLAMA_URL",         "http://127.0.0.1:11434/api/chat")
OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "800"))


# ─────────────────────────────────────────────
#  LLAMADA AL MODELO
# ─────────────────────────────────────────────

def llamar_ollama(
    mensajes : list,
    modelo   : str  = None,
    opciones : dict = None,
) -> str:
    """
    Envía mensajes a Ollama y devuelve la respuesta como string.

    Args:
        mensajes : lista de {"role": "system/user/assistant", "content": "..."}
        modelo   : nombre del modelo (por defecto LLM_MODEL del .env)
        opciones : parámetros del modelo. Por defecto:
                   num_predict=200, temperature=0, num_ctx=1500

    Returns:
        Texto de la respuesta del modelo.

    Raises:
        requests.exceptions.Timeout    : si el modelo tarda más de OLLAMA_TIMEOUT
        requests.exceptions.HTTPError  : si Ollama devuelve un error HTTP
    """
    payload = {
        "model"   : modelo or LLM_MODEL,
        "messages": mensajes,
        "stream"  : False,
        "options" : opciones or {
            "num_predict"   : 200,
            "temperature"   : 0,
            "num_ctx"       : 1500,
            "repeat_penalty": 1.1,
            "top_p"         : 0.9,
        },
    }

    resp = requests.post(OLLAMA_URL, json=payload, timeout=OLLAMA_TIMEOUT)
    resp.raise_for_status()
    return resp.json()["message"]["content"]


# ─────────────────────────────────────────────
#  LIMPIEZA DE RESPUESTA
# ─────────────────────────────────────────────

def limpiar_respuesta(texto: str) -> str:
    """
    Limpia la respuesta del modelo eliminando:
    - Bloques <think>...</think> (modelos de razonamiento)
    - Formato markdown (**bold**, * listas)
    - Convierte * items → bullet •
    """
    # Eliminar bloques de razonamiento interno
    texto = re.sub(r"<think>.*?</think>", "", texto, flags=re.DOTALL)
    # Eliminar markdown
    texto = texto.replace("**", "")
    texto = texto.replace("* ",  "• ")
    texto = texto.replace("*",   "")
    return texto.strip()


# ─────────────────────────────────────────────
#  VERIFICACIÓN
# ─────────────────────────────────────────────

def ollama_disponible() -> bool:
    """
    Verifica si Ollama está corriendo.
    Devuelve True si está disponible, False si no.
    """
    base_url = OLLAMA_URL.replace("/api/chat", "")
    try:
        requests.get(base_url, timeout=3)
        return True
    except Exception:
        return False


def verificar_ollama() -> bool:
    """
    Verifica Ollama al arrancar e imprime el resultado.
    Devuelve True si está disponible.
    """
    ok = ollama_disponible()
    if ok:
        print(f"  Ollama conectado → modelo: {LLM_MODEL}")
    else:
        print(f"   Ollama no responde en {OLLAMA_URL}")
        print("   Ejecuta: ollama serve")
    return ok
