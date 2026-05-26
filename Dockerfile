# ─────────────────────────────────────────────
#  CHATBOTBO — Dockerfile
#  Base: Python 3.11 slim
# ─────────────────────────────────────────────
FROM python:3.11-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Usar HTTPS en vez de HTTP para evitar bloqueo 403 en la red
RUN sed -i 's|http://|https://|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null; \
    sed -i 's|http://|https://|g' /etc/apt/sources.list 2>/dev/null; \
    true

# Dependencias del sistema
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        git \
        poppler-utils \
        tesseract-ocr \
        tesseract-ocr-spa \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir torch==2.5.1+cpu --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

# Copiar proyecto
COPY . /app

EXPOSE 5000

ENV FLASK_ENV=production \
    PYTHONUNBUFFERED=1 \
    OLLAMA_URL=http://ollama:11434/api/chat \
    LLM_MODEL=correos-bot \
    EMBEDDING_MODEL=intfloat/multilingual-e5-small \
    RERANKER_ENABLED=true \
    RERANKER_MODEL=cross-encoder/mmarco-mMiniLMv2-L12-H384-v1 \
    CHROMA_PATH=/app/chroma_db \
    CHUNK_SIZE=800 \
    BATCH_SIZE=500 \
    N_RESULTADOS=10 \
    OLLAMA_TIMEOUT=600 \
    UVICORN_WORKERS=1 \
    HF_HOME=/tmp/huggingface_cache

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=60s \
  CMD curl -f http://localhost:5000/api/status || exit 1

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port 5000 --workers ${UVICORN_WORKERS:-1}"]
