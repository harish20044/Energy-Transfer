# Energy-Transfer — developer command surface.
#
# `make` is not installed on Windows by default. Either:
#   winget install ezwinports.make      (then use these targets from Git Bash)
# or run the underlying commands shown in each recipe directly — every one of
# them is a plain `docker compose` / `npm` invocation with no hidden state.
#
# CI does NOT shell out to make: .github/workflows/ci.yml runs the same commands
# explicitly so that each step is independently cacheable and readable in logs.

SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE := docker compose
BE      := $(COMPOSE) exec -T backend
FE_DIR  := frontend

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# --- Lifecycle ---------------------------------------------------------------

.PHONY: setup
setup: ## First-time setup: create .env from the template
	@test -f .env || (cp .env.example .env && echo "Created .env — review it before starting.")

.PHONY: up
up: setup ## Start the core stack (postgres, redis, backend, frontend)
	$(COMPOSE) up -d --build
	@echo "API  http://localhost:8000/docs"
	@echo "Web  http://localhost:5173"

.PHONY: up-obs
up-obs: setup ## Start the stack plus Prometheus and Grafana
	$(COMPOSE) --profile observability up -d --build

.PHONY: down
down: ## Stop the stack (volumes preserved)
	$(COMPOSE) down

.PHONY: restart
restart: down up ## Restart the stack

.PHONY: logs
logs: ## Tail logs from every service
	$(COMPOSE) logs -f --tail=100

.PHONY: ps
ps: ## Show service status and health
	$(COMPOSE) ps

# --- Shells ------------------------------------------------------------------

.PHONY: shell
shell: ## Open a shell in the backend container
	$(COMPOSE) exec backend /bin/bash

.PHONY: db-shell
db-shell: ## Open psql against the dev database
	$(COMPOSE) exec postgres psql -U energy -d energy_transfer

.PHONY: redis-shell
redis-shell: ## Open redis-cli
	$(COMPOSE) exec redis redis-cli

# --- Backend quality gates ---------------------------------------------------

.PHONY: lint
lint: ## Ruff lint + format check (backend)
	$(BE) ruff check app tests
	$(BE) ruff format --check app tests

.PHONY: format
format: ## Autofix lint and formatting (backend)
	$(BE) ruff check --fix app tests
	$(BE) ruff format app tests

.PHONY: typecheck
typecheck: ## mypy --strict (backend)
	$(BE) mypy app

.PHONY: test
test: ## Run backend tests with coverage gate
	$(BE) pytest

# --- Frontend quality gates --------------------------------------------------

.PHONY: fe-lint
fe-lint: ## ESLint + Prettier check (frontend)
	cd $(FE_DIR) && npm run lint && npm run format:check

.PHONY: fe-typecheck
fe-typecheck: ## tsc --noEmit (frontend)
	cd $(FE_DIR) && npm run typecheck

.PHONY: fe-test
fe-test: ## Vitest (frontend)
	cd $(FE_DIR) && npm run test:run

.PHONY: fe-build
fe-build: ## Production build (frontend)
	cd $(FE_DIR) && npm run build

# --- Aggregate ---------------------------------------------------------------

.PHONY: ci
ci: lint typecheck test fe-lint fe-typecheck fe-test fe-build ## Everything CI runs

.PHONY: clean
clean: ## Stop the stack and DELETE all volumes (destroys the dev database)
	$(COMPOSE) down -v --remove-orphans
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -prune -exec rm -rf {} + 2>/dev/null || true
