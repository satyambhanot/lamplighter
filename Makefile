.PHONY: setup configure results preview api dash tunnel voice voice-test test reset lint

# The project targets Python 3.11. With uv installed, setup fetches 3.11
# itself; otherwise it needs a python3.11 on PATH (override with PYTHON=...).
PYTHON ?= python3.11

VENV ?= .venv
VENV_PYTHON := $(VENV)/bin/python

setup:
	@if command -v uv >/dev/null 2>&1; then \
		uv venv --clear --python 3.11 "$(VENV)" && VIRTUAL_ENV="$(VENV)" uv pip install -r requirements.txt; \
	else \
		command -v $(PYTHON) >/dev/null 2>&1 || { echo "Python 3.11 not found: install uv or python3.11, or run make setup PYTHON=/path/to/python3.11"; exit 1; }; \
		$(PYTHON) -c "import sys; sys.exit(sys.version_info[:2] != (3, 11))" || { echo "$(PYTHON) is not Python 3.11"; exit 1; }; \
		$(PYTHON) -m venv --clear "$(VENV)" && "$(VENV_PYTHON)" -m pip install -r requirements.txt; \
	fi
	@"$(VENV_PYTHON)" -c "import sys; v = sys.version_info[:2]; assert v == (3, 11), f'Environment uses Python {v[0]}.{v[1]}, but the project needs 3.11'"
	@echo "Setup done: $(VENV) uses Python 3.11 with pinned requirements."

results:
	"$(VENV_PYTHON)" -m engine.run_all

preview:
	"$(VENV_PYTHON)" -m scripts.build_dashboard_preview

configure:
	"$(VENV_PYTHON)" -m scripts.configure_demo

api:
	"$(VENV_PYTHON)" -m uvicorn api.main:app --port 8000 --reload

dash:
	"$(VENV_PYTHON)" -m streamlit run dashboard/app.py --server.address 127.0.0.1 --server.headless true

# Uses the fixed ngrok domain from NGROK_DOMAIN in .env, so the ElevenLabs
# tools never need re-pointing. Without it, ngrok picks a random URL.
tunnel:
	@set -a; [ -f .env ] && . ./.env; set +a; \
	if [ -n "$$NGROK_DOMAIN" ]; then ngrok http 8000 --url "https://$$NGROK_DOMAIN"; else ngrok http 8000; fi

# Creates or updates the ElevenLabs agent and tools (needs api + tunnel running).
voice:
	"$(VENV_PYTHON)" -m voice.setup_agent

# Text-only test call through ElevenLabs:
# make voice-test SCENARIO=report|status|hazard|other_city|emergency|conrich|no_hazard|not_found
SCENARIO ?= report
voice-test:
	"$(VENV_PYTHON)" -m voice.test_call --scenario $(SCENARIO)

test:
	"$(VENV_PYTHON)" -m pytest -q

reset:
	"$(VENV_PYTHON)" -m scripts.reset_demo

lint:
	"$(VENV_PYTHON)" -m ruff check . && "$(VENV_PYTHON)" -m ruff format --check .
