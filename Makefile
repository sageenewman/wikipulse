.DEFAULT_GOAL := help
.PHONY: help up down ps logs clean topics lakehouse buckets check-lakehouse ingest record replay check-gaps sync lint fmt typecheck test

# Every profile, so that down and clean also stop the optional services.
ALL_PROFILES := --profile lakehouse

help: ## Show this help
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/:.*## /  -  /'

up: ## Start the stack in the background and create topics
	docker compose up -d --wait
	$(MAKE) topics

down: ## Stop the stack, including optional services (data volumes are kept)
	docker compose $(ALL_PROFILES) down

ps: ## Show running services
	docker compose ps

logs: ## Follow service logs
	docker compose logs -f --tail=100

clean: ## Stop the stack and delete its data volumes (Kafka topics and lakehouse tables)
	docker compose $(ALL_PROFILES) down -v

topics: ## Create the Kafka topics if they do not exist
	docker compose exec -T redpanda sh -s < scripts/create-topics.sh

lakehouse: ## Start object storage and the Iceberg catalog, and create the buckets
	docker compose --profile lakehouse up -d --wait
	$(MAKE) buckets

buckets: ## Create the object storage buckets if they do not exist
	docker compose exec -T object-store sh -s < scripts/create-buckets.sh

check-lakehouse: ## Create a test table through the catalog and check its files reach storage
	docker compose exec -T object-store sh -s < scripts/check-lakehouse.sh

ingest: ## Run the ingestion service (Ctrl+C to stop)
	uv run python -m ingestion

record: ## Record the stream to a file: make record OUT=data/recordings/x.jsonl.gz ARGS="--since-minutes 10"
	uv run python -m ingestion record --out $(OUT) $(ARGS)

replay: ## Publish a recording to the replay topics: make replay FILE=data/recordings/x.jsonl.gz SPEED=10
	uv run python -m ingestion replay $(FILE) --speed $(or $(SPEED),1)

check-gaps: ## Check a topic for lost or duplicated events (default: the live raw topic): make check-gaps TOPIC=wiki.replay
	PYTHONPATH=. uv run python scripts/check_gaps.py $(if $(TOPIC),--topic $(TOPIC))

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
