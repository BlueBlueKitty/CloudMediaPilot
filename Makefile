.PHONY: install test lint typecheck run

install:
	uv sync --project backend --extra dev

test:
	uv run --project backend python -m pytest -q

lint:
	uv run --project backend python -m ruff check app tests

typecheck:
	uv run --project backend python -m mypy app

run:
	uv run --project backend python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 1315
