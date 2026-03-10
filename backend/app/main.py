"""
main.py
Punto de entrada de ChatbotBO — Agencia Boliviana de Correos.
Ejecutar: python main.py
"""

import os
import sys

# ── Agregar app/ al path para que los imports funcionen
BASE_DIR = os.path.dirname(__file__)
sys.path.insert(0, BASE_DIR)

# ── Cargar variables de entorno desde backend/.env
from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, "..", ".env"))

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

from core import ollama, updater
from chatbots.general import routes as general_routes

# ─────────────────────────────────────────────
#  APP FLASK
# ─────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "correos-agbc-2026")
CORS(app)

# ── Registrar rutas del chatbot general (/api/*)
app.register_blueprint(general_routes.bp)

# ── Directorio del frontend
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "frontend"))


# ─────────────────────────────────────────────
#  RUTAS ESTÁTICAS
# ─────────────────────────────────────────────

@app.route("/")
def index():
    """Sirve la interfaz principal del chatbot."""
    return send_from_directory(FRONTEND_DIR, "chatbot.html")

@app.route("/widget.js")
def widget():
    return send_from_directory(FRONTEND_DIR, "widget.js", mimetype="application/javascript")

@app.route("/widget.css")
def widget_css():
    return send_from_directory(FRONTEND_DIR, "widget.css", mimetype="text/css")

@app.route("/widget.html")
def widget_html():
    return send_from_directory(FRONTEND_DIR, "widget.html", mimetype="text/html")

@app.route("/favicon.ico")
def favicon():
    return send_from_directory(FRONTEND_DIR, "favicon.ico"), 204


# ─────────────────────────────────────────────
#  MANEJO DE ERRORES
# ─────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Ruta no encontrada"}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Error interno del servidor"}), 500


# ─────────────────────────────────────────────
#  INICIALIZACIÓN
# ─────────────────────────────────────────────

def inicializar():
    """
    Inicializa todo antes de arrancar el servidor:
    1. Verifica conexión con Ollama
    2. Carga embeddings y ChromaDB
    3. Indexa datos del scraper (si la BD está vacía)
    4. Inicia el scheduler de actualización automática
    """
    print("\n" + "=" * 50)
    print("   ChatbotBO — Agencia Boliviana de Correos")
    print("=" * 50)

    # 1. Verificar Ollama
    ollama.verificar_ollama()

    # 2. Inicializar chatbot general (RAG + scheduler)
    general_routes.inicializar()

    print("=" * 50)
    print("  Rutas disponibles:")
    print("  GET  /                  → Interfaz del chatbot")
    print("  GET  /widget.js         → Widget embebible")
    print("  GET  /api/welcome       → Mensaje de bienvenida")
    print("  POST /api/chat          → Enviar mensaje")
    print("  POST /api/translate     → Traducir varios textos")
    print("  GET  /api/sucursales    → Lista de sucursales")
    print("  GET  /api/idiomas       → Idiomas disponibles")
    print("  POST /api/reset         → Limpiar historial")
    print("  GET  /api/status        → Estado del sistema")
    print("  POST /api/actualizar    → Forzar actualización")
    print("=" * 50)


# ─────────────────────────────────────────────
#  ARRANQUE
# ─────────────────────────────────────────────

if __name__ == "__main__":
    inicializar()

    PORT  = int(os.environ.get("PORT",  "5000"))
    DEBUG = os.environ.get("DEBUG", "false").lower() == "true"

    print(f"\n🚀 Servidor corriendo en http://localhost:{PORT}")
    print(f"   Debug: {DEBUG}")
    print(f"   Presiona Ctrl+C para detener\n")

    try:
        app.run(
            host  = "0.0.0.0",
            port  = PORT,
            debug = DEBUG,
            use_reloader = False,   # evita doble inicialización en debug
        )
    except KeyboardInterrupt:
        print("\n Deteniendo servidor...")
    finally:
        updater.detener_scheduler()
        print(" Servidor detenido correctamente")
