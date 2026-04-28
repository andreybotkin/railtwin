# Thailand Railway Digital Twin - Rail Data Collector

Data ingestion service for the Thailand Railway Digital Twin.

## Overview

The `raildatacollector` service fetches schedule and tracking data from external sources, normalizes it, and stores it for use by the simulation and gateway services.

## Quick Start

### Prerequisites

- Python 3.14+
- PostgreSQL
- Redis

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
# Edit .env with your database and Redis settings
```

4. Run the service or use Docker Compose to start it.

## Project Structure

```
raildatacollector/
├── app/               # Data collector application logic
├── tests/             # Unit and integration tests
├── pyproject.toml     # Project configuration
└── Dockerfile         # Container image build config
```

## License
MIT License.

