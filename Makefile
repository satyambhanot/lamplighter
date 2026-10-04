.PHONY: setup configure results preview api dash tunnel test reset lint

setup:
	python3 -m venv .venv
	. .venv/bin/activate && pip install -r requirements.txt

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
