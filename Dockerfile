FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y \
    gcc libpq-dev libjpeg-dev zlib1g-dev libpng-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY frontend/ ./frontend/
COPY cleanclaw_main.py .
COPY database/ ./database/

RUN adduser --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser

EXPOSE 8003

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=5 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://localhost:{os.getenv(\"PORT\",\"8003\")}/health')"

CMD ["sh", "-c", "uvicorn cleanclaw_main:app --host 0.0.0.0 --port ${PORT:-8003}"]
