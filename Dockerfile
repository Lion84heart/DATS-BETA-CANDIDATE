# ---------------------------------------------------------------------------
# DATS Beta — Production Container
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Builder stage — compile & install Python dependencies
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies (required for compiling scipy, numpy, pandas)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install project with all dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e "."

# ---------------------------------------------------------------------------
# Runtime stage — minimal image with only runtime artifacts
# ---------------------------------------------------------------------------
FROM python:3.12-slim

WORKDIR /app

# Security: run as non-root
RUN groupadd -r dats && useradd -r -g dats dats

# Install runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY src/ ./src/
COPY docs/ ./docs/
COPY tests/ ./tests/
COPY pyproject.toml ./
COPY .env.example ./

# Ensure Python can find internal packages (trading, api, agents, etc.)
ENV PYTHONPATH=/app/src

RUN chown -R dats:dats /app
USER dats

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health/ || exit 1

# Launch with PYTHONPATH set so 'api.main' resolves to /app/src/api/main.py
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
