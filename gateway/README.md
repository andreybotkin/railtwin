# Thailand Railway Digital Twin - Gateway

Stateless FastAPI gateway between the website and simulation services.

## Responsibilities

- Accept all website requests.
- Return train positions from Redis (`/api/v1/trains/positions`).
- Stream positions over WebSocket (`/ws/trains`, `/ws/trains/{train_id}`) from Redis.
- Proxy all other `/api/v1/*` requests to simulation.

## Run locally

```bash
pip install -e .
uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload
```
