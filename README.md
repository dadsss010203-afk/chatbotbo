# ChatbotBO

ChatbotBO es un asistante virtual completo para la Agencia Boliviana de Correos (AGBC). Está diseñado como un bot híbrido que combina:

- Respuestas conversacionales con **Ollama**.
- Recuperación semántica documental con **RAG** (Qdrant / ChromaDB).
- Cache y orquestación con **Redis**.
- Procesamiento en segundo plano con **Celery**.
- API REST con **FastAPI**.
- Frontend ligero en HTML/JS para chat, widget y panel de gestión.

---

## 1. Resumen del proyecto

Este repositorio contiene:

- `backend/app`: backend principal con FastAPI, Celery y la lógica del chatbot.
- `docker-compose.yml`: define los servicios Docker necesarios.
- `Dockerfile`: construye la imagen Python usada por los contenedores backend.
- `frontend`: interfaz del chatbot, widget embebible y panel de capacidades.
- `backend/app/core`: motor RAG, cliente Ollama, cache Redis, scheduler, manejo de skills y tarifas.
- `backend/app/chatbots/general`: lógica de rutas, prompts, traducción, detección de intenciones y flujo de conversación.
- `backend/app/data`: datos generados por el scraper que alimentan el RAG y el chatbot.
- `backend/app/skills`: skill wrappers para la lógica de tarifas.

---

## 2. Arquitectura general

### 2.1 Servicios principales

- `ollama`: servidor de modelo de lenguaje local.
- `ollama-setup`: contenedor auxiliar que descarga y crea el modelo `correos-bot`.
- `redis`: broker/result backend de Celery y cache de respuesta/embeddings.
- `qdrant`: vector store para búsqueda semántica.
- `chatbot`: backend FastAPI.
- `celery_worker`: worker Celery para tareas de mantenimiento y cálculos pesados.

### 2.2 Flujo de solicitud de chat

1. El cliente envía `POST /api/chat` con `message`, `lang` y opcionalmente `sid`.
2. El backend resuelve la sesión con `session.get_sid()` o usa `X-Session-Id`.
3. Detecta el idioma con `core/idiomas.py` y normaliza la petición.
4. Revisa reglas rápidas: saludos, despedidas, ubicaciones, consultas fuera de scope, consultas especiales.
5. Si hay skill detectada, resuelve el `primary_skill` mediante `core/capabilities.resolve_skills_for_query()`.
6. Si procede, busca contexto RAG con `core/rag.buscar()` y construye un prompt con `chatbots/general/config.py`.
7. Llama a Ollama para generar la respuesta y aplica postprocesamiento.
8. Si la respuesta es apta, se cachea en Redis y se guarda el turno en memoria.

---

## 3. Cómo funciona el RAG

### 3.1 `backend/app/core/rag.py`

Este módulo implementa:

- Carga de embeddings con `SentenceTransformer`.
- Inicialización de colecciones en Qdrant o ChromaDB.
- Segmentación de texto en chunks semánticos.
- Indexado de chunks con metadatos.
- Búsqueda semántica y ranking final.

### 3.2 Chunking y normalización

El pipeline de chunking hace:

- Limpia saltos de línea y ruido de scraping/PDF.
- Divide texto por párrafos, encabezados y etiquetas.
- Usa solapamiento (`overlap`) para mantener coherencia.
- Omite fragments muy pequeños.
- Deduplica por hash SHA-1 corto.

### 3.3 Indexado

- `documento_a_chunks()` convierte cualquier texto en chunks.
- `indexar()` crea embeddings y los inserta en Qdrant o Chroma.
- `reemplazar_por_source_type()` permite reindexar solo un `source_type` (por ejemplo, PDFs).

### 3.4 Búsqueda

- `buscar()` calcula el embedding de la pregunta.
- Preferencia de fuentes con `preferred_source_types`.
- Realiza cache de embedding (`cache.get_embedding`) y cache de resultados RAG (`cache.get_rag_search`).
- Usa Qdrant si `RAG_VECTOR_STORE=qdrant`, o Chroma si `RAG_VECTOR_STORE=chroma`.
- Calcula un ranking combinado con prioridades de fuente, penalizaciones de longitud y coincidencia de tipo.
- Devuelve:
  - `context`: texto concatenado para el prompt.
  - `sources`: lista de fuentes con `source_type`, `label`, `source_name`, `source_path`.
  - `primary_source_type`.

---

## 4. Diseño de cache Redis

### 4.1 `backend/app/core/cache.py`

Redis se usa para:

- **Embeddings**: cachea vectores generados para preguntas repetidas.
- **Búsquedas RAG**: guarda resultados de búsqueda para preguntas similares.
- **Respuestas finales**: evita volver a llamar a Ollama para la misma pregunta/skill/idioma.
- **Cálculos de tarifas**: memoiza consultas de tarifa.

