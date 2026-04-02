"""
chatbots/general/routes.py
Rutas Flask del chatbot general. Usa el core/ para toda la lógica.

GET  /api/welcome
POST /api/chat
GET  /api/sucursales
GET  /api/idiomas
POST /api/reset
GET  /api/status
POST /api/actualizar
"""

import sys
import os
import threading
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "core"))

import requests
import json
from flask import Blueprint, request, jsonify

from core import rag, ollama, session, location, idiomas, intents, updater, capabilities
import tarifas

# intentamos usar biblioteca de traducción local para evitar llamadas a LLM
try:
    from deep_translator import GoogleTranslator
    _translator_available = True
except ImportError:
    GoogleTranslator = None  # type: ignore
    _translator_available = False
from chatbots.general.config import (
    NOMBRE, CHROMA_PATH, DATA_FILE, SUCURSALES_FILE, SECCIONES_FILE, HISTORIA_FILE,
    construir_prompt, REQUIRE_EVIDENCE,
)

# ─────────────────────────────────────────────
#  BLUEPRINT
# ─────────────────────────────────────────────
bp = Blueprint("general", __name__)   # sin prefix → rutas en /api/*

SUCURSALES: list = []
CHATBOT_GENERAL_ONLY = os.environ.get("CHATBOT_GENERAL_ONLY", "false").strip().lower() in ("1", "true", "yes")
GENERAL_SYSTEM_PROMPT = (
    "Eres un asistente conversacional general, útil, claro y profesional. "
    "No afirmes tener acceso a bases de datos, documentos, skills, RAG, PDFs, scraping o contexto institucional "
    "si no aparecen explícitamente en la conversación. "
    "Responde solo con conocimiento general del modelo y con lo que diga el usuario en esta charla. "
    "Mantén respuestas breves, naturales y en el mismo idioma del usuario."
)


def _modo_general_only() -> bool:
    return CHATBOT_GENERAL_ONLY


def _respuesta_chat_vacio(lang: str, pregunta: str) -> str:
    texto = (pregunta or "").strip().lower()
    if any(token in texto for token in ("hola", "buenas", "hello", "bonjour", "olá", "ola", "hi")):
        if lang == "en":
            return "Hello. This chatbot has no information loaded yet."
        if lang == "fr":
            return "Bonjour. Ce chatbot n'a encore aucune information chargée."
        if lang == "pt":
            return "Olá. Este chatbot ainda não tem informações carregadas."
        if lang == "zh":
            return "您好。这个聊天机器人目前还没有加载任何信息。"
        if lang == "ru":
            return "Здравствуйте. В этом чат-боте пока не загружена информация."
        return "Hola. Este chatbot todavía no tiene información cargada."

    if lang == "en":
        return "I have no information loaded yet."
    if lang == "fr":
        return "Je n'ai encore aucune information chargée."
    if lang == "pt":
        return "Ainda não tenho nenhuma informação carregada."
    if lang == "zh":
        return "我目前还没有加载任何信息。"
    if lang == "ru":
        return "У меня пока нет загруженной информации."
    return "No tengo información cargada todavía."


