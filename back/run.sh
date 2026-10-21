source .venv/bin/activate

uvicorn main:app --reload --workers 1 --port 8080