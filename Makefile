.PHONY: install test lint typecheck run smoke-mock smoke-real-connectivity smoke-real-action verify-secrets

PYTHON ?= python3

install:
	cd backend && \
	if $(PYTHON) -m pip --version >/dev/null 2>&1; then \
		$(PYTHON) -m pip install -e '.[dev]'; \
	elif command -v uv >/dev/null 2>&1; then \
		uv pip install -p $(PYTHON) -e '.[dev]'; \
	else \
		$(PYTHON) -m ensurepip --upgrade && $(PYTHON) -m pip install -e '.[dev]'; \
	fi

test:
	cd backend && $(PYTHON) -m pytest -q

lint:
	cd backend && $(PYTHON) -m ruff check app tests

typecheck:
	cd backend && $(PYTHON) -m mypy app

run:
	cd backend && $(PYTHON) -m uvicorn app.main:app --reload --host 0.0.0.0 --port 1315

smoke-mock:
	CMP_USE_MOCK=true $(PYTHON) infra/scripts/smoke.py mock

smoke-real-connectivity:
	CMP_USE_MOCK=false $(PYTHON) infra/scripts/smoke.py connectivity

smoke-real-action:
	CMP_USE_MOCK=false $(PYTHON) infra/scripts/smoke.py action

verify-secrets:
	$(PYTHON) infra/scripts/verify_secrets.py
