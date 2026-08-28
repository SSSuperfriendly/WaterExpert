# syntax=docker/dockerfile:1
#
# WaterExpert — multi-stage build (review item 25).
#
# Stage 1 compiles the Next.js frontend to a static export; stage 2 installs the
# Python research runtime and copies the export in. The image runs the FastAPI
# app, which serves both the API and the frontend at `/ui`, so a single container
# is the deployment unit and nginx in front of it does TLS + reverse proxying.

# ---- frontend build --------------------------------------------------------
FROM node:26-slim AS frontend
WORKDIR /build

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci || npm install

COPY frontend/ ./
RUN npm run build

# ---- backend runtime -------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System libraries for the scientific stack: rasterio needs GDAL, opencv needs
# libGL, and a few wheels (tigramite, pyarrow) want a C++ toolchain at install.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libgdal-dev \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Drop privileges for the runtime process.
RUN groupadd -r waterexpert && useradd -r -g waterexpert waterexpert

WORKDIR /app

# Install Python dependencies before copying source so this layer is cached
# across code-only changes.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY configs/ ./configs/
COPY scripts/ ./scripts/
COPY src/ ./src/
COPY --from=frontend /build/out ./frontend/out/

# The runtime root holds `data/` (inputs) and `var/` (state, reports, datasets).
# These are populated at run time via mounted volumes, not baked into the image.
RUN mkdir -p /app/var/state /app/var/reports /app/var/datasets /app/data \
    && chown -R waterexpert:waterexpert /app

USER waterexpert

# Resolve the runtime root to the working directory so `data/` and `var/` land
# on the mounted volumes rather than inside the immutable image.
ENV WATEREXPERT_RUNTIME_ROOT=/app

EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
