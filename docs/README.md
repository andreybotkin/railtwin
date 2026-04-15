# Thailand Railway Digital Twin - Documentation

This directory contains additional documentation for the project.

## Contents

- `api/` - API documentation and examples
- `architecture/` - Architecture diagrams and decisions
- `deployment/` - Deployment guides

## Quick Links

- [Main README](../README.md) - Project overview and quick start
- [Architecture](../ARCHITECTURE.md) - System architecture documentation
- [Simulation README](../simulation/README.md) - Simulation setup and development
- [Frontend README](../frontend/README.md) - Frontend setup and development

## API Documentation

When the simulation service is running, access the interactive API documentation:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

## Development Guides

### Setting Up Local Environment

1. Install Docker and Docker Compose
2. Copy environment template: `cp .env.sample .env`
3. Run `docker compose up -d`
4. Access frontend at http://localhost:3000

### Running Tests

```bash
# Simulation tests
cd simulation
pytest

# Frontend tests
cd frontend
npm run test
```

### Code Style

This project follows strict code style guidelines:

**Python (Simulation)**:
- Formatter: Black
- Linter: Ruff
- Type Checker: mypy

**TypeScript (Frontend)**:
- Formatter: Prettier
- Linter: ESLint
- Type Checker: TypeScript strict mode

### Database Migrations

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
