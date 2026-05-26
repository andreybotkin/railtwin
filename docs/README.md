# Thailand Railway Digital Twin - Documentation

This directory contains additional project documentation and quick references.

## Contents

- `api/` - API documentation and examples (if present)
- `architecture/` - Architecture diagrams and decisions (if present)
- `deployment/` - Deployment guides (if present)
- `frontend/` - Frontend-specific documentation lives in `frontend/README.md`
- `simulation/` - Simulation-specific documentation lives in `simulation/README.md`
- `gateway/` - Gateway service documentation lives in `gateway/README.md`
- `raildbsetup/` - Database setup service documentation lives in `raildbsetup/README.md`
- `raildatacollector/` - Data collector service documentation lives in `raildatacollector/README.md`

## Quick Links

- [Main README](../README.md) - Project overview and quick start
- [Architecture](../ARCHITECTURE.md) - System architecture documentation
- [Simulation README](../simulation/README.md) - Simulation setup and development
- [Frontend README](../frontend/README.md) - Frontend setup and development
- [Gateway README](../gateway/README.md) - Gateway service setup and development
- [Rail DB Setup README](../raildbsetup/README.md) - Database initialization service
- [Rail Data Collector README](../raildatacollector/README.md) - Data ingestion service
- [Precomputed Movement Plan](precomputed-movement-plan.md) - Precomputed trajectory resolution design
- [Data Collection & Frontend](data-collection.md) - Real-time tracking data sources and frontend details

## API Documentation

When the simulation service is running, access the interactive API documentation:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

## Development Guides

### Setting Up Local Environment

1. Install Docker and Docker Compose
2. Copy environment template: `cp .env.example .env`
3. Run `docker compose up -d`
4. Access the frontend at http://localhost:3000

## Running Tests

```bash
# Simulation tests
cd simulation
pytest

# Gateway tests
cd gateway
pytest

# Frontend tests
cd frontend
npm run test
```

## Code Style

This project follows strict code style guidelines and validates them automatically on every push in GitHub Actions.

**Python (All services: simulation, raildbsetup, raildatacollector, gateway)**:
- Formatter: Black (`uv run black app tests` to format; `uv run black --check app tests` to check)
- Linter: Ruff (`uv run ruff check .` or `uv run ruff check --fix .`)
- Type Checker: mypy (`uv run mypy app`)

**TypeScript (Frontend)**:
- Formatter: Prettier
- Linter: ESLint
- Type Checker: TypeScript

## Database Migrations

```bash
# Create new migration
cd simulation
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

## Contact

For questions or issues, please open a GitHub issue.
