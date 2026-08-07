.PHONY: build test lint format check

build:
	go build ./...

test:
	go test ./...

lint:
	golangci-lint run

format:
	gofmt -w .

format-check:
	gofmt -l .

check: lint format-check test
