# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-04-26

### Added

- Initial release of Thailand Railway Digital Twin
- Interactive map visualization with Leaflet
- Real-time train position tracking via WebSocket
- RESTful API for stations, routes, trains, and schedules
- Train simulation based on actual SRT schedules
- 35 railway stations across Thailand
- 5 main railway lines (Northern, Northeastern, Southern, Eastern)
- 16 active trains with schedules
- Dark/Light mode support
- Responsive design for mobile and desktop
- Docker Compose for local development
- Kubernetes manifests for K3s deployment
- GitHub Actions CI/CD pipeline
- Comprehensive API documentation (OpenAPI/Swagger)
- Database migrations with Alembic
- PostGIS support for geospatial queries

### Technical Stack

- Backend: FastAPI, SQLAlchemy 2.0, Pydantic V2
- Frontend: Next.js 16, TypeScript, Tailwind CSS
- Database: PostgreSQL 15 with PostGIS
- Infrastructure: K3s, Docker, GitHub Actions