### 4.2 Namespace de keys

- `emb:<hash>` → embedding serializado con pickle.
- `rag:<hash>` → resultado de búsqueda RAG JSON.
- `resp:<hash>` → respuesta final JSON.
- `tariff:<hash>` → resultado de tarifa JSON.

### 4.3 Filtros de cache

Las variables de entorno deciden qué partes cachear:

- `REDIS_EMBEDDING_CACHE`
- `REDIS_TARIFF_CACHE`
- `REDIS_RESPONSE_CACHE`
- `REDIS_RESPONSE_CACHE_TTL`

### 4.4 Salud y limpieza

El cache incluye funciones para:

- listar estados y métricas.
- limpiar respuestas específicas.
- limpiar patrones completos.

---

## 5. Control de sesión y `tarifa_flow`

### 5.1 `backend/app/core/session.py`

El backend mantiene sesiones en memoria con TTL y límite.

Funciones clave:

- `get_sid()` crea/retorna un UUID de sesión.
- `get_historial(sid)` devuelve el historial de conversación.
- `agregar_turno(sid, pregunta, respuesta)` mantiene un historial limitado.
- `historial_reciente(sid)` regresa mensajes recientes para el prompt.
- `total_sesiones()` cuenta sesiones activas.

### 5.2 Flujo de cotización postal

- `start_tarifa_flow()` inicia un flujo de tarifas en la sesión.
- `set_pendiente_tarifa()` guarda estado intermedio de campos faltantes.
- `append_tarifa_flow_turn()` registra pasos del diálogo de tarifa.
- `pop_tarifa_flow()` cierra el flujo y devuelve la traza.

El modo tarifas permite manejar consultas en múltiples mensajes y reintentos.

---

## 6. Skills y resolución de intención

### 6.1 `backend/app/core/capabilities.py`

Este módulo administra:

- catálogo de skills configurables en `data/skills.json`.
- detección de `primary_skill` mediante triggers y palabras clave.
- respuestas fuera de scope.
- prioridades y filtros de fuentes RAG.
- endpoints de gestión de skills, PDFs y datos JSON.

### 6.2 Detección de skill

`resolve_skills_for_query()`:

- normaliza el texto de la pregunta.
- compara contra `trigger_tokens` y `trigger_words` de cada skill.
- suma puntajes especiales para skills relevantes.
- retorna `primary_skill`, `matched_skills`, `skill_ids` y si está `in_scope`.

### 6.3 Fuentes preferidas

`preferred_sources_for_skill()` retorna el orden de prioridad RAG según el skill:

- `oficinas_contacto`: `branch`, `web_main`, `section`, `history`, `json_data`.
- `historia_correos_bolivia`, `filatelia_boliviana`: `pdf`, `history`, `json_data`, `section`.
- otros skills de atención usan una mezcla de `pdf`, `web_main`, `section`, `json_data`, `branch`.

### 6.4 Consultas especiales

`detectar_consulta_especial()` intercepta preguntas sobre:

- `skills`
- `rag`
- `estado del sistema`
- `capacidades del bot`
- generación / qué puede hacer

Si detecta esto, la respuesta se genera internamente sin pasar por RAG+LLM normal.

---

## 7. Lógica de tarifas postales

### 7.1 `backend/app/core/tarifas_skill.py`

Administra las consultas de tarifa con varios tipos de servicio:

- EMS Nacional / Internacional
- Encomienda Prioritario Nacional / Internacional
- LC/AO Nacional / Internacional
- ECA Nacional / Internacional
- Pliegos Nacional / Internacional
- Sacas M Nacional / Internacional
- EMS Contratos Nacional
- Super Express Nacional / Internacional

### 7.2 Skills de cálculo

Cada scope usa un wrapper shell ubicado en `backend/app/skills/skillX/tools/calcular_hojaY_json.sh`.

Los wrappers leen parámetros de peso, destino/columna y generan resultados JSON.

### 7.3 Orquestación híbrida

- El bot puede usar LLM para entender intención y extraer campos.
- El cálculo final se hace determinísticamente con `ejecutar_tarifa()` y los wrappers.
- En el modo `tarifa_mode` o `TARIFF_DETERMINISTIC_ONLY=true`, el backend fuerza este flujo.

### 7.4 Reconocimiento de campos

`parse_tarifa_request()` extrae de la pregunta:

- `scope`
- `peso`
- `columna`
- `family`
- `nivel`

Y se valida con mensajes de error claros.

---

## 8. Endpoints API detallados

### 8.1 Rutas públicas

