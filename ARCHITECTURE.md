# Architecture Documentation

## System Overview

The Thailand Railway Digital Twin is a web application that provides real-time visualization of Thailand's railway network. The system consists of three main components: a FastAPI backend, a Next.js frontend, and a PostgreSQL database with PostGIS extension.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                           Users                                  │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Kubernetes Ingress (Traefik)                  │
│                   - TLS Termination                              │
│                   - Load Balancing                               │
└─────────────────────────────────────────────────────────────────┘
                    │                           │
                    ▼                           ▼
┌──────────────────────────┐    ┌──────────────────────────┐
│        Frontend          │    │         Backend          │
│    (Next.js / React)     │    │        (FastAPI)         │
│                          │    │                          │
│  - Interactive Map       │    │  - REST API              │
│  - Real-time Updates     │◄──►│  - WebSocket Server      │
│  - Schedule Display      │    │  - Business Logic        │
│  - Responsive UI         │    │  - Train Simulation      │
│                          │    │                          │
│    ┌──────────────┐      │    │    ┌──────────────┐      │
│    │  Leaflet Map │      │    │    │   Services   │      │
│    │  Components  │      │    │    │   Layer      │      │
│    └──────────────┘      │    │    └──────────────┘      │
│                          │    │           │              │
│    ┌──────────────┐      │    │           ▼              │
│    │ React Query  │      │    │    ┌──────────────┐      │
│    │ State Mgmt   │      │    │    │ Repository   │      │
│    └──────────────┘      │    │    │    Layer     │      │
└──────────────────────────┘    │    └──────────────┘      │
                                │           │              │
                                └───────────┼──────────────┘
                                            │
                                            ▼
                    ┌───────────────────────────────────────┐
                    │    PostgreSQL + PostGIS Database      │
                    │                                       │
                    │  - Stations (with locations)          │
                    │  - Routes (with line geometry)        │
                    │  - Trains                             │
                    │  - Schedules                          │
                    │  - Train Positions                    │
                    │                                       │
                    │    ┌─────────────────────────────┐    │
                    │    │    Spatial Indexes (GIST)  │    │
                    │    └─────────────────────────────┘    │
                    └───────────────────────────────────────┘
```

## Component Details

### Frontend (Next.js)

The frontend is built with Next.js 14 using the App Router pattern.

**Key Features:**
- Server-side rendering for initial page load
- Client-side interactivity with React
- Real-time WebSocket connection for train updates
- Responsive design with Tailwind CSS

**Data Flow:**
1. Initial data (stations, routes) fetched via REST API
2. Train positions streamed via WebSocket
3. TanStack Query manages caching and refetching

**Component Structure:**
```
src/
├── app/              # Pages and layouts
├── components/
│   ├── Map/          # Leaflet map components
│   ├── Schedule/     # Schedule display
│   ├── TrainInfo/    # Train list and details
│   └── ui/           # Reusable UI components
├── lib/
│   ├── api/          # API client
│   ├── hooks/        # Custom React hooks
│   └── utils/        # Utility functions
└── types/            # TypeScript definitions
```

### Backend (FastAPI)

The backend follows Clean Architecture principles with clear separation of concerns.

**Layers:**
1. **API Layer** (`api/`): HTTP endpoints and WebSocket handlers
2. **Service Layer** (`services/`): Business logic and simulation
3. **Repository Layer** (`repositories/`): Data access abstraction
4. **Model Layer** (`models/`): Database models and domain entities

**Key Services:**
- `StationService`: Station CRUD and geospatial queries
- `RouteService`: Route management with geometry
- `TrainService`: Train tracking and positions
- `ScheduleService`: Schedule management
- `SimulationService`: Real-time position calculation

**Data Flow:**
1. Request → API Endpoint → Service → Repository → Database
2. Response flows back through the same layers
3. WebSocket broadcasts positions to all connected clients

### Database (PostgreSQL + PostGIS)

The database uses PostgreSQL with PostGIS extension for geospatial data.

**Schema:**
```sql
stations (id, name, code, location POINT, ...)
routes (id, name, line_geometry LINESTRING, ...)
route_stations (route_id, station_id, sequence, ...)
trains (id, train_number, train_type, current_route_id, ...)
schedules (train_id, station_id, arrival_time, departure_time, ...)
train_positions (train_id, location POINT, speed, heading, ...)
```

**Indexes:**
- GIST indexes on all geometry columns
- B-tree indexes on frequently queried columns

## Real-time Train Simulation

The system simulates train positions based on actual schedules:

1. **Schedule Processing**: Load train schedules for current day
2. **Position Calculation**: 
   - Determine current segment (between which stations)
   - Calculate progress based on scheduled times
   - Interpolate position along route geometry
3. **Delay Simulation**: Add random delays (0-15 min) for realism
4. **Broadcasting**: Send positions via WebSocket every 30 seconds

```
Time Flow:
──────────────────────────────────────────────────────►

Schedule:  Station A    ──────────────────►    Station B
           Dep: 08:00                          Arr: 10:00

Current Time: 09:00 (50% progress)

Position: Midpoint between A and B on route geometry
```

## Deployment Architecture

### Kubernetes (K3s)

```
Namespace: railway
├── backend (Deployment, 2+ replicas)
│   ├── HorizontalPodAutoscaler
│   └── Service (ClusterIP)
├── frontend (Deployment, 2+ replicas)
│   └── Service (ClusterIP)
├── postgres (existing, external)
│   └── Service (ClusterIP)
└── Ingress (Traefik)
    ├── railway.example.com → frontend
    └── api.railway.example.com → backend
```

### CI/CD Pipeline

```
Push to main
    │
    ▼
┌──────────────────┐
│   Lint & Test    │
│   (parallel)     │
│  - Backend CI    │
│  - Frontend CI   │
└──────────────────┘
    │
    ▼
┌──────────────────┐
│   Build Images   │
│   Push to GHCR   │
└──────────────────┘
    │
    ▼
┌──────────────────┐
│   Deploy to K3s  │
│   Rolling Update │
└──────────────────┘
```

## Security Considerations

1. **Authentication**: JWT tokens for admin endpoints (optional)
2. **CORS**: Restricted to allowed origins
3. **Rate Limiting**: 100 requests/minute per IP
4. **Input Validation**: Pydantic schemas for all inputs
5. **SQL Injection**: Prevented by SQLAlchemy ORM
6. **Network Policies**: K8s network policies limit pod communication
7. **Secrets Management**: Kubernetes secrets for sensitive data

## Performance Optimizations

1. **Database**:
   - Spatial indexes for geometry queries
   - Connection pooling with asyncpg

2. **API**:
   - Async handlers throughout
   - Response caching with Redis (optional)
   - Pagination for list endpoints

3. **Frontend**:
   - Server components where possible
   - React Query caching
   - Dynamic imports for map components
   - Debounced search inputs

4. **WebSocket**:
   - Batched position updates
   - Heartbeat mechanism for connection health
   - Automatic reconnection with backoff

## Monitoring (Future)

Planned monitoring stack:
- **Prometheus**: Metrics collection
- **Grafana**: Visualization
- **Loki**: Log aggregation

Key metrics to track:
- API response times
- WebSocket connection count
- Database query performance
- Train simulation accuracy
