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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "core"))

import requests
import json
from flask import Blueprint, request, jsonify

from core import rag, ollama, session, location, idiomas, intents, updater, capabilities
from chatbots.general.config import (
    NOMBRE, CHROMA_PATH, DATA_FILE, SUCURSALES_FILE, SECCIONES_FILE,
    construir_prompt,
)

# ─────────────────────────────────────────────
#  BLUEPRINT
# ─────────────────────────────────────────────
bp = Blueprint("general", __name__)   # sin prefix → rutas en /api/*

SUCURSALES: list = []


def _estado_capacidades() -> dict:
    return capabilities.get_runtime_capabilities(
        chunks=rag.total_chunks(),
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
    chunks, ids = [], []

    # 1. Texto principal (HTML plano acumulado)
    c, i = rag.archivo_a_chunks(DATA_FILE, prefijo="txt")
    chunks += c; ids += i

    # 2. Sucursales
    SUCURSALES = location.cargar_sucursales(SUCURSALES_FILE)
    for idx, s in enumerate(SUCURSALES):
        chunks.append(location.sucursal_a_texto(s))
        ids.append(f"suc_{idx}")

    # 3. Secciones del home
    c, i = location.cargar_secciones(SECCIONES_FILE)
    chunks += c; ids += i

    # 4. Contenido de PDFs (si existe el JSON generado por el scraper)
    try:
        pdf_path = os.path.join(os.path.dirname(DATA_FILE), "pdfs_contenido.json")
        if os.path.exists(pdf_path):
            with open(pdf_path, "r", encoding="utf-8") as f:
                pdfs = json.load(f)
            for idx, p in enumerate(pdfs):
                texto = p.get("texto_extraido") or ""
                if texto:
                    chunks.append(texto)
                    ids.append(f"pdf_{idx}")
    except Exception as e:
        print(f"   Error leyendo PDF JSON: {e}")

    return rag.indexar(chunks, ids)


# ─────────────────────────────────────────────
#  INICIALIZACIÓN
# ─────────────────────────────────────────────

def inicializar():
    """Llamar desde main.py al arrancar la app."""
    global SUCURSALES
    print(f"\n🤖 Iniciando {NOMBRE}...")

    rag.inicializar(chroma_path=CHROMA_PATH, collection_name="general")

    if rag.total_chunks() == 0:
        print("  BD vacía → indexando datos del scraper...")
        reindexar()
    else:
        print(f" BD lista ({rag.total_chunks()} chunks)")
        SUCURSALES = location.cargar_sucursales(SUCURSALES_FILE)

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

    # ── 6. Consulta general → RAG + Ollama
    try:
        contexto = rag.buscar(pregunta)
    except Exception as e:
        return jsonify({"error": f"Error en búsqueda RAG: {e}"}), 500

    hora     = session.get_hora_bolivia()
    sistema  = construir_prompt(t["instruccion"], contexto, hora, t["sin_info"])
    mensajes = [
        {"role": "system", "content": sistema},
        *session.historial_reciente(sid),
        {"role": "user",   "content": pregunta},
    ]

    try:
        print(f" [{lang}] {pregunta[:60]}")
        respuesta = ollama.llamar_ollama(mensajes)
        respuesta = ollama.limpiar_respuesta(respuesta)

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
        return jsonify({"response": respuesta, "lang": lang})

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
        "chunks"          : rag.total_chunks(),
        "modelo"          : os.environ.get("LLM_MODEL", "correos-bot"),
        "ollama"          : ollama.ollama_disponible(),
        "sesiones_activas": session.total_sesiones(),
        "sucursales"      : len(SUCURSALES),
        "idiomas"         : list(idiomas.IDIOMAS.keys()),
        "actualizacion"   : updater.get_estado(),
        "skills"          : estado_cap["skills"],
        "rag"             : estado_cap["rag"],
    })


@bp.route("/api/capabilities", methods=["GET"])
def listar_capacidades():
    return jsonify(_estado_capacidades())


@bp.route("/api/skills", methods=["GET"])
def listar_skills():
    return jsonify({"skills": _estado_capacidades()["skills"]})


@bp.route("/api/actualizar", methods=["POST"])
def actualizar():
    if updater.estado["en_proceso"]:
        return jsonify({"ok": False, "mensaje": "  Actualización ya en proceso."}), 409
    updater.disparar_manual(reindexar_fn=reindexar)
    return jsonify({"ok": True, "mensaje": "  Actualización iniciada."})
