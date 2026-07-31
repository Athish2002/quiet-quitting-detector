# syntax=docker/dockerfile:1
#
# Multi-stage build: dependencies are resolved and installed in the
# `builder` stage (which needs uv + build tooling); the runtime stage
# copies only the resulting virtualenv and app code, and runs as a
# non-root user with no build tooling present.

# ---------------------------------------------------------------------------
# Stage 1: builder
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

RUN pip install --no-cache-dir uv==0.8.13

WORKDIR /code

# Install dependencies first (cached separately from app code changes).
COPY pyproject.toml README.md uv.lock* ./
RUN uv sync --frozen --no-install-project --no-dev

# Now install the project itself.
COPY src ./src
COPY app.py ./app.py
COPY static ./static
RUN uv sync --frozen --no-dev

# ---------------------------------------------------------------------------
# Stage 2: runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim

WORKDIR /code

RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /code/data \
    && chown -R appuser:appuser /code

COPY --from=builder --chown=appuser:appuser /code /code

USER appuser

ENV PATH="/code/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

ARG COMMIT_SHA=""
ENV COMMIT_SHA=${COMMIT_SHA}

ARG AGENT_VERSION=0.0.0
ENV AGENT_VERSION=${AGENT_VERSION}

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/api/metrics', timeout=3)" || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
