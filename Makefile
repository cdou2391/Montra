.PHONY: help up down logs ps build test lint fmt migrate revision shell-api shell-db reset smoke

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'

up:  ## Start the full stack
	docker compose up -d

down:  ## Stop the stack
	docker compose down

logs:  ## Tail all logs
	docker compose logs -f

ps:  ## Show service status
	docker compose ps

build:  ## Rebuild images
	docker compose build

test:  ## Run the backend test suite
	docker compose run --rm --no-deps api pytest -q

lint:  ## Lint backend and typecheck frontend
	docker compose run --rm --no-deps api ruff check .
	docker compose run --rm --no-deps web pnpm typecheck

fmt:  ## Format backend code
	docker compose run --rm --no-deps api ruff format --line-length 100 app tests
	docker compose run --rm --no-deps api ruff check . --fix

migrate:  ## Apply migrations
	docker compose run --rm --no-deps api alembic upgrade head

revision:  ## Autogenerate a migration: make revision m="add loans"
	docker compose run --rm --no-deps api alembic revision --autogenerate -m "$(m)"

shell-api:  ## Shell into the API container
	docker compose exec api bash

shell-db:  ## psql into the development database
	docker compose exec postgres psql -U montra -d montra

reset:  ## Destroy all data and start clean
	docker compose down -v
	docker compose up -d

# --------------------------------------------------------------------- UAT

# One command, and it rebuilds everything.
#
# The version the app shows comes from the API image, so rebuilding only the
# service you changed leaves About reporting whatever the API was last built
# at. Naming no service is what keeps the two in step.
UAT = docker compose -p montra-uat --env-file .env.uat -f docker-compose.prod.yml

uat:  ## Build and start the UAT stack (production images, plain HTTP)
	$(UAT) up -d --build
	$(UAT) restart proxy
	@echo "waiting for the API..."
	@until curl -sf localhost:$${PROXY_PORT:-8090}/api/v1/health/live >/dev/null; do sleep 2; done
	@echo "UAT serving $$(curl -s localhost:$${PROXY_PORT:-8090}/api/v1/meta)"

uat-down:  ## Stop the UAT stack, keeping its data
	$(UAT) down

uat-logs:  ## Tail the UAT logs
	$(UAT) logs -f --tail 100
