"""
chatbots/general/translation_service.py
Servicio de traducción por lotes con múltiples backends.
"""

from __future__ import annotations

import json
import re

import requests

try:
    from deep_translator import GoogleTranslator

    _translator_available = True
except ImportError:
    GoogleTranslator = None  # type: ignore
    _translator_available = False


LANG_NAMES = {
    "es": "español",
    "en": "English",
    "fr": "français",
    "pt": "português",
    "zh": "中文",
    "ru": "русский",
}


def translate_texts(texts: list[str], lang: str, ollama_module) -> tuple[list[str], str]:
    if not texts:
        return [], "none"

    if _translator_available:
        try:
            translated = []
            translator = GoogleTranslator(source="auto", target=lang)
            for text in texts:
                translated.append(translator.translate(text))
            return translated, "deep_translator"
        except Exception:
            pass

    try:
        translated = []
        for text in texts:
            resp = requests.post(
                "https://libretranslate.com/translate",
                data={"q": text, "source": "auto", "target": lang},
                timeout=10,
            )
            if resp.ok:
                translated.append(resp.json().get("translatedText", text))
            else:
                translated.append(text)
        return translated, "libretranslate"
    except Exception:
        pass

    target_lang = LANG_NAMES.get(lang, "español")
    input_json = json.dumps(texts, ensure_ascii=False)
    prompt = (
        f"Eres un traductor profesional. Traduce la siguiente lista de mensajes al idioma **{target_lang}**. "
        "La entrada es una lista JSON. Debes devolver SOLO una lista JSON con las traducciones en el mismo orden. "
        "No añadas explicaciones, ni números de índice, solo el JSON resultante.\n\n"
        f"Entrada:\n{input_json}"
    )

    respuesta = ollama_module.llamar_ollama([{"role": "user", "content": prompt}])
    respuesta = ollama_module.limpiar_respuesta(respuesta)

    match = re.search(r"\[.*\]", respuesta, re.DOTALL)
    if not match:
        return texts, "fallback_original"

    json_str = match.group(0)
    try:
        traducciones = json.loads(json_str)
    except json.JSONDecodeError:
        return texts, "fallback_original"

    if isinstance(traducciones, list) and len(traducciones) == len(texts):
        return traducciones, "ollama"
    return texts, "fallback_original"
