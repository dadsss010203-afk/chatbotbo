"""
core/ollama.py
Cliente del modelo Ollama: llamadas, limpieza y verificacion.
Compartido por todos los chatbots.
"""

import os
import re
import time
import json
import threading
import requests
import logging

logger = logging.getLogger("chatbotbo.ollama")

# ─────────────────────────────────────────────
#  CONFIGURACION
# ─────────────────────────────────────────────
# LOCAL
LLM_MODEL             = os.environ.get("LLM_MODEL",        "correos-bot")
OLLAMA_URL            = os.environ.get("OLLAMA_URL",        "http://127.0.0.1:11434/api/chat")

OLLAMA_TIMEOUT           = int(os.environ.get("OLLAMA_TIMEOUT",        "800"))
OLLAMA_RETRIES           = int(os.environ.get("OLLAMA_RETRIES",        "2"))
OLLAMA_RETRY_BACKOFF     = float(os.environ.get("OLLAMA_RETRY_BACKOFF","0.5"))
OLLAMA_MAX_TOKENS        = os.environ.get("OLLAMA_MAX_TOKENS")
OLLAMA_PROMPT_MAX_TOKENS = int(os.environ.get("OLLAMA_PROMPT_MAX_TOKENS", "1800"))
# Timeout maximo para respuesta del LLM (segundos). Si se supera, se devuelve fallback.
LLM_RESPONSE_TIMEOUT     = int(os.environ.get("LLM_RESPONSE_TIMEOUT",  "50"))

_SESSION = requests.Session()
_ACTIVE_LOCK = threading.Lock()
_ACTIVE_REQUESTS: dict[str, dict] = {}


class OllamaCancelled(Exception):
    """La generacion fue cancelada explicitamente por el usuario."""


# ─────────────────────────────────────────────
#  GESTION DE REQUESTS ACTIVOS
# ─────────────────────────────────────────────

def _register_active_request(request_id: str, cancel_event: threading.Event) -> None:
    with _ACTIVE_LOCK:
        _ACTIVE_REQUESTS[request_id] = {
            "cancel_event": cancel_event,
            "response": None,
            "session": None,
        }


def _set_active_response(request_id: str, response) -> None:
    with _ACTIVE_LOCK:
        if request_id in _ACTIVE_REQUESTS:
            _ACTIVE_REQUESTS[request_id]["response"] = response


def _set_active_session(request_id: str, session) -> None:
    with _ACTIVE_LOCK:
        if request_id in _ACTIVE_REQUESTS:
            _ACTIVE_REQUESTS[request_id]["session"] = session


def _unregister_active_request(request_id: str) -> None:
    with _ACTIVE_LOCK:
        _ACTIVE_REQUESTS.pop(request_id, None)


def cancel_request(request_id: str) -> bool:
    with _ACTIVE_LOCK:
        state = _ACTIVE_REQUESTS.get(request_id)
        if not state:
            return False
        state["cancel_event"].set()
        response = state.get("response")
        session  = state.get("session")
    try:
        if response is not None:
            try:
                raw = getattr(response, "raw", None)
                if raw is not None:
                    raw.close()
            except Exception:
                pass
            response.close()
    except Exception:
        pass
    try:
        if session is not None:
            session.close()
    except Exception:
        pass
    return True


