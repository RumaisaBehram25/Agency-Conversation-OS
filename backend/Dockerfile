# ============================================
# Attora Backend — Multi-stage Dockerfile (Optimized)
# ============================================

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app


# ── System dependencies ───────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*


# ── Dependencies stage ───────────────────────
FROM base AS dependencies

RUN pip install --upgrade pip setuptools wheel

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt


# ── Application stage ────────────────────────
FROM dependencies AS application

WORKDIR /app

# Copy only required backend code
COPY app ./app
COPY alembic ./alembic

# If you use alembic config file, ensure it's included
COPY alembic.ini ./

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]