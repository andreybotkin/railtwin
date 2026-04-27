# Thailand Railway Digital Twin - Simulation Service

FastAPI simulation service for the Thailand Railway Digital Twin application.

## Features

- RESTful API with automatic OpenAPI documentation
- Background train position calculation and Redis caching for the gateway
- PostGIS integration for geospatial queries
- Train simulation based on actual schedules
- Rate limiting and CORS protection

## Quick Start

### Prerequisites

- Python 3.14+
- PostgreSQL with PostGIS
- Redis (required for train position cache)

### Installation

1. Create a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:
```bash
pip install -e ".[dev]"
```

3. Copy the root environment file and configure database credentials:
```bash
cp ../.env.example .env
# Edit .env with your database and Redis configuration
```

4. Run database migrations:
```bash
alembic upgrade head
```

5. Start the development server:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## API Documentation

Once running, access the API documentation at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Development

### Running Tests

```bash
pytest
```

### Code Quality

```bash
# Format code
black app tests

# Lint code
ruff check app tests

# Type checking
mypy app
```

## Project Structure

```
simulation/
├── app/
│   ├── api/           # API endpoints
│   ├── core/          # Configuration, logging, security
│   ├── models/        # Database models
│   ├── repositories/  # Data access layer
│   ├── services/      # Business logic
│   ├── schemas/       # Pydantic schemas
│   └── main.py        # App entry point
├── alembic/           # Database migrations
├── tests/             # Test suite
└── pyproject.toml     # Project configuration
```

## License

MIT License