- `GET /` → `frontend/chatbot.html`
- `GET /gestion/capacidades` → `frontend/capacidades.html`
- `GET /widget.js` → script widget embebible
- `GET /widget.css` → estilos del widget
- `GET /widget.html` → página embebible

### 8.2 API principal

#### `GET /api/welcome`

- Retorna saludo según idioma.
- Query param: `lang` (ej: `es`, `en`, `fr`).

#### `POST /api/chat`

- Body JSON mínimo:
  - `message`: texto del usuario.
  - `lang`: opcional, idioma forzado.
  - `tarifa_mode`: opcional, booleano.
  - `sid`: opcional, session id.

- Respuesta:
  - `response`
  - `lang`
  - `sid`
  - `skill_resolution`
  - `sources`
  - `primary_source_type`
  - `cache_hit`

#### `POST /api/translate`

- Traduce textos.
- Payload esperado: `lang` y opcionalmente `texts`.
- Si no hay `texts`, reconstruye desde la sesión.
- Usa `chatbots/general/translation_service.py`.

#### `GET /api/sucursales`

- Lista de sucursales cargadas desde `data/sucursales_contacto.json`.

#### `GET /api/idiomas`

- Retorna idiomas habilitados.

#### `POST /api/reset`

- Limpia historial y estado de tarifa de la sesión.

#### `GET /api/status`

- Estado general del bot:
  - cantidad de chunks RAG
  - modelo activo
  - estado Ollama
  - sesiones activas
  - número de sucursales
  - idiomas
  - estado de actualización
  - skills y estado RAG
  - si `CHATBOT_GENERAL_ONLY` está activo

#### `GET /api/metrics`

- Snapshot de observabilidad.

#### `GET /api/capabilities`

- Estado runtime y capacidades del bot.

#### `GET /api/capabilities/options`

- Opciones y metadatos para la UI de administración.

#### Cache y logs

- `GET /api/cache/stats`
- `GET /api/cache/responses`
- `DELETE /api/cache/responses/{cache_id}`
- `POST /api/cache/responses/clear`

- `GET /api/conversations`
- `GET /api/conversations/tarifas`
- `DELETE /api/conversations/{log_id}`
- `DELETE /api/conversations/tarifas/{log_id}`
- `POST /api/conversations/clear`
- `PUT /api/conversations/{log_id}/rating`

#### PDFs y JSON de datos

- `GET /api/pdfs`
- `GET /api/data-jsons`
- `GET /api/data-jsons/{nombre_archivo}`
- `PUT /api/data-jsons/{nombre_archivo}`
- `GET /api/scraping`
- `POST /api/pdfs/upload`
- `DELETE /api/pdfs/{nombre_archivo}`
- `PUT /api/pdfs/{nombre_archivo}`

#### Skills

- `GET /api/skills`
- `POST /api/skills`
- `DELETE /api/skills/{skill_id}`

#### Actualización y RAG

- `POST /api/actualizar` → encola actualización con `run_update_task`.
- `POST /api/rag/rebuild` → encola reconstrucción completa del RAG con `rebuild_rag_task`.

#### Tarifas

- `POST /api/tarifa` → cálculo determinístico de tarifa.
- `POST /api/tarifa/start` → inicia el flujo guiado de tarifa.
- `POST /api/tarifa/cancel` → cancela el flujo de tarifa.

### 8.3 Compatibilidad antigua

También existe un endpoint genérico `POST /api` que actúa como proxy para compatibilidad con integraciones anteriores.

---

## 9. Datos y scraper

### 9.1 Archivos generados

- `data/correos_bolivia.txt`: texto principal usado por RAG.
- `data/sucursales_contacto.json`: sucursales y datos de contacto.
- `data/secciones_home.json`: secciones de la web.
- `data/historia_institucional.json`: historia institucional.
- `data/pdfs_contenido.json`: texto extraído de PDFs.
- `data/skills.json`: catálogo de skills.
- `data/estadisticas.json`: métricas del scraper.
- `data/aplicativos_detalle.json`: detalles de aplicativos.
- `data/enlaces_interes.json`: enlaces.
- `data/pdfs_descargados/`: PDFs originales.

### 9.2 Scraper

El scraper vive en `backend/app/scraper/` y genera los datos anteriores.
Se ejecuta desde `scraper/runner.py`.

### 9.3 PDF manual y reindexación

- Se pueden subir PDFs con `/api/pdfs/upload`.
- Se puede editar texto extraído manualmente.
- Después de cambios, el endpoint inicia un reindexado diferido.

---

## 10. Docker y despliegue

### 10.1 Ejecución recomendada

```bash
cd /home/lider/Escritorio/Datos/docker/chatbotbo-main
docker compose up --build
```

