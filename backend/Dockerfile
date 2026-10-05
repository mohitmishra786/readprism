FROM python:3.12-slim

WORKDIR /app

# Install system deps for Playwright + psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-lite.txt .
# LITE=1 builds the lite profile image (RL-01): requirements-lite.txt is the
# same list minus torch/sentence-transformers (~1.8 GB smaller); the
# embedding service falls back to the deterministic hash embedder.
ARG LITE=0
RUN if [ "$LITE" = "1" ]; then REQ=requirements-lite.txt; else REQ=requirements.txt; fi \
    && pip install --no-cache-dir -r "$REQ"

# Install Playwright browsers
RUN playwright install chromium --with-deps 2>/dev/null || true

COPY . .

ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
