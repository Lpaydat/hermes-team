.PHONY: install test lint format format-check check

install:
	npm install

test:
	npx vitest run

lint:
	npx biome check .

format:
	npx biome format --write .

format-check:
	npx biome format .

check: lint test
