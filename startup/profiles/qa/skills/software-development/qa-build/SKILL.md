---
name: qa-build
description: "Use when building and containerizing an artifact for QA testing. Detects build system, generates Containerfile if needed, builds Podman/Docker image, verifies health check."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [qa, build, container, podman, docker, containerfile]
    related_skills: [qa-protocol]
---

# QA Build — build and containerize the artifact

You build the real artifact from source and create a container **image** that test workers can run in isolation. The image is the shared artifact: built once, each worker starts its own container from it.

## Detect the build system

| Signal | Build command |
|--------|--------------|
| `package.json` | `npm install && npm run build` (or `yarn`, `pnpm`, `bun`) |
| `Cargo.toml` | `cargo build --release` |
| `pyproject.toml` / `setup.py` | `pip install -e .` or `pip install .` |
| `go.mod` | `go build -o <binary>` or `go install` |
| `Makefile` | `make` |
| `Dockerfile` | Use directly (skip generation) |
| `docker-compose.yml` | `docker compose up --build` |
| `CMakeLists.txt` | `mkdir build && cd build && cmake .. && make` |
| `pom.xml` | `mvn package` |
| `build.gradle` / `build.gradle.kts` | `./gradlew build` |
| `Gemfile` | `bundle install` then `rake` or the app command |
| `mix.exs` | `mix deps.get && mix compile` |
| `flake.nix` | `nix build` or `nix develop` |

For more languages (C#, PHP, Scala, Haskell, Erlang, Lua, R, Zig, Nim), load the `references/language-build-reference.md` from the `live-testing` skill directory.

## Detect container runtime

```bash
command -v podman && echo "podman" || (command -v docker && echo "docker" || echo "none")
```

- **Podman (default):** rootless, daemonless. `podman build` reads Dockerfiles. `podman run` accepts same flags as Docker.
- **Docker (fallback):** when Podman not available.
- **None:** workspace isolation for stateless artifacts only. For stateful artifacts without a runtime, file P0 finding: "cannot isolate test environment."

## Generate Containerfile (if project doesn't have one)

If no `Dockerfile` or `Containerfile` exists, generate one based on the build system:

### Node.js / Next.js
```dockerfile
FROM node:20-slim
WORKDIR /app
COPY package*.json ./
RUN npm ci --production
COPY . .
RUN npm run build
EXPOSE 3000
CMD ["npm", "start"]
```

### Python (Flask/FastAPI)
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml setup.py ./
RUN pip install -e .
COPY . .
EXPOSE 8000
CMD ["python", "-m", "gunicorn", "app:app", "--bind", "0.0.0.0:8000"]
```

### Python (Django)
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt
COPY . .
RUN python manage.py migrate
EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
```

### Go
```dockerfile
FROM golang:1.21-alpine AS builder
WORKDIR /app
COPY go.* ./
RUN go mod download
COPY . .
RUN go build -o /app/server .
FROM alpine:latest
COPY --from=builder /app/server /app/server
EXPOSE 8080
CMD ["/app/server"]
```

### Rust
```dockerfile
FROM rust:1.75-slim AS builder
WORKDIR /app
COPY Cargo.* ./
RUN cargo build --release
COPY . .
RUN cargo build --release
FROM debian:bookworm-slim
COPY --from=builder /app/target/release/<binary> /app/<binary>
EXPOSE 8080
CMD ["/app/<binary>"]
```

Write the generated Containerfile to the workspace (not the project repo).

### Environment variables

Most real artifacts need secrets/env at runtime (API keys, DB URLs, Stripe keys). Copy the project's `.env`, `.env.local`, or `.env.production` into the container:

```dockerfile
# Add after COPY . . :
COPY .env.local .env.local
```

If the project has no env file, the container will start but fail on first API call. Check for env files during build detection and warn in the completion summary if missing.

### Next.js special case

Next.js standalone builds need `output: 'standalone'` in `next.config.js` and a different Containerfile pattern (copy `.next/standalone` + `.next/static` + `public/`). If `npm run build` produces `.next/standalone/`, use the standalone pattern instead of the generic Node.js template.

## Build the image

```bash
<podman|docker> build -t qa-test:<card-id> -f Containerfile .
```

## Verify image health

```bash
# Start container
<podman|docker> run -d --memory=1g --cpus=1 -p 18080:<app-port> qa-test:<card-id>

# Wait for health (up to 30 seconds)
for i in $(seq 1 30); do
  curl -sf http://localhost:18080/health && break
  # Or check TCP port:
  # ss -tlnp | grep -q :18080 && break
  sleep 1
done

# Stop verification container
<podman|docker> rm -f <container-id>
```

## Complete with image metadata

```python
kanban_complete(
    summary=f"Built image qa-test:{card_id}, health check passed",
    metadata={
        "image_tag": f"qa-test:{card_id}",
        "container_port": app_port,
        "containerfile_source": "project" | "generated",
        "build_success": True
    }
)
```

## Worker container lifecycle

Each test worker starts its own container from the pre-built image:

```bash
# Worker starts container on unique port (18081-18084)
<podman|docker> run -d \
  --memory=1g --cpus=1 \
  -p 18081:<app-port> \
  qa-test:<card-id>

# Wait for health
for i in $(seq 1 30); do curl -sf http://localhost:18081/health && break; sleep 1; done

# Run tests against localhost:18081
# Post results to blackboard

# Cleanup (non-negotiable)
<podman|docker> rm -f <container-id>
```

Port allocation: 18081 (worker A), 18082 (worker B), 18083 (worker C), 18084 (worker D).

## Resource limits

Default: 1GB memory, 1 CPU per container. Configurable via `qa.container_memory` and `qa.container_cpus` in config.yaml.
