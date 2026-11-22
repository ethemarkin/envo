# Envo in one image: the API and the dashboard served by the same process.
#
#   docker build -t earkin/envo .
#
# Runtime configuration comes from environment variables (see
# backend/.env.example). TLS is terminated by the reverse proxy in front.

# --- Dashboard -----------------------------------------------------------------
FROM node:22-bookworm-slim AS frontend
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- API + dashboard ---------------------------------------------------------
FROM python:3.13-slim

ARG VERSION=dev
LABEL org.opencontainers.image.title="envo" \
      org.opencontainers.image.description="Envo: environment variables and secrets for teams" \
      org.opencontainers.image.version="$VERSION"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ENVO_STATIC_DIR=/app/static

WORKDIR /app
COPY backend/pyproject.toml ./
COPY backend/app ./app
RUN pip install --no-compile .

COPY backend/alembic.ini ./
COPY backend/migrations ./migrations
COPY --from=frontend /src/dist ./static

RUN useradd --create-home --uid 10001 envo
USER envo

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"]

# Migrations run on start; uvicorn trusts X-Forwarded-* only from
# FORWARDED_ALLOW_IPS (set it to the reverse proxy's address).
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