# ─────────────────────────────────────────────
#  HELPERS DE ENTORNO
# ─────────────────────────────────────────────

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
    num_ctx alto ayuda a no truncar instrucciones + contexto RAG,
    lo cual reduce alucinaciones.
    """
    seed = os.environ.get("OLLAMA_SEED")
    options = {
        "num_predict":   _env_int("OLLAMA_NUM_PREDICT",   600),
        "temperature":   _env_float("OLLAMA_TEMPERATURE", 0.2),
        "num_ctx":       _env_int("OLLAMA_NUM_CTX",       2048),
        "repeat_penalty":_env_float("OLLAMA_REPEAT_PENALTY", 1.1),
        "top_p":         _env_float("OLLAMA_TOP_P",       0.9),
        "top_k":         _env_int("OLLAMA_TOP_K",         40),
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
#  LLAMADA AL MODELO (no-streaming)
# ─────────────────────────────────────────────

def llamar_ollama(
    mensajes:   list,
    modelo:     str  = None,
    opciones:   dict = None,
    request_id: str | None = None,
) -> str:
    """
    Envia mensajes a Ollama y devuelve la respuesta como string.

    Args:
        mensajes   : lista de {"role": "system/user/assistant", "content": "..."}
        modelo     : nombre del modelo (por defecto LLM_MODEL del .env)
        opciones   : parametros del modelo
        request_id : si se pasa, permite cancelar con cancel_request()

    Returns:
        Texto de la respuesta del modelo.

    Raises:
        requests.exceptions.Timeout   : si el modelo tarda mas de OLLAMA_TIMEOUT
        requests.exceptions.HTTPError : si Ollama devuelve un error HTTP
    """
    payload = {
        "model":    modelo or LLM_MODEL,
        "messages": mensajes,
        "stream":   bool(request_id),
        "options":  {**_default_options(), **(opciones or {})},
    }

    last_exception = None
    cancel_event = threading.Event() if request_id else None
    if request_id and cancel_event is not None:
        _register_active_request(request_id, cancel_event)
    try:
        for attempt in range(1, OLLAMA_RETRIES + 2):
            try:
                if request_id:
                    request_session = requests.Session()
                    _set_active_session(request_id, request_session)
                    with request_session.post(
                        OLLAMA_URL, json=payload,
                        timeout=OLLAMA_TIMEOUT, stream=True
                    ) as resp:
                        _set_active_response(request_id, resp)
                        resp.raise_for_status()
                        partes = []
                        for raw_line in resp.iter_lines(chunk_size=1, decode_unicode=True):
                            if cancel_event is not None and cancel_event.is_set():
                                raise OllamaCancelled("Generacion cancelada por el usuario.")
                            if not raw_line:
                                continue
                            data = json.loads(raw_line)
                            fragmento = ((data.get("message") or {}).get("content") or "")
                            if fragmento:
                                partes.append(fragmento)
                            if data.get("done"):
                                break
                        if cancel_event is not None and cancel_event.is_set():
                            raise OllamaCancelled("Generacion cancelada por el usuario.")
                        return "".join(partes)
                # Sin streaming
                resp = _SESSION.post(OLLAMA_URL, json=payload, timeout=OLLAMA_TIMEOUT)
                resp.raise_for_status()
                data = resp.json()
                return data["message"]["content"]
            except OllamaCancelled:
                raise
            except requests.exceptions.RequestException as exc:
                last_exception = exc
                if cancel_event is not None and cancel_event.is_set():
                    raise OllamaCancelled("Generacion cancelada por el usuario.") from exc
                if attempt > OLLAMA_RETRIES:
                    raise
                time.sleep(OLLAMA_RETRY_BACKOFF * attempt)
        raise last_exception
    finally:
        if request_id:
            _unregister_active_request(request_id)


# ─────────────────────────────────────────────
#  STREAMING
# ─────────────────────────────────────────────

def stream_ollama(
    mensajes:   list,
    modelo:     str  = None,
    opciones:   dict = None,
    request_id: str | None = None,
):
    """
    Envia mensajes a Ollama y produce fragmentos de respuesta conforme llegan.
    Si se pasa request_id, la generacion puede cancelarse con cancel_request().
    """
    payload = {
        "model":    modelo or LLM_MODEL,
        "messages": mensajes,
        "stream":   True,
        "options":  {**_default_options(), **(opciones or {})},
    }

    last_exception = None
    cancel_event = threading.Event() if request_id else None
    if request_id and cancel_event is not None:
        _register_active_request(request_id, cancel_event)
    try:
        for attempt in range(1, OLLAMA_RETRIES + 2):
            try:
                request_session = requests.Session()
                if request_id:
                    _set_active_session(request_id, request_session)
                with request_session.post(
                    OLLAMA_URL, json=payload,
                    timeout=OLLAMA_TIMEOUT, stream=True
                ) as resp:
                    if request_id:
                        _set_active_response(request_id, resp)
                    try:
                        resp.raise_for_status()
                    except requests.exceptions.HTTPError as e:
                        error_detail = resp.text
                        try:
                            error_json = resp.json()
                            error_detail = error_json.get("error", str(error_json))
                        except Exception:
                            pass
                        logger.error(
                            "Ollama HTTP error",
                            extra={"status": resp.status_code, "detail": error_detail},
                        )
                        raise requests.exceptions.HTTPError(
                            f"Ollama HTTP {resp.status_code}: {error_detail}"
                        ) from e
                    for raw_line in resp.iter_lines(chunk_size=1, decode_unicode=True):
                        if cancel_event is not None and cancel_event.is_set():
                            raise OllamaCancelled("Generacion cancelada por el usuario.")
                        if not raw_line:
                            continue
                        data = json.loads(raw_line)
                        fragmento = ((data.get("message") or {}).get("content") or "")
                        if fragmento:
                            yield fragmento
                        if data.get("done"):
                            break
                    if cancel_event is not None and cancel_event.is_set():
                        raise OllamaCancelled("Generacion cancelada por el usuario.")
                    return
            except OllamaCancelled:
                raise
            except requests.exceptions.RequestException as exc:
                last_exception = exc
                if cancel_event is not None and cancel_event.is_set():
                    raise OllamaCancelled("Generacion cancelada por el usuario.") from exc
                if attempt > OLLAMA_RETRIES:
                    raise
                time.sleep(OLLAMA_RETRY_BACKOFF * attempt)
        raise last_exception
    finally:
        if request_id:
            _unregister_active_request(request_id)


# ─────────────────────────────────────────────
#  LIMPIEZA DE RESPUESTA
# ─────────────────────────────────────────────

def limpiar_respuesta(texto: str) -> str:
    """
    Limpia la respuesta del modelo eliminando:
    - Bloques <think>...</think> (modelos de razonamiento)
    - Tokens Thai/Unicode que Qwen3 filtra como thinking tokens
    - Formato markdown (**bold**, ##, __, * listas)
    - Bullets anidados: convierte sub-bullets en continuacion de linea
    - Espacios multiples (artefactos del tokenizer SentencePiece)
    """
    if not texto:
        return ""

    # Eliminar bloques de razonamiento interno
    texto = re.sub(r"<think>.*?</think>", "", texto, flags=re.DOTALL)
    # Eliminar tokens de pensamiento Thai que Qwen3 puede filtrar sin etiquetas XML
    texto = re.sub(r"[\u0E00-\u0E7F]+", "", texto)
    # Eliminar markdown: negrita, cursiva, encabezados
    # Insertar espacio cuando el marcador está pegado a texto adyacente
    # ej: "en**Bolivia**tiene" → "en Bolivia tiene"
    texto = re.sub(r"(\w)\*\*(.+?)\*\*(\w)", r"\1 \2 \3", texto)
    texto = re.sub(r"(\w)\*\*(.+?)\*\*",     r"\1 \2",    texto)
    texto = re.sub(r"\*\*(.+?)\*\*(\w)",     r"\1 \2",    texto)
    texto = re.sub(r"\*\*(.+?)\*\*",         r"\1",       texto)
    texto = re.sub(r"(\w)__(.+?)__(\w)",     r"\1 \2 \3", texto)
    texto = re.sub(r"(\w)__(.+?)__",         r"\1 \2",    texto)
    texto = re.sub(r"__(.+?)__(\w)",         r"\1 \2",    texto)
    texto = re.sub(r"__(.+?)__",             r"\1",       texto)
    texto = re.sub(r"^#{1,6}\s+", "", texto, flags=re.MULTILINE)
    # Eliminar asteriscos y guiones bajos sueltos
    texto = re.sub(r"(\w)\*(\w)", r"\1 \2", texto)   # *pegado entre palabras
    texto = texto.replace("*", "").replace("_", " ")

    # Colapsar saltos de línea simples en espacios (artefactos del tokenizer).
    # El modelo genera \n después de palabras en negrita: "en\nBolivia" → "en Bolivia"
    # Preservar solo \n\n como separadores de párrafo real.
    texto = re.sub(r'\n{2,}', '\u0000PARA\u0000', texto)
    texto = texto.replace('\n', ' ')
    texto = re.sub(r'[ \t]{2,}', ' ', texto)
    texto = texto.replace('\u0000PARA\u0000', '\n\n')

    # Normalizar listas (solo aplica si quedan \n\n reales)
    lineas = texto.splitlines()
    resultado = []
    for linea in lineas:
        stripped = linea.strip()
        if not stripped:
            resultado.append("")
            continue
        # Detectar sub-bullet (linea con indentacion + simbolo de lista)
        es_sub_bullet = bool(re.match(r"^(\s{2,}|\t+)[•\-\*●○▪▸►]", linea))
        if es_sub_bullet:
            contenido = re.sub(r"^[\s•\-\*●○▪▸►]+", "", linea).strip()
            if resultado and resultado[-1]:
                resultado[-1] = resultado[-1].rstrip(".,:") + ", " + contenido
            else:
                resultado.append(contenido)
        else:
            # Bullet de primer nivel: limpiar simbolo y dejar texto plano
            limpio = re.sub(r"^[•\-\*●○▪▸►]\s*", "", stripped)
            resultado.append(limpio)

    texto = "\n".join(resultado)
    # Colapsar lineas en blanco multiples
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    # Normalizar espacios multiples dentro de cada linea (artefactos del tokenizer)
    texto = re.sub(r"[ \t]{2,}", " ", texto)
    # Eliminar espacios antes de puntuacion
    texto = re.sub(r" +([.,;:!?])", r"\1", texto)
    # Filtrar caracteres no-latinos que Qwen3 mezcla de su entrenamiento
    # multilingue (arabe, chino, emoji, cirilico, etc.)
    # Se permite: ASCII imprimible + Latin-1 + Latin Extendido + puntuacion espanola
    texto = re.sub(r'[^\x20-\xFF\u0100-\u024F\u2013\u2014\u2026\n]', '', texto)
# Colapsar espacios dobles que hayan quedado al remover caracteres extranjeros
    texto = re.sub(r"[ \t]{2,}", " ", texto)
    # Reconstruir saltos de linea entre items de listas que el LLM genero
    # en lineas separadas pero fueron colapsados a un solo parrafo.
    # Patron 1: ". ItemCapitalizado:" → separa items de lista
    # Patron 2: ": ItemCapitalizado:" → separa primer item tras intro
    # Sistemico: funciona con cualquier lista, no solo servicios.
    texto = re.sub(r'(?<=[.:])(\s+)(?=[A-ZÁÉÍÓÚÑ][a-zA-ZáéíóúñÁÉÍÓÚÑ]+(?:\s+[a-zA-ZáéíóúñÁÉÍÓÚÑ]+)*\s*:)', r'<br>', texto)
    return texto.strip()


# ─────────────────────────────────────────────
#  VERIFICACION
# ─────────────────────────────────────────────

def ollama_disponible() -> bool:
    """Verifica si Ollama esta corriendo. Devuelve True si esta disponible."""
    base_url = OLLAMA_URL.replace("/api/chat", "")
    try:
        requests.get(base_url, timeout=3)
        return True
    except Exception:
        return False


def verificar_ollama() -> bool:
    """Verifica Ollama al arrancar e imprime el resultado. Devuelve True si disponible."""
    ok = ollama_disponible()
    if ok:
        logger.info("Ollama conectado", extra={"model": LLM_MODEL, "url": OLLAMA_URL})
    else:
        logger.warning("Ollama no responde", extra={"url": OLLAMA_URL})
    return ok