def _normalizar_busqueda_local(texto: str) -> str:
    texto = (texto or "").lower().strip()
    texto = re.sub(r"[^a-z0-9áéíóúñü\s]", " ", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def _cargar_contexto_local_minimo() -> list[dict]:
    fuentes = []

    try:
        pdfs_path = os.path.join(os.path.dirname(DATA_FILE), "pdfs_contenido.json")
        if os.path.exists(pdfs_path):
            with open(pdfs_path, "r", encoding="utf-8") as fh:
                pdfs = json.load(fh)
            for item in pdfs:
                texto = (item.get("texto_extraido") or "").strip()
                if not texto:
                    continue
                fuentes.append({
                    "source_type": "pdf",
                    "source_name": item.get("nombre_archivo") or "PDF",
                    "source_url": item.get("url") or "",
                    "texto": texto,
                })
    except Exception:
        pass

    try:
        historia_path = HISTORIA_FILE
        if historia_path and not os.path.isabs(historia_path):
            historia_path = os.path.join(os.path.dirname(DATA_FILE), os.path.basename(historia_path))
        if os.path.exists(historia_path):
            with open(historia_path, "r", encoding="utf-8") as fh:
                historia = json.load(fh)
            for item in historia if isinstance(historia, list) else []:
                texto = (item.get("contenido") or "").strip()
                if not texto:
                    continue
                fuentes.append({
                    "source_type": "history",
                    "source_name": item.get("titulo") or "Historia",
                    "source_url": item.get("url") or "",
                    "texto": texto,
                })
    except Exception:
        pass

    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as fh:
                texto = fh.read().strip()
            if texto:
                fuentes.append({
                    "source_type": "web_main",
                    "source_name": "Texto base",
                    "source_url": "",
                    "texto": texto,
                })
    except Exception:
        pass

    return fuentes


def _buscar_contexto_local_minimo(pregunta: str) -> dict:
    consulta = _normalizar_busqueda_local(pregunta)
    palabras = [w for w in consulta.split() if len(w) >= 4]
    if not palabras:
        palabras = consulta.split()

    candidatos = []
    for fuente in _cargar_contexto_local_minimo():
        texto = fuente["texto"]
        texto_norm = _normalizar_busqueda_local(texto)
        score = 0
        for palabra in palabras:
            if palabra and palabra in texto_norm:
                score += 2
        if consulta and consulta in texto_norm:
            score += 4
        if score <= 0:
            continue

        inicio = 0
        for palabra in palabras:
            pos = texto_norm.find(palabra)
            if pos >= 0:
                inicio = pos
                break
        snippet = texto[max(0, inicio - 220):inicio + 650].strip() or texto[:700].strip()
        candidatos.append({
            "score": score,
            "context": snippet,
            "source_type": fuente["source_type"],
            "source_name": fuente["source_name"],
            "source_url": fuente["source_url"],
        })

    candidatos.sort(key=lambda item: (-item["score"], item["source_name"]))
    if not candidatos:
        return {"context": "", "sources": [], "primary_source_type": None}

    top = candidatos[:2]
    context = "\n\n".join(item["context"] for item in top if item["context"])
    sources = [{
        "label": f"{item['source_type']}: {item['source_name']}",
        "source_name": item["source_name"],
        "source_page": "",
        "source_path": "",
        "source_type": item["source_type"],
        "source_url": item["source_url"],
    } for item in top]
    return {
        "context": context,
        "sources": sources,
        "primary_source_type": top[0]["source_type"],
    }


def _respuesta_extractiva_local(pregunta: str, contexto: str, lang: str) -> str:
    consulta = _normalizar_busqueda_local(pregunta)
    palabras = [w for w in consulta.split() if len(w) >= 4]
    if not palabras:
        palabras = consulta.split()

    texto = (contexto or "").strip()
    if not texto:
        return _respuesta_chat_vacio(lang, pregunta)

    bloques = [b.strip() for b in re.split(r"\n\s*\n", texto) if b.strip()]
    candidatos = []
    for bloque in bloques:
        bloque_norm = _normalizar_busqueda_local(bloque)
        score = 0
        if consulta and consulta in bloque_norm:
            score += 4
        for palabra in palabras:
            if palabra and palabra in bloque_norm:
                score += 2
        if score > 0:
            candidatos.append((score, bloque))

    if not candidatos:
        return _respuesta_chat_vacio(lang, pregunta)

    candidatos.sort(key=lambda item: -item[0])
    mejor = candidatos[0][1]
    lineas = [l.strip() for l in mejor.splitlines() if l.strip() and not l.strip().startswith("--- Página")]
    if not lineas:
        return _respuesta_chat_vacio(lang, pregunta)

    texto_lineal = " ".join(lineas).strip()
    if not texto_lineal:
        return _respuesta_chat_vacio(lang, pregunta)

    consulta = _normalizar_busqueda_local(pregunta)
    texto_norm = _normalizar_busqueda_local(texto_lineal)
    inicio_real = 0
    if consulta and consulta in texto_norm:
        inicio_real = texto_norm.find(consulta)
    else:
        for palabra in palabras:
            pos = texto_norm.find(palabra)
            if pos >= 0:
                inicio_real = pos
                break

    ventana_inicio = max(0, inicio_real - 180)
    ventana_fin = min(len(texto_lineal), inicio_real + 1100)
    respuesta = texto_lineal[ventana_inicio:ventana_fin].strip()

    if ventana_inicio > 0:
        respuesta = "... " + respuesta
    if ventana_fin < len(texto_lineal):
        respuesta = respuesta.rstrip() + " ..."

    if len(respuesta) > 1200:
        respuesta = respuesta[:1200].rsplit(" ", 1)[0].strip() + " ..."
    return respuesta or _respuesta_chat_vacio(lang, pregunta)


def _respuesta_tarifaria_directa(tarifa_result: dict, lang: str) -> str:
    detalle = tarifa_result.get("tariff_result") or {}
    monto = detalle.get("amount_bs")
    servicio = detalle.get("service") or "el servicio consultado"
    peso = detalle.get("weight_g")
    destino = detalle.get("destination") or "la modalidad indicada"
    rango = detalle.get("matched_range") or ""

    if monto is None:
        return _respuesta_chat_vacio(lang, "")

    peso_txt = ""
    if isinstance(peso, (int, float)):
        if float(peso) >= 1000:
            kg = float(peso) / 1000.0
            peso_txt = f"{kg:.2f}".rstrip("0").rstrip(".") + " kg"
        else:
            peso_txt = f"{int(peso) if float(peso).is_integer() else peso} g"

    monto_txt = f"{int(monto) if float(monto).is_integer() else monto}"

    if lang == "en":
        return (
            f"The exact cost is Bs {monto_txt} for {servicio}, with a weight of {peso_txt}, "
            f"under the {destino} column. Applicable range: {rango}."
        )
    if lang == "pt":
        return (
            f"O custo exato é Bs {monto_txt} para {servicio}, com peso de {peso_txt}, "
            f"na coluna {destino}. Faixa aplicada: {rango}."
        )
    if lang == "fr":
        return (
            f"Le coût exact est de Bs {monto_txt} pour {servicio}, avec un poids de {peso_txt}, "
            f"dans la colonne {destino}. Plage appliquée : {rango}."
        )
    if lang == "zh":
        return (
            f"准确费用是 Bs {monto_txt}。服务：{servicio}，重量：{peso_txt}，对应栏目：{destino}。适用区间：{rango}。"
        )
    if lang == "ru":
        return (
            f"Точная стоимость: Bs {monto_txt}. Услуга: {servicio}, вес: {peso_txt}, "
            f"колонка: {destino}. Применённый диапазон: {rango}."
        )
    return (
        f"El costo exacto es Bs {monto_txt} para {servicio}, con un peso de {peso_txt}, "
        f"en la columna {destino}. El rango aplicado del tarifario es: {rango}."
    )


def _respuesta_tarifaria_faltante(tarifa_result: dict, lang: str) -> str:
    contexto = (tarifa_result.get("prompt_context") or "").strip()
    if not contexto:
        return _respuesta_chat_vacio(lang, "")
    if lang == "en":
        return contexto
    if lang == "pt":
        return contexto
    if lang == "fr":
        return contexto
    if lang == "zh":
        return contexto
    if lang == "ru":
        return contexto
    return contexto

def _extraer_citas_evidencia(respuesta: str) -> list[str]:
    """
    Extrae citas entre comillas dobles desde una línea 'EVIDENCIA:'.
    Devuelve lista vacía si no hay evidencia.
    """
    if not respuesta:
        return []
    for line in (respuesta or "").splitlines():
        if line.strip().lower().startswith("evidencia:"):
            return [q.strip() for q in re.findall(r"\"([^\"]+)\"", line) if q.strip()]
    return []


def _validar_evidencia_en_contexto(citas: list[str], contexto: str) -> bool:
    if not citas:
        return False
    ctx = contexto or ""
    return all(cita in ctx for cita in citas)


def _refresh_pdfs_after_start() -> None:
    """Revisa PDFs heredados después del arranque para no bloquear Flask."""
    try:
        pdf_refresh = capabilities.reprocesar_pdfs_pendientes()
        if pdf_refresh.get("mejorados"):
            print(
                "  PDFs heredados mejorados tras arranque "
                f"({pdf_refresh['mejorados']} mejoras) → reindexando..."
            )
            reindexar()
        elif pdf_refresh.get("reprocesados"):
            print(
                "  PDFs revisados en segundo plano: "
                f"{pdf_refresh['reprocesados']} reprocesados, "
                f"{pdf_refresh['mejorados']} mejorados."
            )
    except Exception as e:
        print(f"   Error validando PDFs tras arranque: {e}")


def _rag_chunks_seguro() -> int:
    if _modo_general_only():
        return 0
    try:
        return rag.total_chunks()
    except Exception:
        return 0


def _estado_capacidades() -> dict:
    return capabilities.get_runtime_capabilities(
        chunks=_rag_chunks_seguro(),
        embedding_model=os.environ.get("EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2"),
        chroma_path=CHROMA_PATH,
        ollama_ok=ollama.ollama_disponible(),
        modelo=os.environ.get("LLM_MODEL", "correos-bot"),
        sesiones_activas=session.total_sesiones(),
        sucursales=SUCURSALES,
        actualizacion=updater.get_estado(),
    )


# ─────────────────────────────────────────────
#  REINDEXADO
# ─────────────────────────────────────────────

def reindexar() -> bool:
    """Indexa en ChromaDB los datos generados por el scraper.

    Además del texto principal y las sucursales/secciones, incorpora los
    textos extraídos de los PDF que el scraper descargó. El JSON
    `pdfs_contenido.json` está situado en el mismo directorio de datos.
    """
    global SUCURSALES
    chunks, ids, metadatas = [], [], []

    try:
        pdf_refresh = capabilities.reprocesar_pdfs_pendientes()
        if pdf_refresh.get("reprocesados"):
            print(
                "   PDFs reprocesados antes de indexar: "
                f"{pdf_refresh['reprocesados']} | mejorados: {pdf_refresh['mejorados']} | "
                f"fallidos: {pdf_refresh['fallidos']}"
            )
    except Exception as e:
        print(f"   Error refrescando PDFs antes del RAG: {e}")

    # 1. Texto principal (HTML plano acumulado)
    c, i, m = rag.archivo_a_documentos(
        DATA_FILE,
        prefijo="txt",
        metadata_base={
            "source_type": "web_main",
            "source_label": "Sitio principal de Correos de Bolivia",
            "source_path": DATA_FILE,
        },
    )
    chunks += c; ids += i; metadatas += m

    # 2. Sucursales
    SUCURSALES = location.cargar_sucursales(SUCURSALES_FILE)
    for idx, s in enumerate(SUCURSALES):
        nombre = s.get("nombre", f"Sucursal {idx + 1}")
        c, i, m = rag.documento_a_chunks(
            location.sucursal_a_texto(s),
            prefijo=f"suc_{idx}",
            metadata_base={
                "source_type": "branch",
                "source_name": nombre,
                "source_label": nombre,
                "city": nombre,
            },
        )
        chunks += c; ids += i; metadatas += m

    # 3. Secciones del home
    c, i = location.cargar_secciones(SECCIONES_FILE)
    for idx, texto in enumerate(c):
        source_name = i[idx] if idx < len(i) else f"seccion_{idx}"
        sec_chunks, sec_ids, sec_meta = rag.documento_a_chunks(
            texto,
            prefijo=source_name,
            metadata_base={
                "source_type": "section",
                "source_name": source_name,
                "source_label": source_name.replace("sec_", "").replace("_", " "),
            },
        )
        chunks += sec_chunks; ids += sec_ids; metadatas += sec_meta

    # 4. Contenido de PDFs (si existe el JSON generado por el scraper)
    try:
        pdf_path = os.path.join(os.path.dirname(DATA_FILE), "pdfs_contenido.json")
        if os.path.exists(pdf_path):
            with open(pdf_path, "r", encoding="utf-8") as f:
                pdfs = json.load(f)
            for idx, p in enumerate(pdfs):
                texto = p.get("texto_extraido") or ""
                if texto:
                    nombre_pdf = p.get("nombre_archivo") or f"PDF {idx + 1}"
                    pdf_chunks, pdf_ids, pdf_meta = rag.documento_a_chunks(
                        texto,
                        prefijo=f"pdf_{idx}",
                        metadata_base={
                            "source_type": "pdf",
                            "source_name": nombre_pdf,
                            "source_label": nombre_pdf,
                            "source_url": p.get("url", ""),
                            "source_page": p.get("pagina_fuente", ""),
                            "extraction_method": p.get("metodo_extraccion", ""),
                        },
                    )
                    chunks += pdf_chunks; ids += pdf_ids; metadatas += pdf_meta
    except Exception as e:
        print(f"   Error leyendo PDF JSON: {e}")

    # 5. Historia institucional (si existe el JSON generado por el scraper)
    try:
        historia_path = HISTORIA_FILE
        if historia_path and not os.path.isabs(historia_path):
            historia_path = os.path.join(os.path.dirname(DATA_FILE), os.path.basename(historia_path))
        if os.path.exists(historia_path):
            with open(historia_path, "r", encoding="utf-8") as f:
                historia = json.load(f)
            for idx, item in enumerate(historia):
                if not isinstance(item, dict):
                    continue
                contenido = (item.get("contenido") or "").strip()
                if not contenido:
                    continue
                titulo = item.get("titulo") or f"Historia {idx + 1}"
                hist_chunks, hist_ids, hist_meta = rag.documento_a_chunks(
                    contenido,
                    prefijo=f"hist_{idx}",
                    metadata_base={
                        "source_type": "history",
                        "source_name": titulo,
                        "source_label": titulo,
                        "source_url": item.get("url", ""),
                        "years": ", ".join(str(y) for y in item.get("anos_mencionados", [])[:12]),
                    },
                )
                chunks += hist_chunks; ids += hist_ids; metadatas += hist_meta
    except Exception as e:
        print(f"   Error leyendo historia institucional: {e}")

    return rag.indexar(chunks, ids, metadatas=metadatas)


# ─────────────────────────────────────────────
#  INICIALIZACIÓN
# ─────────────────────────────────────────────

def inicializar():
    """Llamar desde main.py al arrancar la app."""
    global SUCURSALES
    print(f"\n🤖 Iniciando {NOMBRE}...")

    SUCURSALES = location.cargar_sucursales(SUCURSALES_FILE)

    if _modo_general_only():
        print("  Modo general activo → sin embeddings, sin ChromaDB y sin RAG al arranque")
        updater.iniciar_scheduler(reindexar_fn=reindexar)
        print(f" {NOMBRE} listo en http://localhost:5000\n")
        return

    rag.inicializar(chroma_path=CHROMA_PATH, collection_name="general")

    if rag.total_chunks() == 0:
        print("  BD vacía → indexando datos del scraper...")
        reindexar()
    else:
        print(f" BD lista ({rag.total_chunks()} chunks)")
        SUCURSALES = location.cargar_sucursales(SUCURSALES_FILE)
        threading.Thread(target=_refresh_pdfs_after_start, daemon=True).start()

    updater.iniciar_scheduler(reindexar_fn=reindexar)
    print(f" {NOMBRE} listo en http://localhost:5000\n")


# ─────────────────────────────────────────────
#  RUTAS
# ─────────────────────────────────────────────

@bp.route("/api/welcome", methods=["GET"])
def welcome():
    lang = request.args.get("lang", idiomas.IDIOMA_DEFAULT)
    if lang not in idiomas.IDIOMAS:
        lang = idiomas.IDIOMA_DEFAULT
    return jsonify({"response": idiomas.IDIOMAS[lang]["bienvenida"], "lang": lang})


@bp.route("/api/chat", methods=["POST"])
def chat():
    sid = session.get_sid()

    data     = request.get_json(silent=True) or {}
    pregunta = data.get("message", "").strip()

    if not pregunta:
        return jsonify({"error": "Pregunta vacía"}), 400

    # resolver el idioma lo antes posible para usarlo también en respuestas
    lang = idiomas.resolver_idioma(data.get("lang"), pregunta)

    # traducción automática: el frontend envía un mensaje como
    # "Traduce EXACTAMENTE este texto al <idioma>...". No queremos aplicar
    # la detección de intenciones ni devolver la lista de sucursales.
    # Simplemente reenviamos la petición al modelo y devolvemos lo que diga.
    if pregunta.lower().startswith("traduce exactamente"):
        try:
            # construimos mensajes mínimos para Ollama
            respuesta = ollama.llamar_ollama([
                {"role": "user", "content": pregunta}
            ])
            respuesta = ollama.limpiar_respuesta(respuesta)
            return jsonify({"response": respuesta, "lang": lang})
        except Exception as e:
            return jsonify({"error": f"Error traduciéndose: {e}"}), 500

    if _modo_general_only():
        tarifa_result = tarifas.resolve_tariff_query(pregunta)
        if tarifa_result is not None:
            if tarifa_result.get("mode") == "answer":
                respuesta = _respuesta_tarifaria_directa(tarifa_result, lang)
            else:
                respuesta = _respuesta_tarifaria_faltante(tarifa_result, lang)

            session.agregar_turno(sid, pregunta, respuesta)
            return jsonify({
                "response": respuesta,
                "lang": lang,
                "general_only": True,
                "skill_resolution": {
                    "in_scope": None,
                    "primary_skill": None,
                    "matched_skills": [],
                },
                "sources": tarifa_result.get("sources", []),
                "primary_source_type": tarifa_result.get("primary_source_type"),
                "tariff_result": tarifa_result.get("tariff_result"),
            })

        local_result = _buscar_contexto_local_minimo(pregunta)
        contexto = local_result.get("context", "").strip()
        sistema = (
            f"CRITICAL LANGUAGE RULE: {idiomas.IDIOMAS[lang]['instruccion']} "
            f"You MUST respond ONLY in that language.\n\n"
            "Eres un asistente que razona SOLO con el CONTEXTO LOCAL proporcionado.\n"
            "Tu tarea es interpretar, resumir y responder con claridad usando exclusivamente ese contenido.\n"
            "Responde de forma breve, puntual y útil. Prioriza la respuesta directa antes que la explicación larga.\n"
            "Si la pregunta pide un dato puntual, responde primero con ese dato en una o dos frases.\n"
            "Solo añade una breve aclaración extra si realmente mejora la comprensión.\n"
            "No inventes datos, no completes huecos con conocimiento externo y no afirmes nada que no esté sustentado en el contexto.\n"
            f"Si el contexto no alcanza para responder, di exactamente: \"{_respuesta_chat_vacio(lang, pregunta)}\"\n"
            "Si el usuario pide una explicación, puedes reorganizar la información y redactarla de forma más clara, "
            "pero sin salirte del contenido disponible.\n\n"
            f"CONTEXTO LOCAL:\n{contexto}\n"
        )
        mensajes = [
            {"role": "system", "content": sistema},
            {"role": "user", "content": pregunta},
        ]

        try:
            respuesta = ollama.limpiar_respuesta(ollama.llamar_ollama(mensajes))
            respuesta_limpia = (respuesta or "").strip()
            if not respuesta_limpia:
                respuesta = _respuesta_chat_vacio(lang, pregunta)
        except Exception:
            return jsonify({"error": "Error razonando con la IA sobre el contexto local."}), 500

        respuesta = re.sub(r"\s+", " ", (respuesta or "")).strip()
        if len(respuesta) > 450:
            respuesta = respuesta[:450].rsplit(" ", 1)[0].strip() + "..."

        session.agregar_turno(sid, pregunta, respuesta)
        return jsonify({
            "response": respuesta,
            "lang": lang,
            "general_only": True,
            "skill_resolution": {
                "in_scope": None,
                "primary_skill": None,
                "matched_skills": [],
            },
            "sources": local_result.get("sources", []),
            "primary_source_type": local_result.get("primary_source_type"),
        })

    # si el usuario responde con un pedido corto, reorganizamos la pregunta para
    # no perder el tema anterior. La función `es_pedido_corto` revisa comandos
    # como "dame" o mensajes muy breves.
    if intents.es_pedido_corto(pregunta):
        hist = session.get_historial(session.get_sid())
        # buscar el último mensaje del propio usuario en el historial
        last_user = None
        for entry in reversed(hist):
            if entry.get("role") == "user":
                last_user = entry.get("content")
                break
        if last_user:
            nueva = f"{last_user} {pregunta}"
            print(f" Follow‑up detectado, reescribiendo pregunta: '{pregunta}' → '{nueva}'")
            pregunta = nueva  # añade contexto

    t    = idiomas.IDIOMAS[lang]
    skill_resolution = capabilities.resolve_skills_for_query(pregunta)

    consulta_especial = capabilities.detectar_consulta_especial(pregunta)
    if consulta_especial is not None:
        estado = _estado_capacidades()
        resultado = capabilities.execute_special_query(consulta_especial, estado)
        respuesta = resultado["response"]
        session.agregar_turno(sid, pregunta, respuesta)
        return jsonify(
            {
                "response": respuesta,
                "lang": lang,
                "capabilities": estado,
                "tool_result": resultado,
            }
        )

    # ── 1. Saludo → sin Ollama
    if intents.es_saludo(pregunta):
        return jsonify({"response": t["saludo"], "lang": lang})

    # ── 1.5 Presentación
    if intents.es_presentacion(pregunta):
        return jsonify({
            "response": (
                "Soy ChatbotBO, el asistente virtual de la Agencia Boliviana de "
                "Correos. ¿En qué puedo ayudarte?"
            ),
            "lang": lang,
        })

    # ── 2. Despedida
    if intents.es_despedida(pregunta):
        session.limpiar_historial(sid)
        return jsonify({"response": t["despedida"], "despedida": True, "lang": lang})

    # ── 3. ¿Solo nombre de ciudad?
    geo = intents.detectar_solo_ciudad(pregunta, SUCURSALES)

    # ── 4. ¿Consulta de ubicación con palabras clave?
    if geo is None:
        geo = intents.detectar_consulta_ubicacion(pregunta, SUCURSALES)

    # ── 5. Responder con tarjeta de sucursal
    if geo is not None:
        if "nombre" not in geo:
            nombres = " | ".join(s.get("nombre", "") for s in SUCURSALES)
            # usar .get para evitar KeyError si la traducción falta en caliente
            mensaje = t.get("pedir_ciudad")
            if mensaje is None:
                # el servidor puede estar ejecutándose con una versión antigua de
                # idiomas.py; reiniciar lo recargará y evitará este error.
                mensaje = f"Por favor indica una ciudad válida: {nombres}"
            else:
                mensaje = mensaje.format(ciudades=nombres)

            return jsonify({
                "response": mensaje,
                "lang"    : lang,
                "no_translate": True,   # no traducir esta frase cuando el usuario cambie idioma
            })

        lat      = geo.get("lat")
        lng      = geo.get("lng")
        maps_url = location.generar_maps_url(lat, lng) if lat and lng else None
        nd       = t["no_disponible"]

        texto_resp = (
            f" {geo.get('nombre', '')}\n"
            f"Dirección : {geo.get('direccion') or nd}\n"
            f"Teléfono  : {geo.get('telefono') or nd}\n"
            f"Email     : {geo.get('email') or nd}\n"
            f"Horario   : {geo.get('horario') or nd}"
        )
        if maps_url:
            texto_resp += f"\nVer en mapa: {maps_url}"

        session.agregar_turno(sid, pregunta, texto_resp)

        resp_json = {"response": texto_resp, "lang": lang}
        if lat and lng:
            resp_json["ubicacion"] = {
                "nombre"   : geo.get("nombre",    ""),
                "direccion": geo.get("direccion", ""),
                "telefono" : geo.get("telefono",  ""),
                "email"    : geo.get("email",     ""),
                "horario"  : geo.get("horario",   ""),
                "lat"      : lat,
                "lng"      : lng,
                "maps_url" : maps_url,
            }
        return jsonify(resp_json)

    if not skill_resolution["in_scope"]:
        respuesta = capabilities.out_of_scope_response()
        session.agregar_turno(sid, pregunta, respuesta)
        return jsonify({
            "response": respuesta,
            "lang": lang,
            "skill_resolution": {
                "in_scope": False,
                "primary_skill": None,
                "matched_skills": [],
            },
        })

    tarifa_result = tarifas.resolve_tariff_query(pregunta)
    if tarifa_result is not None:
        if tarifa_result.get("mode") == "answer":
            respuesta = _respuesta_tarifaria_directa(tarifa_result, lang)
        else:
            respuesta = _respuesta_tarifaria_faltante(tarifa_result, lang)

        session.agregar_turno(sid, pregunta, respuesta)
        return jsonify({
            "response": respuesta,
            "lang": lang,
            "skill_resolution": {
                "in_scope": skill_resolution["in_scope"],
                "primary_skill": (
                    (skill_resolution.get("primary_skill") or {}).get("id")
                    or "calculadora_tarifas"
                ),
                "matched_skills": skill_resolution.get("skill_ids", []),
            },
            "sources": tarifa_result.get("sources", []),
            "primary_source_type": tarifa_result.get("primary_source_type"),
            "tariff_result": tarifa_result.get("tariff_result"),
        })

    # ── 6. Consulta general → RAG + Ollama
    try:
        rag_result = rag.buscar(
            pregunta,
            preferred_source_types=capabilities.preferred_sources_for_skill(
                skill_resolution.get("primary_skill")
            ),
        )
        contexto = rag_result.get("context", "")
    except Exception as e:
        return jsonify({"error": f"Error en búsqueda RAG: {e}"}), 500

    sources = rag_result.get("sources", [])
    valid_sources = [s for s in sources if s.get("source_type") and s.get("source_type") != "unknown"]
    if not contexto.strip() or not valid_sources:
        respuesta = t["sin_info"]
        session.agregar_turno(sid, pregunta, respuesta)
        return jsonify({
            "response": respuesta,
            "lang": lang,
            "skill_resolution": {
                "in_scope": skill_resolution["in_scope"],
                "primary_skill": (skill_resolution.get("primary_skill") or {}).get("id"),
                "matched_skills": skill_resolution.get("skill_ids", []),
            },
            "sources": sources,
            "primary_source_type": rag_result.get("primary_source_type"),
        })

    hora     = session.get_hora_bolivia()
    primary_skill = skill_resolution.get("primary_skill") or {}
    sistema  = construir_prompt(
        t["instruccion"],
        contexto,
        hora,
        t["sin_info"],
        skills_context=capabilities.build_skill_manifest(),
        skill_name=primary_skill.get("nombre", ""),
        skill_description=primary_skill.get("descripcion", ""),
        skill_triggers=primary_skill.get("trigger", ""),
    )
    mensajes = [
        {"role": "system", "content": sistema},
        *session.historial_reciente(sid),
        {"role": "user",   "content": pregunta},
    ]

    try:
        print(f" [{lang}] {pregunta[:60]}")
        respuesta = ollama.llamar_ollama(mensajes)
        respuesta = ollama.limpiar_respuesta(respuesta)

        # Guardia anti-alucinación: si se exige evidencia, solo aceptamos la
        # respuesta si trae 1-2 citas literales que existan en el contexto RAG.
        if REQUIRE_EVIDENCE:
            citas = _extraer_citas_evidencia(respuesta)
            if not _validar_evidencia_en_contexto(citas, contexto):
                respuesta = t["sin_info"]

        # si el modelo no encontró nada relevante a partir del contexto, a
        # veces devuelve simplemente el system prompt o la frase de
        # presentación. Detectamos esa situación y devolvemos el texto de
        # "sin_info" en lugar de repetir el saludo.
        presentacion_corta = (
            "Soy ChatbotBO, el asistente virtual de la Agencia Boliviana de "
            "Correos. ¿En qué puedo ayudarte?"
        )
        if respuesta.startswith("Eres ChatbotBO") or respuesta.strip().startswith(presentacion_corta):
            respuesta = t["sin_info"]

        session.agregar_turno(sid, pregunta, respuesta)
        print(f" [{lang}] {len(respuesta)} chars")
        return jsonify({
            "response": respuesta,
            "lang": lang,
            "skill_resolution": {
                "in_scope": skill_resolution["in_scope"],
                "primary_skill": primary_skill.get("id"),
                "matched_skills": skill_resolution.get("skill_ids", []),
            },
            "sources": rag_result.get("sources", []),
            "primary_source_type": rag_result.get("primary_source_type"),
        })

    except requests.exceptions.Timeout:
        return jsonify({"error": "El modelo tardó demasiado. Intenta de nuevo."}), 504
    except Exception as e:
        return jsonify({"error": f"Error generando respuesta: {e}"}), 500

# ─────────────────────────────────────────────
#  TRADUCCIÓN POR LOTES
# ─────────────────────────────────────────────

@bp.route("/api/translate", methods=["POST"])
def translate_bulk():
    """
    Traduce texto(s) a un idioma objetivo.

    Se espera un JSON con al menos:
      { "lang": "en" }
    Opcionalmente el cliente puede pasar un array de textos explícitos:
      { "texts": ["hola", "adios"], "lang": "en" }
    Si `texts` no está presente, la función usa el historial de la sesión
    para reconstruir los textos.

    Devuelve: { "translations": ["texto1", "texto2", ...], "lang": lang }
    """
    data = request.get_json(silent=True) or {}
    lang = data.get("lang", idiomas.IDIOMA_DEFAULT)

    # 1. Preparar lista inicial de textos a traducir. El frontend puede
    #    proporcionar el array directamente, lo cual evita discrepancias
    #    entre lo que el usuario ve y lo que el servidor guarda en sesión.
    textos_a_traducir = data.get("texts")

    if textos_a_traducir is None:
        # No se enviaron textos explícitos: reconstruimos a partir del
        # historial de la sesión, como antes.
        sid = session.get_sid()
        historial = session.get_historial(sid)
        if not historial:
            return jsonify({"translations": [], "lang": lang})

        textos_a_traducir = []
        for entry in historial:
            content = entry.get("content", "")
            if " " in content or "Ver en mapa:" in content or entry.get("role") == "system":
                continue
            textos_a_traducir.append(content)

        if not textos_a_traducir:
            return jsonify({"translations": [], "lang": lang})

    # opcional: registrar para depuración
    print(f"🔤 Traducción solicitada ({lang}) para {len(textos_a_traducir)} textos")

    # 4. Si disponemos de biblioteca local, úsala y evitamos el modelo LLM
    # Primero, si instalamos deep-translator, úsalo
    if _translator_available:
        try:
            translated = []
            translator = GoogleTranslator(source='auto', target=lang)
            for t in textos_a_traducir:
                translated.append(translator.translate(t))
            return jsonify({"translations": translated, "lang": lang})
        except Exception as e:
            print(f"  Error usando deep_translator: {e}")
            # si falla, no abortamos: seguiremos a siguientes opciones

    # Si la librería no está disponible o falló, intentamos un servicio gratuito
    try:
        translated = []
        for t in textos_a_traducir:
            resp = requests.post(
                "https://libretranslate.com/translate",
                data={"q": t, "source": "auto", "target": lang},
                timeout=10
            )
            if resp.ok:
                translated.append(resp.json().get("translatedText", t))
            else:
                translated.append(t)
        return jsonify({"translations": translated, "lang": lang})
    except Exception as e:
        print(f"  Error contactando LibreTranslate: {e}")
        # seguimos al fallback con Llama
    lang_names = {
        "es": "español", "en": "English", "fr": "français", 
        "pt": "português", "zh": "中文", "ru": "русский"
    }
    target_lang = lang_names.get(lang, "español")

    # Creamos un JSON string con los textos para que el modelo lo procese
    input_json = json.dumps(textos_a_traducir, ensure_ascii=False)
    
    prompt = (
        f"Eres un traductor profesional. Traduce la siguiente lista de mensajes al idioma **{target_lang}**. "
        f"La entrada es una lista JSON. Debes devolver SOLO una lista JSON con las traducciones en el mismo orden. "
        f"No añadas explicaciones, ni números de índice, solo el JSON resultante.\n\n"
        f"Entrada:\n{input_json}"
    )

    try:
        # Llamada al modelo
        respuesta = ollama.llamar_ollama([
            {"role": "user", "content": prompt}
        ])
        respuesta = ollama.limpiar_respuesta(respuesta)

        # 4. Parsear la respuesta JSON del modelo
        # Buscamos el JSON dentro de la respuesta (por si el modelo agregó texto extra)
        import re
        match = re.search(r'\[.*\]', respuesta, re.DOTALL)
        if match:
            json_str = match.group(0)
            traducciones = json.loads(json_str)
            
            # Validar que la cantidad coincida
            if len(traducciones) == len(textos_a_traducir):
                return jsonify({"translations": traducciones, "lang": lang})
            else:
                print(f"  Error: Cantidad de traducciones no coincide. Esperadas: {len(textos_a_traducir)}, Recibidas: {len(traducciones)}")
                # Si falla, devolvemos los textos originales como fallback
                return jsonify({"translations": textos_a_traducir, "lang": lang})
        else:
            print(f"  El modelo no devolvió un JSON válido: {respuesta[:100]}")
            return jsonify({"translations": textos_a_traducir, "lang": lang})

    except json.JSONDecodeError:
        print("  Error decodificando JSON de traducción")
        return jsonify({"translations": textos_a_traducir, "lang": lang})
    except Exception as e:
        print(f"  Error en traducción por lotes: {e}")
        return jsonify({"error": f"Error en traducción: {e}"}), 500 
        return jsonify({"error": f"Error en traducción por lotes: {e}"}), 500


@bp.route("/api/sucursales", methods=["GET"])
def listar_sucursales():
    return jsonify({"sucursales": [location.sucursal_a_dict(s) for s in SUCURSALES]})


@bp.route("/api/idiomas", methods=["GET"])
def listar_idiomas():
    return jsonify({
        "idiomas": [{"code": c, "nombre": d["nombre"]} for c, d in idiomas.IDIOMAS.items()]
    })


@bp.route("/api/reset", methods=["POST"])
def reset():
    session.limpiar_historial(session.get_sid())
    return jsonify({"ok": True})


@bp.route("/api/status", methods=["GET"])
def status():
    estado_cap = _estado_capacidades()
    return jsonify({
        "status"          : "ok",
        "chunks"          : _rag_chunks_seguro(),
        "modelo"          : os.environ.get("LLM_MODEL", "correos-bot"),
        "ollama"          : ollama.ollama_disponible(),
        "sesiones_activas": session.total_sesiones(),
        "sucursales"      : len(SUCURSALES),
        "idiomas"         : list(idiomas.IDIOMAS.keys()),
        "actualizacion"   : updater.get_estado(),
        "skills"          : estado_cap["skills"],
        "rag"             : estado_cap["rag"],
        "general_only"    : _modo_general_only(),
    })


@bp.route("/api/capabilities", methods=["GET"])
def listar_capacidades():
    return jsonify(_estado_capacidades())


@bp.route("/api/capabilities/options", methods=["GET"])
def listar_opciones_capacidades():
    return jsonify(capabilities.management_options())


@bp.route("/api/pdfs", methods=["GET"])
def listar_pdfs():
    return jsonify({
        "pdfs": capabilities.listar_pdfs(),
        "resumen": capabilities.resumen_pdfs(),
    })


@bp.route("/api/scraping", methods=["GET"])
def scraping_info():
    return jsonify(capabilities.get_scraping_summary())


@bp.route("/api/pdfs/upload", methods=["POST"])
def subir_pdf():
    archivo = request.files.get("file")
    fuente_url = request.form.get("fuente_url", "")
    pagina_fuente = request.form.get("pagina_fuente", "")
    try:
        resultado = capabilities.guardar_pdf_subido(archivo, fuente_url=fuente_url, pagina_fuente=pagina_fuente)
        return jsonify(resultado), 201 if resultado.get("created") else 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Error subiendo PDF: {e}"}), 500


@bp.route("/api/pdfs/<path:nombre_archivo>", methods=["DELETE"])
def eliminar_pdf(nombre_archivo: str):
    try:
        return jsonify(capabilities.eliminar_pdf(nombre_archivo))
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": f"Error eliminando PDF: {e}"}), 500


@bp.route("/api/skills", methods=["GET"])
def listar_skills():
    return jsonify({"skills": _estado_capacidades()["skills"]})


@bp.route("/api/skills", methods=["POST"])
def guardar_skill():
    data = request.get_json(silent=True) or {}
    try:
        resultado = capabilities.guardar_skill(data)
        return jsonify(resultado), 201 if resultado["created"] else 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Error guardando skill: {e}"}), 500


@bp.route("/api/skills/<skill_id>", methods=["DELETE"])
def eliminar_skill(skill_id: str):
    if capabilities.eliminar_skill(skill_id):
        return jsonify({"ok": True, "id": skill_id})
    return jsonify({"error": "Skill no encontrada"}), 404


@bp.route("/api/actualizar", methods=["POST"])
def actualizar():
    if updater.estado["en_proceso"]:
        return jsonify({"ok": False, "mensaje": "  Actualización ya en proceso."}), 409
    updater.disparar_manual(reindexar_fn=reindexar)
    return jsonify({"ok": True, "mensaje": "  Actualización iniciada."})


@bp.route("/api/rag/rebuild", methods=["POST"])
def rebuild_rag():
    try:
        print("  Iniciando rebuild limpio del RAG...")
        exito = reindexar()
        if not exito:
            return jsonify({"ok": False, "error": "No se pudieron indexar documentos en el rebuild limpio del RAG."}), 500
        print(f"  Rebuild limpio del RAG completado ({rag.total_chunks()} chunks).")
        return jsonify({
            "ok": True,
            "mensaje": "Rebuild limpio del RAG completado.",
            "chunks": rag.total_chunks(),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": f"Error en rebuild limpio del RAG: {e}"}), 500


# ─────────────────────────────────────────────
#  COMPATIBILIDAD / API GENÉRICA
# ─────────────────────────────────────────────
# El widget original usaba un único endpoint `/api` con campos
# `action` o `message` para decidir qué hacer. La implementación actual
# ha dividido esto en rutas REST más explícitas, pero mantener un
# manejador genérico ayuda a que integraciones existentes no se rompan.

@bp.route("/api", methods=["GET", "POST"])
def api_root():
    """Ruteador ligero para compatibilidad con versiones antiguas del
    widget y otros clientes que envían `action` en vez de llamar a
    subrutas específicas.

    - GET  /api?action=sucursales  → lista sucursales
    - GET  /api?action=idiomas     → lista de idiomas
    - POST /api {"action":"translate", ...} → translate_bulk
    - POST /api {"action":"reset"}        → reset
    - POST /api {"action":"rebuild_rag"}  → rebuild_rag
    - POST /api {"message":...}            → chat
    """
    if request.method == "GET":
        act = request.args.get("action")
        if act == "sucursales":
            return listar_sucursales()
        if act == "idiomas":
            return listar_idiomas()
        return jsonify({"error": "action no soportada"}), 400

    # POST
    data = request.get_json(silent=True) or {}
    act = data.get("action")
    if act == "translate":
        # el método translate_bulk espera 'lang' y 'texts' opcionales
        return translate_bulk()
    if act == "reset":
        return reset()
    if act == "rebuild_rag":
        return rebuild_rag()
    # si el cuerpo contiene 'message' asumimos chat
    if "message" in data:
        return chat()
    return jsonify({"error": "requisição inválida"}), 400
