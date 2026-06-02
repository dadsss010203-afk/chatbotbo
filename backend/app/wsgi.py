"""WSGI entrypoint para Gunicorn.

Gunicorn importa `application` desde aquí. La inicialización del servicio
se realiza cuando se importa este módulo en cada worker.
"""

from main import app, inicializar

# Inicializar la aplicación cuando Gunicorn importe el módulo.
# Esto permite ejecutar la misma app bajo WSGI en lugar de app.run().
if not getattr(app, "initialized", False):
    inicializar()
    app.initialized = True

application = app
