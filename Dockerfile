# syntax=docker/dockerfile:1
#
# Production Multi-stage Container for Fullstack Deployment (Render, Cloud Run, Hugging Face, etc.)
# Stage 1: Build React/Vite Frontend
# Stage 2: Build Python Backend Virtualenv with uv
# Stage 3: Minimal, secure non-root runtime container

# ---------------------------------------------------------------------------
# Stage 1: Frontend Builder
# ---------------------------------------------------------------------------
FROM node:22-slim AS frontend-builder

WORKDIR /build/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2: Python Backend Builder
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS backend-builder

RUN pip install --no-cache-dir uv==0.8.13

WORKDIR /code

# Install dependencies first for Docker layer caching
COPY pyproject.toml README.md uv.lock* ./
RUN uv sync --frozen --no-install-project --no-dev

# Install app code
COPY src ./src
COPY app.py ./app.py
RUN uv sync --frozen --no-dev

# ---------------------------------------------------------------------------
# Stage 3: Production Runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim

WORKDIR /code

RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /code/data /code/frontend/dist \
    && chown -R appuser:appuser /code

# Copy Python virtualenv and backend code
COPY --from=backend-builder --chown=appuser:appuser /code /code

# Copy built frontend assets so FastAPI serves the SPA UI directly
COPY --from=frontend-builder --chown=appuser:appuser /build/frontend/dist /code/frontend/dist

USER appuser

ENV PATH="/code/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONOPTIMIZE=1 \
    MALLOC_TRIM_THRESHOLD_=65536 \
    PORT=8080

ARG COMMIT_SHA=""
ENV COMMIT_SHA=${COMMIT_SHA}

ARG AGENT_VERSION=1.0.0
ENV AGENT_VERSION=${AGENT_VERSION}

EXPOSE 8080

CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1 --limit-concurrency 50 --no-access-log"]
