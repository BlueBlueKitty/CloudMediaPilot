.PHONY: install test lint typecheck run smoke-mock smoke-real-connectivity smoke-real-action verify-secrets

install:
	cd backend && python -m pip install -e '.[dev]'

test:
	cd backend && pytest -q

lint:
	cd backend && ruff check app tests

typecheck:
	cd backend && mypy app

run:
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 1315

smoke-mock:
	CMP_USE_MOCK=true python infra/scripts/smoke.py mock

smoke-real-connectivity:
	CMP_USE_MOCK=false python infra/scripts/smoke.py connectivity

smoke-real-action:
	CMP_USE_MOCK=false python infra/scripts/smoke.py action

verify-secrets:
	python infra/scripts/verify_secrets.py
