.PHONY: install test lint format format-check check

install:
	pip install -e ".[dev]"

test:
	pytest -q

lint:
	ruff check .

format:
	ruff format .

format-check:
	ruff format --check .

check: lint format-check test
