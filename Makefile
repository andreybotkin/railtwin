.PHONY: help dev down logs test test-simulation test-gateway test-frontend lint format clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

## Development
dev:  ## Start all services with Docker Compose
	docker compose up -d

dev-tools:  ## Start all services including dev tools (pgadmin, redis-commander)
	docker compose --profile tools up -d

down:  ## Stop all services
	docker compose down

logs:  ## Follow logs from all services
	docker compose logs -f --tail=100

logs-simulation:  ## Follow simulation service logs
	docker compose logs -f --tail=100 simulation

logs-gateway:  ## Follow gateway service logs
	docker compose logs -f --tail=100 gateway

logs-frontend:  ## Follow frontend service logs
	docker compose logs -f --tail=100 frontend

## Testing
test: test-simulation test-gateway test-frontend  ## Run all tests

test-simulation:  ## Run simulation service tests
	cd simulation && pytest --cov=app --cov-report=term-missing

test-gateway:  ## Run gateway service tests
	cd gateway && pytest --cov=app --cov-report=term-missing

test-frontend:  ## Run frontend tests
	cd frontend && npm run test

## Linting & Formatting
lint:  ## Run all linting checks
	cd simulation && ruff check app tests
	cd gateway && ruff check app tests
	cd frontend && npm run lint

lint-fix:  ## Fix linting issues
	cd simulation && ruff check --fix app tests
	cd frontend && npm run lint:fix

format:  ## Format all code
	cd simulation && black app tests
	cd gateway && black app tests
	cd frontend && npm run format

## Database
migrate:  ## Run database migrations
	docker compose exec simulation alembic upgrade head

## Cleanup
clean:  ## Clean up generated files and caches
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .coverage coverage.xml *.pyc 2>/dev/null || true