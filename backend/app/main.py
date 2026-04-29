"""
main.py
Punto de entrada de ChatbotBO — Agencia Boliviana de Correos.
Ejecutar: python main.py
"""

import os
import sys
import time
from collections import defaultdict
from functools import wraps

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
#  RATE LIMITING
# ─────────────────────────────────────────────
# Configuración de rate limiting
RATE_LIMIT_ENABLED = os.environ.get("RATE_LIMIT_ENABLED", "true").lower() in ("1", "true", "yes")
RATE_LIMIT_DEFAULT = int(os.environ.get("RATE_LIMIT_DEFAULT", "60"))  # requests por minuto
RATE_LIMIT_CHAT = int(os.environ.get("RATE_LIMIT_CHAT", "10"))  # requests por minuto para /api/chat
RATE_LIMIT_WINDOW = int(os.environ.get("RATE_LIMIT_WINDOW", "60"))  # ventana en segundos

# Almacén de rate limits: {ip: [(timestamp, count), ...]}
_rate_limit_store = defaultdict(list)
_rate_limit_lock = None  # se inicializa después


def _cleanup_old_requests(ip: str, window: int):
    """Limpia requests antiguos fuera de la ventana de tiempo."""
    now = time.time()
    cutoff = now - window
    _rate_limit_store[ip] = [ts for ts in _rate_limit_store[ip] if ts > cutoff]


def check_rate_limit(ip: str, limit: int, window: int = 60) -> tuple[bool, int, int]:
    """
    Verifica si la IP ha excedido el rate limit.
    Retorna: (permitido, requests actuales, límite)
    """
    if not RATE_LIMIT_ENABLED:
        return True, 0, limit
    
    now = time.time()
    _cleanup_old_requests(ip, window)
    
    current_requests = len(_rate_limit_store[ip])
    
    if current_requests >= limit:
        return False, current_requests, limit
    
    # Registrar nuevo request
    _rate_limit_store[ip].append(now)
    return True, current_requests + 1, limit


# ─────────────────────────────────────────────
#  APP FASTAPI
# ─────────────────────────────────────────────
app = FastAPI(title="ChatbotBO", description="Agencia Boliviana de Correos")
_APP_INITIALIZED = False

@app.on_event("startup")
def startup_event():
    global _rate_limit_lock
    import threading
    _rate_limit_lock = threading.Lock()
    inicializar()


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """
    Middleware de rate limiting por IP.
    Aplica límites diferentes según el endpoint.
    """
    if not RATE_LIMIT_ENABLED:
        return await call_next(request)
    
    # Obtener IP real (considerando proxies)
    ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")
    ip = ip.split(",")[0].strip() if "," in ip else ip
    
    # Determinar límite según el endpoint
    path = request.url.path
    if path == "/api/chat" and request.method == "POST":
        limit = RATE_LIMIT_CHAT
        window = RATE_LIMIT_WINDOW
    elif path.startswith("/api/"):
        limit = RATE_LIMIT_DEFAULT
        window = RATE_LIMIT_WINDOW
    else:
        # Endpoints estáticos no tienen rate limit
        return await call_next(request)
    
    # Verificar rate limit con lock para thread-safety
    import threading
    lock = _rate_limit_lock or threading.Lock()
    with lock:
        allowed, current, max_limit = check_rate_limit(ip, limit, window)
    
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={
                "error": "Rate limit excedido",
                "message": f"Has excedido el límite de {max_limit} requests por minuto. Intenta nuevamente en un momento.",
                "retry_after": window
            },
            headers={
                "X-RateLimit-Limit": str(max_limit),
                "X-RateLimit-Remaining": "0",
                "Retry-After": str(window)
            }
        )
    
    # Procesar request normalmente
    response = await call_next(request)
    
    # Agregar headers informativos
    remaining = max(0, max_limit - current)
    response.headers["X-RateLimit-Limit"] = str(max_limit)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    
    return response


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


@app.get("/widget-embed.js")
async def widget_embed():
    """Widget flotante mejorado para sitios externos."""
    return FileResponse(os.path.join(FRONTEND_DIR, "widget-embed.js"), media_type="application/javascript")


@app.get("/favicon.ico")
async def favicon():
    favicon_path = os.path.join(FRONTEND_DIR, "favicon.ico")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path, media_type="image/x-icon")
    raise HTTPException(status_code=404, detail="Favicon not found")


@app.get("/logo_chatbot.png")
async def logo_chatbot():
    """Sirve el logo del chatbot."""
    logo_path = os.path.join(FRONTEND_DIR, "logo_chatbot.png")
    if os.path.exists(logo_path):
        return FileResponse(logo_path, media_type="image/png")
    raise HTTPException(status_code=404, detail="Logo not found")


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
    global _APP_INITIALIZED
    if _APP_INITIALIZED:
        return

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
    print("  POST /api/chat/stream   → Enviar mensaje (streaming)")
    print("  POST /api/translate     → Traducir varios textos")
    print("  GET  /api/sucursales    → Lista de sucursales")
    print("  GET  /api/idiomas       → Idiomas disponibles")
    print("  POST /api/reset         → Limpiar historial")
    print("  GET  /api/capabilities  → Skills y estado RAG")
    print("  GET  /api/capabilities/options → Opciones para formularios")
    print("  GET  /api/metrics       → Métricas de observabilidad")
    print("  POST /api/tarifa        → Cálculo directo de tarifa")
    print("  GET  /api/skills        → Lista de skills")
    print("  POST /api/skills        → Crear o actualizar skill")
    print("  DELETE /api/skills/<id> → Eliminar skill")
    print("  POST /api/rag/rebuild   → Rebuild limpio del RAG")
    print("  GET  /api/status        → Estado del sistema")
    print("  POST /api/actualizar    → Forzar actualización")
    print("  POST /api/escalate      → Escalar a agente humano")
    print("  GET  /api/escalation/tickets → Tickets pendientes")
    print("  POST /api/sucursal/cercana → Sucursal más cercana (GPS)")
    print("  GET  /widget-embed.js   → Widget flotante mejorado")
    print("=" * 50)
    _APP_INITIALIZED = True


# ─────────────────────────────────────────────
#  ARRANQUE
# ─────────────────────────────────────────────

if __name__ == "__main__":
    inicializar()

    PORT  = int(os.environ.get("PORT",  "5000"))
    DEBUG = os.environ.get("DEBUG", "true").lower() == "true"

    print(f"\n🚀 Servidor corriendo en http://localhost:{PORT}")
    print(f"   Debug: {DEBUG}")
    print(f"   Presiona Ctrl+C para detener\n")

    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=PORT,
        reload=False,
        log_level="info",
    )
