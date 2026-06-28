.PHONY: install dev test lint typecheck db-upgrade docker-up docker-down

VENV = .venv
PYTHON = $(VENV)/Scripts/python
PIP = $(VENV)/Scripts/pip

install:
	python -m venv $(VENV)
	$(PIP) install -e ".[dev,db]"

dev:
	$(PYTHON) -m uvicorn rabeeh_core.infra.server:app --host 0.0.0.0 --port 8000 --reload

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check src tests

typecheck:
	$(PYTHON) -m mypy

db-upgrade:
	$(PYTHON) -m alembic upgrade head

docker-up:
	docker compose -f deploy/docker-compose.yml up -d

docker-down:
	docker compose -f deploy/docker-compose.yml down
