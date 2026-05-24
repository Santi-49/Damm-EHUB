# ── base ──────────────────────────────────────────────────────────────
FROM python:3.12-slim AS base
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/services/api \
    MPLCONFIGDIR=/tmp/matplotlib
COPY services/api/pyproject.toml services/api/pyproject.toml
COPY services/api/app services/api/app
WORKDIR /app/services/api
RUN pip install --no-cache-dir -e .

# ── development ───────────────────────────────────────────────────────
FROM base AS development
WORKDIR /app
COPY packages packages
COPY services/api services/api
COPY services/optimizer services/optimizer
COPY services/node_cost_ml services/node_cost_ml
COPY data data
WORKDIR /app/services/api
RUN pip install --no-cache-dir -e ".[dev]"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ── production ────────────────────────────────────────────────────────
FROM base AS production
WORKDIR /app
COPY packages packages
COPY services/api services/api
COPY services/optimizer services/optimizer
COPY services/node_cost_ml services/node_cost_ml
COPY data data
WORKDIR /app/services/api
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
