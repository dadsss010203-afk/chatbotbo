# Ultimos Cambios MCP, Skills y RAG

Fecha base del trabajo: 31/03/2026

## Resumen general

Se incorporo una capa de capacidades para el chatbot con soporte para:

- listado y ejecucion de MCPs internos
- listado de skills disponibles
- inspeccion del estado real del RAG
- botones rapidos en la interfaz del chatbot y del widget
- nuevas rutas API para consultar capacidades del bot

## Cambios en backend

### 1. Capa de capacidades

Se creo el archivo `backend/app/core/capabilities.py` con:

- catalogo de skills
- catalogo de MCPs
- construccion de capacidades en tiempo real
- deteccion de consultas especiales como `skills`, `mcps`, `rag`
- ejecucion de MCPs internos:
  - `rag_local`
  - `system_status`
  - `branches_summary`

### 2. Integracion real en el blueprint activo

Se actualizo `backend/app/chatbots/general/routes.py` para:

- conectar `capabilities.py` al flujo del chat
- responder consultas especiales sin depender del LLM
- exponer nuevas rutas:
  - `GET /api/capabilities`
  - `GET /api/mcps`
  - `GET /api/skills`
  - `POST /api/mcps/execute`
- ampliar `GET /api/status` con datos de:
  - `skills`
  - `mcps`
  - `rag`

### 3. Catalogos de datos

Se agregaron y alinearon estos archivos:

- `backend/app/data/skills.json`
- `backend/app/data/mcps.json`

Estos archivos publican los catalogos visibles desde la API y el chat.

### 4. Ajuste de arranque

Se actualizo `backend/app/main.py` para mostrar en consola las nuevas rutas disponibles.

## Cambios en frontend

### 1. Chat principal

Se modifico `frontend/chatbot.html` para agregar botones rapidos:

- Generar
- MCPs
- Skills
- Analizar RAG

Tambien se agrego la logica `quickAction(...)` para enviar estas consultas al backend.

### 2. Widget

Se modificaron:

- `frontend/widget.html`
- `frontend/widget.css`
- `frontend/widget.js`

Con los mismos botones rapidos y su comportamiento asociado.

## Validaciones realizadas

Se verifico:

- compilacion Python con `py_compile`
- presencia de rutas nuevas en el blueprint correcto
- ejecucion de MCPs internos desde la capa `capabilities`

## Problema detectado y corregido

Inicialmente los endpoints nuevos se habian agregado en `backend/app/core/routes.py`, pero Flask registraba realmente `backend/app/chatbots/general/routes.py`.

Se corrigio moviendo la implementacion al blueprint activo.

## Estado final esperado

Despues de reiniciar el contenedor `chatbot`, deben responder correctamente:

- `GET /api/status`
- `GET /api/capabilities`
- `GET /api/mcps`
- `GET /api/skills`
- `POST /api/mcps/execute`

## Archivos mas importantes tocados

- `.gitignore`
- `ULTIMOS_CAMBIOS_MCP_SKILLS_RAG.md`
- `backend/app/core/capabilities.py`
- `backend/app/chatbots/general/routes.py`
- `backend/app/main.py`
- `backend/app/data/skills.json`
- `backend/app/data/mcps.json`
- `frontend/chatbot.html`
- `frontend/widget.html`
- `frontend/widget.css`
- `frontend/widget.js`
