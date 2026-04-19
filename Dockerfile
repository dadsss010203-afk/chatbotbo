# ─────────────────────────────────────────────
#  CHATBOTBO — Dockerfile
#  Base: Python 3.11 slim
# ─────────────────────────────────────────────
FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Dependencias del sistema
RUN apt-get update --fix-missing && \
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
    && pip install --no-cache-dir -r requirements.txt

# Copiar proyecto
COPY . /app

EXPOSE 5000

ENV FLASK_ENV=production \
    PYTHONUNBUFFERED=1 \
    OLLAMA_URL=http://ollama:11434/api/chat \
    LLM_MODEL=correos-bot \
    EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2 \
    CHROMA_PATH=/app/chroma_db \
    CHUNK_SIZE=600 \
    BATCH_SIZE=500 \
    N_RESULTADOS=3 \
    OLLAMA_TIMEOUT=600 \
    UVICORN_WORKERS=1

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=60s \
  CMD curl -f http://localhost:5000/api/status || exit 1

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port 5000 --workers ${UVICORN_WORKERS:-1}"]
