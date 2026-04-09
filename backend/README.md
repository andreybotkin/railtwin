# Thailand Railway Digital Twin - Backend

FastAPI backend for the Thailand Railway Digital Twin application.

## Features

- RESTful API with automatic OpenAPI documentation
- WebSocket support for real-time train position updates
- PostGIS integration for geospatial queries
- Train simulation based on actual schedules
- Rate limiting and CORS protection

## Quick Start

### Prerequisites

- Python 3.14+
- PostgreSQL 15+ with PostGIS extension
- Redis (optional, for caching)

### Installation

1. Create a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# or
.venv\Scripts\activate  # Windows
```

2. Install dependencies:
```bash
pip install -e ".[dev]"
```

3. Copy environment file and configure:
```bash
cp .env.example .env
# Edit .env with your database credentials
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
backend/
├── app/
│   ├── api/           # API endpoints
│   ├── core/          # Configuration, logging, security
│   ├── models/        # Database models
│   ├── repositories/  # Data access layer
│   ├── services/      # Business logic
│   ├── schemas/       # Pydantic models
│   └── main.py        # Application entry point
├── alembic/           # Database migrations
├── tests/             # Test suite
└── pyproject.toml     # Project configuration
```

## License

MIT License
