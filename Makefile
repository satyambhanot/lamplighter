.PHONY: setup configure results preview api dash tunnel test reset lint

VENV ?= .venv
PYTHON := $(VENV)/bin/python

setup:
	python3 -m venv $(VENV)
	$(PYTHON) -m pip install -r requirements.txt

results:
	$(PYTHON) -m engine.run_all

preview:
	$(PYTHON) -m scripts.build_dashboard_preview

configure:
	$(PYTHON) -m scripts.configure_demo

api:
	$(PYTHON) -m uvicorn api.main:app --port 8000 --reload

dash:
	$(PYTHON) -m streamlit run dashboard/app.py --server.address 127.0.0.1 --server.headless true

tunnel:
	ngrok http 8000

test:
	$(PYTHON) -m pytest -q

reset:
	$(PYTHON) -m scripts.reset_demo

lint:
	$(PYTHON) -m ruff check . && $(PYTHON) -m ruff format --check .
