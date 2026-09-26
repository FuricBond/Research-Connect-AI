# syntax=docker/dockerfile:1
#
# ResearchConnect AI — backend API image (Phase 6.1).
#
# Build from the repository root, because the API imports the repo-level `ml/` package:
#   docker build -f backend/Dockerfile -t researchconnect-backend .
# The context is filtered by backend/Dockerfile.dockerignore, an allowlist.

ARG PYTHON_IMAGE=python:3.13.9-slim-bookworm

# ── Build stage: resolve dependencies into an isolated virtualenv ─────────────
FROM ${PYTHON_IMAGE} AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

COPY backend/requirements.txt /tmp/requirements.txt

# sentence-transformers depends on torch. Left to pip, Linux resolves the CUDA build plus
# several GB of NVIDIA libraries; the API only runs inference on CPU, so the CPU wheel is
# installed first, pinned to the version the test suite runs against. pytest is listed in
# requirements.txt for local test runs and is left out of the image.
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch==2.14.0 \
 && grep -vE '^[[:space:]]*pytest' /tmp/requirements.txt > /tmp/requirements.runtime.txt \
 && pip install -r /tmp/requirements.runtime.txt

# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM ${PYTHON_IMAGE} AS runtime

# PYTHONPATH covers `app` (backend/) and the repo-level `ml` and `scrapers` packages.
# HF_HOME is where sentence-transformers caches the embedding model it downloads on first
# use; it must be writable by the unprivileged user.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}" \
    PYTHONPATH="/app/backend:/app" \
    HF_HOME="/home/app/.cache/huggingface"

RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --home-dir /home/app --create-home \
    --shell /usr/sbin/nologin app

COPY --from=builder /opt/venv /opt/venv

# Mirror the repository layout: services locate `ml/` relative to their own path. Source
# stays root-owned, so the unprivileged runtime user cannot modify it.
WORKDIR /app/backend
COPY backend/alembic.ini ./alembic.ini
COPY backend/alembic ./alembic
COPY backend/app ./app
COPY backend/scripts ./scripts
COPY ml /app/ml
COPY scrapers /app/scrapers

USER app

EXPOSE 8000

# One worker: the login rate limiter and discovery cache live in process memory, so extra
# workers would each keep their own and multiply the effective limits.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
