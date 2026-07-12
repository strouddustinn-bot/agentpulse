FROM node:22-bookworm-slim AS web-build
WORKDIR /build
COPY dashboard/web/package.json dashboard/web/package-lock.json ./
RUN npm ci
COPY dashboard/web/ ./
RUN npm run build

FROM python:3.13-slim AS python-base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080
WORKDIR /app
COPY dashboard/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY dashboard/pulse_server/ ./pulse_server/

FROM python-base AS backend-test
RUN pip install --no-cache-dir httpx2
COPY dashboard/tests/ ./tests/
RUN python -m unittest discover -s tests -v && touch /tests-passed

FROM python-base AS runtime
COPY --from=backend-test /tests-passed /tests-passed
COPY --from=web-build /build/dist ./web/dist/
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn pulse_server.main:app --host 0.0.0.0 --port ${PORT}"]
