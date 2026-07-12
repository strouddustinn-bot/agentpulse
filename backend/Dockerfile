FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    AGENTPULSE_BACKEND_DB=/data/agentpulse.db

WORKDIR /app

COPY backend/pyproject.toml /app/pyproject.toml
COPY backend/agentpulse_backend /app/agentpulse_backend

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

VOLUME ["/data"]
EXPOSE 8000

CMD ["uvicorn", "agentpulse_backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
