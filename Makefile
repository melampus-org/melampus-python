.PHONY: dev lint typecheck test cov semconv build ci format demo demo-otlp benchmark

dev:
	uv sync --locked --all-extras
lint:
	uv run --locked ruff check .
	uv run --locked ruff format --check .
typecheck:
	uv run --locked mypy -p melampus
test:
	uv run --locked pytest
cov:
	uv run --locked pytest --cov=melampus --cov-report=term-missing --cov-fail-under=85
semconv:
	uv run --locked python scripts/generate_semconv.py --check
build:
	uv build --no-build-isolation
	uv run --locked twine check --strict dist/*
	uv run --locked python scripts/check_dist.py
ci: dev semconv lint typecheck cov build
format:
	uv run --locked ruff check --fix .
	uv run --locked ruff format .
demo:
	uv run --locked python scripts/demo_agent_session.py
demo-otlp:
	uv run --locked python scripts/demo_session.py
benchmark:
	uv run --locked python benchmarks/overhead.py
