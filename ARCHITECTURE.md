# Architecture Documentation

### System Overview

The Thailand Railway Digital Twin is a real-time visualization system of Thailand's railway network. The system is built using a microservices architecture consisting of five main services, a PostgreSQL/PostGIS spatial database, and a Redis caching layer:
1. **Frontend (Next.js)**: Interactive web application.
2. **Gateway (FastAPI)**: API gateway routing client traffic and proxying Redis and Simulation queries.
3. **Simulation (FastAPI)**: Tracks trains and simulates active position trajectories based on schedules.
4. **Rail DB Setup (FastAPI)**: Initializes database schema and topology, seeds initial schedules, and computes movement plans.
5. **Rail Data Collector (FastAPI)**: Scrapes external State Railway of Thailand (SRT) tracking delays and processes timetables.

## Architecture Diagram

```
                                 Users / Web Clients
                                         │
                                         ▼
                     ┌───────────────────────────────────────┐
                     │      Kubernetes Ingress (Traefik)     │
                     └───────────────────────────────────────┘
                        │                         │
            (HTTP/WS)   ▼                         ▼   (Static / HTTP)
       ┌────────────────────────┐         ┌────────────────────────┐
       │     Gateway API        │         │       Frontend         │
       │      (FastAPI)         │         │   (Next.js / React)    │
       └────────────────────────┘         └────────────────────────┘
          │                 │
          ▼                 ▼
   ┌───────────┐    ┌────────────────────────┐
   │   Redis   │◄───│   Simulation Service   │
   │   Cache   │    │       (FastAPI)        │
   └───────────┘    └────────────────────────┘
         ▲                      ▲
         │                      │ (SQLAlchemy)
         │                      │
   ┌───────────┐    ┌────────────────────────┐         ┌───────────────────────┐
   │ Rail Data │    │      PostgreSQL        │◄────────│      Rail DB Setup    │
   │ Collector │◄───│    + PostGIS DB        │         │   (FastAPI / Seed)    │
   │ (FastAPI) │    └────────────────────────┘         └───────────────────────┘
```

## Component Details

### Frontend (Next.js)

The frontend is built with Next.js 16 using the App Router pattern and React 19.

**Key Features:**
- Server-side rendering (SSR) for initial page load and static assets.
- Interactive Map Component: Leaflet-based map displaying stations, routes, and animated train positions.
- Unified Autocomplete Search: Integrates station lists and active train trajectories.
- State Management: TanStack Query for server state and Zustand for local map state.
- WebSocket client with exponential backoff reconnection and tab visibility-aware heartbeat.

### Gateway (FastAPI)

Exposes a unified entry point for frontend API and WebSocket connections.

**Key Features:**
- WebSocket Proxying: Relays real-time train positions from Redis pub/sub.
- REST Proxying: Proxies static stations and routes metadata queries to the simulation service.
- Local Cache: Proxies trajectory queries directly from the Redis cache to minimize simulation service load.

### Simulation (FastAPI)

Runs the core train simulation and trajectory calculations.

**Key Features:**
- Real-time Position Calculation: Calculates train positions along polylines using either the precomputed movement plan resolver or the on-the-fly trajectory builder.
- WebSocket Broadcasting: Emits periodic position updates (batched) to the gateway.
- Async Database & Cache layer: Uses SQLAlchemy 2.0 and asyncpg for database access, and redis-py for caching.

### Rail DB Setup (FastAPI)

Executes schema initialization and data migrations.

**Key Features:**
- Database Migrations: Runs Alembic migrations.
- Topology Generation: Imports KML data, snaps railway stations, and builds network graph edges.
- Precomputed Movement Plans: Analyzes timetables and computes segment coordinates in advance.

### Rail Data Collector (FastAPI)

Maintains the system data freshness.

**Key Features:**
- Timetable Scraping: Periodically fetches updated SRT timetables and seeds database files.
- Delay Scraping: Fetches live train delay minutes from the official SRT tracking service.
- Task Scheduler: Runs periodic background tasks using APScheduler.ection for train updates
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

### Simulation (FastAPI)

The simulation service follows Clean Architecture principles with clear separation of concerns.

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
├── gateway (Deployment, 2+ replicas)
│   └── Service (ClusterIP)
├── simulation (Deployment, 2+ replicas)
│   ├── HorizontalPodAutoscaler
│   └── Service (ClusterIP)
├── frontend (Deployment, 2+ replicas)
│   ├── Service (ClusterIP)
│   └── Ingress (Traefik) → routes to gateway and frontend
├── raildatacollector (Deployment, 1 replica)
│   └── Service (ClusterIP)
├── raildbsetup (Job / InitContainer dependency)
├── postgres + PostGIS (StatefulSet)
│   └── Service (ClusterIP)
└── redis (Deployment)
    └── Service (ClusterIP)
```

### CI/CD Pipeline

```
Push to main
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│                    Lint, Format & Test                       │
│    - gateway-ci          - simulation-ci     - frontend-ci   │
│    - raildatacollector-ci  - raildbsetup-ci                  │
└──────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│                  Build & Push Docker Images                  │
│  Build changed components and push to GHCR (latest + SHA)   │
└──────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│                    Deploy to K3s Cluster                     │
│  Apply manifests and perform rolling restarts of deployments │
└──────────────────────────────────────────────────────────────┘
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
