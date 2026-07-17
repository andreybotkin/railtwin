FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

ENV UV_PROJECT_ENVIRONMENT=/opt/venv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY . .
RUN uv sync --frozen

# Ensure data directories exist
RUN mkdir -p /app/railroad /app/schedule/raw \
    && adduser --disabled-password --gecos "" setupuser \
    && chown -R setupuser:setupuser /app

USER setupuser
ENV PATH="/opt/venv/bin:$PATH"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
