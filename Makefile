.PHONY: setup configure results preview api dash tunnel test reset lint

# The project targets Python 3.11. With uv installed, setup fetches 3.11
# itself; otherwise it needs a python3.11 on PATH (override with PYTHON=...).
PYTHON ?= python3.11

setup:
	@if command -v uv >/dev/null 2>&1; then \
		uv venv --clear --python 3.11 .venv && VIRTUAL_ENV=.venv uv pip install -r requirements.txt; \
	else \
		command -v $(PYTHON) >/dev/null 2>&1 || { echo "Python 3.11 not found: install uv or python3.11, or run make setup PYTHON=/path/to/python3.11"; exit 1; }; \
		$(PYTHON) -c "import sys; sys.exit(sys.version_info[:2] != (3, 11))" || { echo "$(PYTHON) is not Python 3.11"; exit 1; }; \
		rm -rf .venv && $(PYTHON) -m venv .venv && .venv/bin/pip install -r requirements.txt; \
	fi
	@.venv/bin/python -c "import sys; v = sys.version_info[:2]; assert v == (3, 11), f'.venv uses Python {v[0]}.{v[1]}, but the project needs 3.11'"
	@echo "Setup done: .venv uses Python 3.11 with pinned requirements."

results:
	. .venv/bin/activate && python -m engine.run_all

preview:
	. .venv/bin/activate && python -m scripts.build_dashboard_preview

configure:
	. .venv/bin/activate && python -m scripts.configure_demo

api:
	. .venv/bin/activate && uvicorn api.main:app --port 8000 --reload

dash:
	. .venv/bin/activate && streamlit run dashboard/app.py

tunnel:
	ngrok http 8000

test:
	. .venv/bin/activate && pytest -q

reset:
	. .venv/bin/activate && python -m scripts.reset_demo

lint:
	. .venv/bin/activate && ruff check . && ruff format --check .
