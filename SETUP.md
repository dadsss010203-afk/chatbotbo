# Instrucciones para compilar y ejecutar ChatbotBO

Estas instrucciones permiten a cualquier persona clonar el proyecto, instalar
las dependencias y ejecutar el servidor de ChatbotBO en su máquina Windows
(la mayoría de pasos es similar en macOS/Linux).

## 1. Requisitos previos

1. **Python 3.11+**
   - Descárgalo desde https://www.python.org/downloads/ e instala.
   - Marca "Add Python to PATH" durante la instalación.

2. **Opcional (recomendado)**: Build Tools de Visual Studio
   - Necesario si se quiere compilar paquetes como `chroma-hnswlib`.
   - Se puede instalar con Winget:
     ```powershell
     winget install --id Microsoft.VisualStudio.2022.BuildTools -e
     ```
   - O descargando el instalador desde el sitio de Microsoft y eligiendo
     "Desarrollo de escritorio con C++".

## 2. Clonar el repositorio

```powershell
cd C:\ruta\de\trabajo
git clone <URL-del-repositorio> ChatbotBO
cd ChatbotBO
```

Reemplaza `<URL-del-repositorio>` por la URL real.

## 3. Crear y activar el entorno virtual

```powershell
cd backend\app
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

(en macOS/Linux `source .venv/bin/activate`)

## 4. Instalar dependencias

```powershell
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

Si hay errores al instalar `chroma-hnswlib`, instala las Build Tools.

## 5. Configurar variables de entorno

Crea un fichero `.env` en `backend/app` con este contenido (ajusta a tus
valores):

```
OPENAI_API_KEY=...
HF_TOKEN=...
SUCURSALES_FILE=data/sucursales_contacto.json
```

También puedes exportarlas en el sistema si prefieres.

## 6. Generar los datos con el scraper

```powershell
python scraper/runner.py
```

Esto extraerá texto, secciones, sucursales, historia, noticias y creará los
archivos JSON en `backend/app/data/`.

## 7. Ejecutar el servidor

```powershell
cd backend/app
.\.venv\Scripts\Activate.ps1  # si no está activo
python main.py
```

La API quedará disponible en `http://localhost:5000`.

### Rutas principales

| Ruta               | Método | Descripción                                 |
|--------------------|--------|---------------------------------------------|
| `/api/chat`        | POST   | Pregunta al bot                             |
| `/api/sucursales`  | GET    | Lista de sucursales                         |
| `/api/translate`   | POST   | Traduce texto o conversación                |
| `/api/idiomas`     | GET    | Lista de idiomas disponibles                |
| `/api/reset`       | POST   | Limpia el historial de la sesión            |

## 8. Desarrollo

- Edita los archivos bajo `core/`, `scraper/` o `chatbots/` y reinicia
  `main.py` para ver los cambios.
- Para refrescar los datos, vuelve a ejecutar el scraper.

## Notas adicionales

- Si quieres ejecutar sin entorno virtual, instala las dependencias en el
  Python del sistema y omite los pasos del entorno.
- Guarda la carpeta `data/` y `chroma_db/` si necesitas reproducir resultados.

¡Listo! con estos pasos cualquier persona podrá compilar y ejecutar el
proyecto en su computadora.