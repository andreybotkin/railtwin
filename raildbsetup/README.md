# Thailand Railway Digital Twin - Rail DB Setup

Database initialization and data loading service for the Thailand Railway Digital Twin.

## Overview

The `raildbsetup` service prepares PostgreSQL/PostGIS database schema, imports rail network geometry, and seeds schedule data required by the simulation service.

## Quick Start

### Prerequisites

- Python 3.14+
- PostgreSQL with PostGIS

### Installation

1. Create and activate a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:
```bash
pip install -e .
```

3. Copy the root environment variables file:
```bash
cp ../.env.example .env
# Edit .env with your database settings
```

4. Run the service or use Docker Compose to start it.

## Project Structure

```
raildbsetup/
├── app/               # Database setup application code
├── alembic/           # Migration scripts and configuration
├── tests/             # Unit and integration tests
├── pyproject.toml     # Project configuration
└── Dockerfile         # Container image build config
```

## Development

### Code Quality

Run these verification commands locally before committing or pushing changes:

```bash
# Format code
uv run black app tests

# Format check only
uv run black --check app tests

# Lint code
uv run ruff check .

# Type checking
uv run mypy app
```

## License

MIT License
