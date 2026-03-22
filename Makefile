.PHONY: dev test lint format typecheck migrate docker clean evaluate

## Run development server with hot reload
dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

## Run all tests with coverage
test:
	pytest tests/ -v --tb=short --cov=app --cov-report=term-missing

## Run linter (ruff check)
lint:
	ruff check app/ tests/

## Auto-format all source files
format:
	ruff format app/ tests/

## Run static type checker
typecheck:
	mypy app/ --ignore-missing-imports

## Run Alembic database migrations
migrate:
	alembic upgrade head

## Build and start the full stack with Docker Compose
docker:
	docker-compose up --build

## Remove all generated artefacts
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .mypy_cache .ruff_cache .pytest_cache htmlcov .coverage

## Run the AI evaluation pipeline
evaluate:
	python eval/evaluate.py