### 10.2 Servicios expuestos

- `5000` → backend FastAPI.
- `11434` → Ollama.
- `6333` → Qdrant.
- `6379` → Redis.

### 10.3 Variables de entorno relevantes

| Variable | Descripción | Default |
|---|---|---|
| `OLLAMA_URL` | URL de Ollama | `http://ollama:11434/api/chat` |
| `LLM_MODEL` | Modelo de Ollama | `correos-bot` |
| `OLLAMA_TIMEOUT` | Timeout para llamadas Ollama | `240` |
| `OLLAMA_NUM_PREDICT` | Tokens de salida máximo | `120` |
| `OLLAMA_RETRIES` | Reintentos Ollama | `1` |
| `EMBEDDING_MODEL` | Modelo sentence-transformers | `paraphrase-multilingual-MiniLM-L12-v2` |
| `RAG_VECTOR_STORE` | `qdrant` o `chroma` | `qdrant` |
| `QDRANT_URL` | URL de Qdrant | `http://qdrant:6333` |
| `REDIS_URL` | URL de Redis | `redis://redis:6379/0` |
| `REDIS_CACHE_TTL` | TTL general | `3600` |
| `REDIS_EMBEDDING_CACHE` | `true/false` | `true` |
| `REDIS_RESPONSE_CACHE` | `true/false` | `true` |
| `CHROMA_PATH` | Ruta local de ChromaDB | `/app/chroma_db` |
| `CHUNK_SIZE` | Tamaño chunk RAG | `600` |
| `BATCH_SIZE` | Batch embeddings | `500` |
| `N_RESULTADOS` | Resultados RAG | `2` (app) / `3` (worker) |
| `CHATBOT_GENERAL_ONLY` | Solo modo local sin RAG | `false` |
| `REQUIRE_EVIDENCE` | Exigir evidencia literal | `false` |
| `HORAS_ACTUALIZACION` | Intervalo de actualización automática | `24` |
| `MAX_HISTORIAL` | Mensajes de historial en prompt | `3` |
| `SESSION_TTL_MINUTES` | Expiración de sesión | `180` |

### 10.4 Nota Triton

El proyecto puede configurarse para usar Triton con `USE_TRITON=true`, pero en la configuración por defecto no está activado.

---

## 11. Ejecución local sin Docker

```bash
cd backend/app
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

Si usas `.env`, colócalo en `backend/app/.env`.

---

## 12. Desarrollo y mantenimiento

### 12.1 Principales carpetas de desarrollo

- `backend/app/main.py`: arranque del servidor.
- `backend/app/celery_app.py`: configuración Celery.
- `backend/app/tasks.py`: tareas asíncronas.
- `backend/app/core/rag.py`: RAG e indexado.
- `backend/app/core/ollama.py`: cliente Ollama.
- `backend/app/core/cache.py`: cache Redis.
- `backend/app/core/updater.py`: scraper y scheduler.
- `backend/app/core/session.py`: estado de sesión.
- `backend/app/core/capabilities.py`: skills y administración.
- `backend/app/core/tarifas_skill.py`: cálculo de tarifas.
- `backend/app/chatbots/general/routes.py`: rutas de API, prompts y flujo de chat.
- `frontend/`: interfaz de usuario.

### 12.2 Recomendaciones

- Después de cambios en datos o PDFs, ejecuta `POST /api/rag/rebuild`.
- Si el bot no responde bien, revisa si `ollama` está disponible en `OLLAMA_URL`.
- Mantén los volúmenes `redis_data`, `qdrant_data` y `ollama_data` para persistencia.
- Ajusta `CHUNK_SIZE`, `BATCH_SIZE` y `N_RESULTADOS` progresivamente según capacidad de la máquina.

### 12.3 Áreas de mejora identificadas

- El sistema de skills está basado en coincidencias por trigger estático.
- El backend puede saturar memoria si hay muchas sesiones activas sin purgar.
- Los wrappers de tarifas son scripts shell externos; su mantenimiento depende de `backend/app/skills/skill*/tools`.

---

## 13. Referencias de implementación clave

- `chatbots/general/config.py` construye el prompt del sistema y las reglas de evidencia.
- `chatbots/general/chat_helpers.py` ofrece búsqueda local mínima y validación de citas.
- `core/idiomas.py` detecta idioma y devuelve frases multilingües.
- `core/session.py` guarda historial, TTL y estados de tarifa.
- `core/capabilities.py` administra catalogo de skills, JSON de datos y metadata.
- `core/updater.py` ejecuta scraper y reindexa periódicamente.

---

> Este README documenta con detalle la implementación actual. Si quieres, puedo también generar un diagrama de arquitectura y un ejemplo de payloads JSON para cada endpoint. 
