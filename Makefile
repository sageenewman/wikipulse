.DEFAULT_GOAL := help
.PHONY: help up down ps logs clean topics ingest record replay check-gaps sync lint fmt typecheck test

help: ## Show this help
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/:.*## /  -  /'

up: ## Start the stack in the background and create topics
	docker compose up -d --wait
	$(MAKE) topics

down: ## Stop the stack (data volumes are kept)
	docker compose down

ps: ## Show running services
	docker compose ps

logs: ## Follow service logs
	docker compose logs -f --tail=100

clean: ## Stop the stack and delete its data volumes
	docker compose down -v

topics: ## Create the Kafka topics if they do not exist
	docker compose exec -T redpanda sh -s < scripts/create-topics.sh

ingest: ## Run the ingestion service (Ctrl+C to stop)
	uv run python -m ingestion

record: ## Record the stream to a file: make record OUT=data/recordings/x.jsonl.gz ARGS="--since-minutes 10"
	uv run python -m ingestion record --out $(OUT) $(ARGS)

replay: ## Publish a recording to Kafka: make replay FILE=data/recordings/x.jsonl.gz SPEED=10
	uv run python -m ingestion replay $(FILE) --speed $(or $(SPEED),1)

check-gaps: ## Check the raw topic for lost or duplicated events
	PYTHONPATH=. uv run python scripts/check_gaps.py

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
