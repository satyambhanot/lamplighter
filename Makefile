.PHONY: setup results api dash tunnel test reset lint

setup:
	python3 -m venv .venv
	. .venv/bin/activate && pip install -r requirements.txt

results:
	. .venv/bin/activate && python -m engine.run_all

api:
	. .venv/bin/activate && uvicorn api.main:app --port 8000 --reload

dash:
	. .venv/bin/activate && streamlit run dashboard/app.py

tunnel:
	ngrok http 8000

test:
	. .venv/bin/activate && pytest -q

reset:
	curl -s -X POST http://localhost:8000/demo/reset

lint:
	. .venv/bin/activate && ruff check . && ruff format --check .
