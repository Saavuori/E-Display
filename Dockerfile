# =============================================================================
# Stage 1: Build the virtualenv
# =============================================================================
FROM python:3.14-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# RPi.GPIO and spidev ship as source distributions and need a C toolchain.
# Everything else (Pillow, numpy, pydantic-core) resolves to manylinux aarch64
# wheels, so none of the image libraries (libjpeg, freetype, lcms2, ...) are
# needed here — they were only ever slowing the build down.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Byte-compile on install so the Pi doesn't pay that cost at first import.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Dependencies come from the lockfile only, so this layer stays cached until
# pyproject.toml or uv.lock actually changes.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra pi


# =============================================================================
# Stage 2: Runtime
# =============================================================================
FROM python:3.14-slim-bookworm

# Version info injected at build time by CI
ARG VERSION=dev
ARG BUILD_DATE=""
ARG GIT_SHA=""

# PYTHONUNBUFFERED sends Python output straight to the container log.
# PATH puts the virtualenv first so `python` / `uvicorn` resolve to it.
ENV APP_VERSION=${VERSION} \
    APP_BUILD_DATE=${BUILD_DATE} \
    APP_GIT_SHA=${GIT_SHA} \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# The compiler and its headers stay behind in the builder stage.
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY . .

# Create directory for artifacts if it doesn't exist
RUN mkdir -p pic

# Expose port for API
EXPOSE 8000

# Default command (can be overridden in docker-compose)
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
