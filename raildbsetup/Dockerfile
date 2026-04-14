FROM python:3.14-slim

WORKDIR /app

# Install build deps for asyncpg, lxml, shapely
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY . .

# Ensure data directories exist
RUN mkdir -p /app/railroad /app/schedule/raw \
    && adduser --disabled-password --gecos "" setupuser \
    && chown -R setupuser:setupuser /app

USER setupuser

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
