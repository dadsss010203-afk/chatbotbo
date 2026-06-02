# ─────────────────────────────────────────────
#  CHATBOTBO — Dockerfile
#  Base: Python 3.11 slim
#  Las variables de entorno se configuran en docker-compose.yml
#  Los valores aqui son solo fallback para desarrollo local sin compose.
# ─────────────────────────────────────────────
FROM python:3.11-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Usar HTTPS para repositorios Debian para evitar bloqueos HTTP 403
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true; \
    sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list 2>/dev/null || true; \
    apt-get update --fix-missing && \
    apt-get install -y --no-install-recommends --fix-missing \
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

# Solo fallback para dev local — docker-compose.yml sobreescribe todo
ENV PYTHONUNBUFFERED=1 \
    OLLAMA_URL=http://localhost:11434/api/chat \
    RAG_VECTOR_STORE=qdrant \
    QDRANT_URL=http://localhost:6333 \
    LLM_MODEL=correos-bot \
    EMBEDDING_MODEL=intfloat/multilingual-e5-small \
    CHROMA_PATH=/app/chroma_db \
    HF_HOME=/tmp/huggingface_cache

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=60s \
  CMD curl -f http://localhost:5000/api/status || exit 1

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port 5000 --workers ${UVICORN_WORKERS:-1}"]
