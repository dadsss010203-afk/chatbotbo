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

# ── Cargar variables de entorno priorizando backend/app/.env
from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, ".env"))
load_dotenv(os.path.join(BASE_DIR, "..", ".env"), override=False)

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from core import ollama, updater, observability
from chatbots.general import routes as general_routes

# ─────────────────────────────────────────────
#  APP FASTAPI
# ─────────────────────────────────────────────
app = FastAPI(title="ChatbotBO", description="Agencia Boliviana de Correos")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
observability.init_app(app)

# ── Registrar rutas del chatbot general (/api/*)
app.include_router(general_routes.router)

# ── Directorio del frontend
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "frontend"))


# ─────────────────────────────────────────────
#  RUTAS ESTÁTICAS
# ─────────────────────────────────────────────

@app.get("/")
async def index():
    """Sirve la interfaz principal del chatbot."""
    return FileResponse(os.path.join(FRONTEND_DIR, "chatbot.html"), media_type="text/html")


@app.get("/gestion/capacidades")
@app.get("/gestion/capacidades/{path:path}")
async def gestion_capacidades(path: str = None):
    """Sirve el panel de gestion de skills, PDFs y recursos del bot."""
    return FileResponse(os.path.join(FRONTEND_DIR, "capacidades.html"), media_type="text/html")


@app.get("/widget.js")
async def widget():
    return FileResponse(os.path.join(FRONTEND_DIR, "widget.js"), media_type="application/javascript")


@app.get("/widget.css")
async def widget_css():
    return FileResponse(os.path.join(FRONTEND_DIR, "widget.css"), media_type="text/css")


@app.get("/widget.html")
async def widget_html():
    return FileResponse(os.path.join(FRONTEND_DIR, "widget.html"), media_type="text/html")


@app.get("/favicon.ico")
async def favicon():
    return FileResponse(os.path.join(FRONTEND_DIR, "favicon.ico"), media_type="image/x-icon")


# ─────────────────────────────────────────────
#  MANEJO DE ERRORES
# ─────────────────────────────────────────────

@app.exception_handler(404)
async def not_found(request: Request, exc: HTTPException):
    return JSONResponse(status_code=404, content={"error": "Ruta no encontrada"})


@app.exception_handler(500)
async def server_error(request: Request, exc: HTTPException):
    return JSONResponse(status_code=500, content={"error": "Error interno del servidor"})


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
    print("  GET  /gestion/capacidades → Panel de gestion")
    print("  GET  /widget.js         → Widget embebible")
    print("  GET  /api/welcome       → Mensaje de bienvenida")
    print("  POST /api/chat          → Enviar mensaje")
    print("  POST /api/translate     → Traducir varios textos")
    print("  GET  /api/sucursales    → Lista de sucursales")
    print("  GET  /api/idiomas       → Idiomas disponibles")
    print("  POST /api/reset         → Limpiar historial")
    print("  GET  /api/capabilities  → Skills y estado RAG")
    print("  GET  /api/capabilities/options → Opciones para formularios")
    print("  GET  /api/metrics       → Métricas de observabilidad")
    print("  POST /api/tarifa        → Cálculo directo de tarifa Hoja 1")
    print("  GET  /api/skills        → Lista de skills")
    print("  POST /api/skills        → Crear o actualizar skill")
    print("  DELETE /api/skills/<id> → Eliminar skill")
    print("  POST /api/rag/rebuild   → Rebuild limpio del RAG")
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

    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=PORT,
        reload=DEBUG,
        log_level="info" if DEBUG else "warning",
    )
