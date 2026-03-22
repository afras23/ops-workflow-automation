# Multi-stage build — builder installs deps, final image stays lean
FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim
WORKDIR /app

# Non-root user for security
RUN useradd --create-home --shell /bin/bash appuser

COPY --from=builder /install /usr/local

COPY app/ ./app/
COPY schemas/ ./schemas/
COPY alembic.ini ./
COPY migrations/ ./migrations/

# SQLite data directory — mount as a volume to persist across restarts
RUN mkdir -p data && chown appuser:appuser data

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')"

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
