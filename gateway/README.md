# Thailand Railway Digital Twin - Gateway

FastAPI gateway service for the Thailand Railway Digital Twin.

## Overview

The gateway service provides a lightweight API layer for the frontend. It proxies requests to the simulation service and Redis cache, exposing a stable API surface for the web client.

## Quick Start

### Prerequisites

- Python 3.14+
- Redis
- Simulation service available on the configured `SIMULATION_URL`

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

3. Copy the root environment template and configure:
```bash
cp ../.env.example .env
# Edit .env with your API and Redis settings
```

4. Start the gateway:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8002
```

## Project Structure

```
gateway/
├── app/               # Gateway application code
├── tests/             # Gateway tests
├── pyproject.toml     # Project configuration
└── Dockerfile         # Container image build config
```
