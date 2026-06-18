.PHONY: help install test test-ai test-ingestion up down logs lint clean

VENV ?= .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
COMPOSE := docker compose -f infrastructure/docker/docker-compose.yml

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Create venv and install dev dependencies for both services
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r services/ai-service/requirements-dev.txt
	$(PIP) install -r services/ingestion-service/requirements-dev.txt

test: test-ai test-ingestion ## Run all test suites

test-ai: ## Run AI service tests
	cd services/ai-service && ../../$(PY) -m pytest

test-ingestion: ## Run ingestion service tests
	cd services/ingestion-service && ../../$(PY) -m pytest

up: ## Build and start the full stack with Docker Compose
	$(COMPOSE) up --build -d

down: ## Stop the stack
	$(COMPOSE) down

logs: ## Tail container logs
	$(COMPOSE) logs -f

clean: ## Remove caches and local databases
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.db' -delete
