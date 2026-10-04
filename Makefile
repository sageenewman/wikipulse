.DEFAULT_GOAL := help
.PHONY: help up down ps logs clean sync lint fmt typecheck test

help: ## Show this help
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/:.*## /  -  /'

up: ## Start the stack in the background
	docker compose up -d --wait

down: ## Stop the stack (data volumes are kept)
	docker compose down

ps: ## Show running services
	docker compose ps

logs: ## Follow service logs
	docker compose logs -f --tail=100

clean: ## Stop the stack and delete its data volumes
	docker compose down -v

sync: ## Install Python dependencies
	uv sync

lint: ## Check code style
	uv run ruff check .
	uv run ruff format --check .

fmt: ## Format code and apply safe lint fixes
	uv run ruff format .
	uv run ruff check --fix .

typecheck: ## Run static type checks
	uv run mypy .

test: ## Run tests
	uv run pytest
