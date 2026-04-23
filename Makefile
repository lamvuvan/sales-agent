.PHONY: help install up down logs seed embed test lint fmt cli api

help:
	@echo "Targets:"
	@echo "  install   - pip install -e .[dev]"
	@echo "  up        - docker compose up -d (postgres + neo4j)"
	@echo "  down      - docker compose down"
	@echo "  seed      - load CSV seed into postgres + neo4j"
	@echo "  embed     - generate embeddings for OTC formulas"
	@echo "  api       - run FastAPI with uvicorn"
	@echo "  cli       - run CLI chat client"
	@echo "  test      - run pytest"
	@echo "  lint      - ruff check"
	@echo "  fmt       - ruff format"

install:
	pip install -e ".[dev]"

up:
	docker compose -f infra/docker-compose.yml up -d

down:
	docker compose -f infra/docker-compose.yml down

logs:
	docker compose -f infra/docker-compose.yml logs -f

seed:
	python -m scripts.seed_all

embed:
	python -m scripts.embed_formulas

api:
	uvicorn sales_agent.api.main:app --host 0.0.0.0 --port 8000 --reload

cli:
	python -m sales_agent.cli

test:
	pytest

lint:
	ruff check sales_agent tests scripts

fmt:
	ruff format sales_agent tests scripts
