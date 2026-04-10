FROM python:3.12-slim

WORKDIR /app

# Install build deps for asyncpg, lxml, shapely
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY . .

# Ensure data directories exist and are writable
RUN mkdir -p /app/railroad /app/schedule \
    && adduser --disabled-password --gecos "" collector \
    && chown -R collector:collector /app

USER collector

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
