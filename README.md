# Thailand Railway Digital Twin

[![CI/CD](https://github.com/thailand-railway/digital-twin/actions/workflows/ci-cd.yaml/badge.svg)](https://github.com/thailand-railway/digital-twin/actions/workflows/ci-cd.yaml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A real-time digital twin visualization of Thailand's railway network, featuring live train tracking, route information, and schedule data.

![Thailand Railway Map](docs/screenshot.png)

## Features

- 🗺️ **Interactive Map**: View the complete Thai railway network with all routes and stations
- 🚂 **Real-time Train Tracking**: Watch trains move along routes according to actual schedules
- 📊 **Schedule Information**: Access departure and arrival times for all stations
- 🌓 **Dark/Light Mode**: Comfortable viewing in any lighting condition
- ⚡ **WebSocket Updates**: Live position updates without page refresh
- 📱 **Responsive Design**: Works on desktop, tablet, and mobile devices

## Tech Stack

### Backend
- **Framework**: FastAPI (Python 3.14+)
- **Database**: PostgreSQL 15+ with PostGIS
- **ORM**: SQLAlchemy 2.0 (async)
- **Migrations**: Alembic
- **Validation**: Pydantic V2
- **Real-time**: WebSocket

### Frontend
- **Framework**: Next.js 14+ (App Router)
- **Language**: TypeScript
- **Styling**: Tailwind CSS
- **Components**: shadcn/ui
- **Maps**: Leaflet / React-Leaflet
- **State**: TanStack Query + Zustand

### Infrastructure
- **Orchestration**: K3s (Kubernetes)
- **CI/CD**: GitHub Actions
- **Containers**: Docker

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Node.js 20+ (for local frontend development)
- Python 3.14+ (for local backend development)

### Local Development with Docker

1. Clone the repository:
```bash
git clone https://github.com/thailand-railway/digital-twin.git
cd digital-twin
```

2. Start all services:
```bash
cp .env.sample .env
docker compose up -d
```

3. Run database migrations:
```bash
docker compose exec backend alembic upgrade head
```

4. Access the application:
   - Frontend: http://localhost:3000
   - Gateway API (for frontend): http://localhost:8002
   - Backend API (internal): http://localhost:8000
   - Backend API Docs: http://localhost:8000/docs

### Manual Setup

See individual README files:
- [Backend Setup](backend/README.md)
- [Frontend Setup](frontend/README.md)

## Project Structure

```
thailand-railway-digital-twin/
├── backend/                 # FastAPI backend
│   ├── app/
│   │   ├── api/            # API endpoints
│   │   ├── core/           # Configuration
│   │   ├── models/         # Database models
│   │   ├── repositories/   # Data access layer
│   │   ├── services/       # Business logic
│   │   ├── schemas/        # Pydantic schemas
│   │   └── main.py         # App entry point
│   ├── alembic/            # Database migrations
│   └── tests/              # Test suite
├── frontend/               # Next.js frontend
│   ├── src/
│   │   ├── app/           # Next.js pages
│   │   ├── components/    # React components
│   │   ├── lib/           # Utilities
│   │   └── types/         # TypeScript types
│   └── public/            # Static assets
├── k8s/                   # Kubernetes manifests
├── docs/                  # Documentation
├── docker-compose.yaml    # Local development
└── .github/workflows/     # CI/CD pipelines
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/stations` | List all stations |
| GET | `/api/v1/stations/{id}` | Get station details |
| GET | `/api/v1/routes` | List all routes |
| GET | `/api/v1/routes/{id}` | Get route with geometry |
| GET | `/api/v1/trains` | List all trains |
| GET | `/api/v1/trains/positions` | Get all train positions (via gateway from Redis) |
| GET | `/api/v1/schedules` | List schedules |
| WS | `/ws/trains` | Real-time train positions |

See full API documentation at `/docs` when running the backend. Frontend traffic should use the gateway service.

## Data Sources

- **Railway Network**: State Railway of Thailand (SRT)
- **Geographic Data**: OpenStreetMap
- **Schedules**: SRT official timetables

## Deployment

### K3s Cluster

1. Apply Kubernetes manifests:
```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/postgres/
kubectl apply -f k8s/redis/
kubectl apply -f k8s/backend/
kubectl apply -f k8s/gateway/
kubectl apply -f k8s/frontend/
```

2. Configure secrets:
```bash
kubectl create secret generic backend-secrets \
  --from-literal=SECRET_KEY=your-secret-key \
  --from-literal=DATABASE_URL=your-database-url \
  -n railway
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for deployment architecture details.

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Code Style

- **Python**: Black, Ruff, mypy
- **TypeScript**: ESLint, Prettier
- **Commits**: Conventional Commits

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- State Railway of Thailand for schedule data
- OpenStreetMap contributors for geographic data
- All contributors to this project