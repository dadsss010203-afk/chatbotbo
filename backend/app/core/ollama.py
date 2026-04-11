"""
core/ollama.py
Cliente del modelo Ollama: llamadas, limpieza y verificación.
Compartido por todos los chatbots.
"""

import os
import re
import time
import requests

# ─────────────────────────────────────────────
#  CONFIGURACIÓN
# ─────────────────────────────────────────────
LLM_MODEL             = os.environ.get("LLM_MODEL",         "correos-bot")
OLLAMA_URL            = os.environ.get("OLLAMA_URL",         "http://127.0.0.1:11434/api/chat")
OLLAMA_TIMEOUT        = int(os.environ.get("OLLAMA_TIMEOUT", "800"))
OLLAMA_RETRIES        = int(os.environ.get("OLLAMA_RETRIES", "2"))
OLLAMA_RETRY_BACKOFF  = float(os.environ.get("OLLAMA_RETRY_BACKOFF", "0.5"))
OLLAMA_MAX_TOKENS     = os.environ.get("OLLAMA_MAX_TOKENS")
OLLAMA_PROMPT_MAX_TOKENS = int(os.environ.get("OLLAMA_PROMPT_MAX_TOKENS", "3600"))

_SESSION = requests.Session()

def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except Exception:
        return default


def _default_options() -> dict:
    """
    Opciones por defecto (configurables por variables de entorno).

    Nota: `num_ctx` alto ayuda a no truncar instrucciones + contexto RAG,
    lo cual reduce alucinaciones.
    """
    seed = os.environ.get("OLLAMA_SEED")
    options = {
        "num_predict": _env_int("OLLAMA_NUM_PREDICT", 200),
        "temperature": _env_float("OLLAMA_TEMPERATURE", 0.0),
        "num_ctx": _env_int("OLLAMA_NUM_CTX", 4096),
        "repeat_penalty": _env_float("OLLAMA_REPEAT_PENALTY", 1.1),
        "top_p": _env_float("OLLAMA_TOP_P", 0.7),
        "top_k": _env_int("OLLAMA_TOP_K", 40),
    }
    if seed is not None and seed != "":
        try:
            options["seed"] = int(seed)
        except Exception:
            pass
    if OLLAMA_MAX_TOKENS is not None and OLLAMA_MAX_TOKENS != "":
        options["max_tokens"] = _env_int("OLLAMA_MAX_TOKENS", 0)
    return options


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
                   num_predict=200, temperature=0, num_ctx=4096

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
        "options" : {**_default_options(), **(opciones or {})},
    }

    last_exception = None
    for attempt in range(1, OLLAMA_RETRIES + 2):
        try:
            resp = _SESSION.post(OLLAMA_URL, json=payload, timeout=OLLAMA_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            return data["message"]["content"]
        except requests.exceptions.RequestException as exc:
            last_exception = exc
            if attempt > OLLAMA_RETRIES:
                raise
            time.sleep(OLLAMA_RETRY_BACKOFF * attempt)
    raise last_exception


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
