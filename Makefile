.PHONY: install test lint typecheck run smoke-mock smoke-real-connectivity smoke-real-action verify-secrets

ifeq ($(OS),Windows_NT)
SHELL := powershell.exe
.SHELLFLAGS := -NoProfile -Command
PYTHON ?= python
HOST ?= 0.0.0.0
PORT ?= 1315

install:
	cd backend; if (Get-Command uv -ErrorAction SilentlyContinue) { uv sync --extra dev } elseif (Test-Path '.venv/Scripts/python.exe') { & '.venv/Scripts/python.exe' -m ensurepip --upgrade; & '.venv/Scripts/python.exe' -m pip install -e '.[dev]' } else { & '$(PYTHON)' -m pip install -e '.[dev]' }

test:
	New-Item -ItemType Directory -Force 'backend/.tmp' | Out-Null; $$env:TMP=(Resolve-Path 'backend/.tmp').Path; $$env:TEMP=$$env:TMP; $$env:TMPDIR=$$env:TMP; if (Get-Command uv -ErrorAction SilentlyContinue) { uv run --project backend --extra dev python -m pytest -q 'backend/tests' } elseif (Test-Path 'backend/.venv/Scripts/python.exe') { & 'backend/.venv/Scripts/python.exe' -m pytest -q 'backend/tests' } else { & '$(PYTHON)' -m pytest -q 'backend/tests' }

lint:
	if (Get-Command uv -ErrorAction SilentlyContinue) { uv run --project backend --extra dev python -m ruff check 'backend/app' 'backend/tests' } elseif (Test-Path 'backend/.venv/Scripts/python.exe') { & 'backend/.venv/Scripts/python.exe' -m ruff check 'backend/app' 'backend/tests' } else { & '$(PYTHON)' -m ruff check 'backend/app' 'backend/tests' }

typecheck:
	if (Get-Command uv -ErrorAction SilentlyContinue) { uv run --project backend --extra dev python -m mypy 'backend/app' } elseif (Test-Path 'backend/.venv/Scripts/python.exe') { & 'backend/.venv/Scripts/python.exe' -m mypy 'backend/app' } else { & '$(PYTHON)' -m mypy 'backend/app' }

run:
	if (Get-Command uv -ErrorAction SilentlyContinue) { uv run --project backend python -m uvicorn app.main:app --app-dir backend --reload --host $(HOST) --port $(PORT) } elseif (Test-Path 'backend/.venv/Scripts/python.exe') { & 'backend/.venv/Scripts/python.exe' -m uvicorn app.main:app --app-dir backend --reload --host $(HOST) --port $(PORT) } else { & '$(PYTHON)' -m uvicorn app.main:app --app-dir backend --reload --host $(HOST) --port $(PORT) }

smoke-mock:
	$$env:CMP_USE_MOCK='true'; if (Get-Command uv -ErrorAction SilentlyContinue) { uv run --project backend python 'infra/scripts/smoke.py' mock } elseif (Test-Path 'backend/.venv/Scripts/python.exe') { & 'backend/.venv/Scripts/python.exe' 'infra/scripts/smoke.py' mock } else { & '$(PYTHON)' 'infra/scripts/smoke.py' mock }

smoke-real-connectivity:
	$$env:CMP_USE_MOCK='false'; if (Get-Command uv -ErrorAction SilentlyContinue) { uv run --project backend python 'infra/scripts/smoke.py' connectivity } elseif (Test-Path 'backend/.venv/Scripts/python.exe') { & 'backend/.venv/Scripts/python.exe' 'infra/scripts/smoke.py' connectivity } else { & '$(PYTHON)' 'infra/scripts/smoke.py' connectivity }

smoke-real-action:
	$$env:CMP_USE_MOCK='false'; if (Get-Command uv -ErrorAction SilentlyContinue) { uv run --project backend python 'infra/scripts/smoke.py' action } elseif (Test-Path 'backend/.venv/Scripts/python.exe') { & 'backend/.venv/Scripts/python.exe' 'infra/scripts/smoke.py' action } else { & '$(PYTHON)' 'infra/scripts/smoke.py' action }

verify-secrets:
	if (Get-Command uv -ErrorAction SilentlyContinue) { uv run --project backend python 'infra/scripts/verify_secrets.py' } elseif (Test-Path 'backend/.venv/Scripts/python.exe') { & 'backend/.venv/Scripts/python.exe' 'infra/scripts/verify_secrets.py' } else { & '$(PYTHON)' 'infra/scripts/verify_secrets.py' }
else
PYTHON ?= python3
HOST ?= 0.0.0.0
PORT ?= 1315

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
	cd backend && $(PYTHON) -m uvicorn app.main:app --reload --host $(HOST) --port $(PORT)

smoke-mock:
	CMP_USE_MOCK=true $(PYTHON) infra/scripts/smoke.py mock

smoke-real-connectivity:
	CMP_USE_MOCK=false $(PYTHON) infra/scripts/smoke.py connectivity

smoke-real-action:
	CMP_USE_MOCK=false $(PYTHON) infra/scripts/smoke.py action

verify-secrets:
	$(PYTHON) infra/scripts/verify_secrets.py
endif
