# Container Testing — Podman/Docker Isolation for QA Workers

How to build, run, and clean up containers for isolated parallel test execution. Used when the artifact is medium/large and needs container isolation per the adaptive sizing decision in Phase 1.

## Runtime selection

Detect at runtime which container runtime is available:

```bash
# Check in priority order: podman → docker → none
if command -v podman &>/dev/null; then
  RUNTIME="podman"
elif command -v docker &>/dev/null; then
  RUNTIME="docker"
else
  RUNTIME="none"
fi
echo "$RUNTIME"
```

- **Podman (default):** rootless, daemonless, lighter. `podman build` reads Dockerfile. `podman run` accepts same flags as Docker.
- **Docker (fallback):** used when Podman is not available or configured explicitly via `qa.container_runtime: docker`.
- **Workspace isolation (last resort):** if neither is available, each worker builds from source in its own workspace. Only safe for stateless artifacts (CLI, library). For stateful artifacts, file a finding: "cannot isolate test environment — container runtime not available."

Configurable: `qa.container_runtime` in config.yaml (`podman` | `docker` | `none`). When set to a specific value, skip detection and use that.

## Containerfile detection and generation

### If the project has a Dockerfile/Containerfile

Use it directly. No generation needed.

```bash
ls Dockerfile Containerfile 2>/dev/null
```

### Generate a Containerfile based on build system

If no Dockerfile exists, generate one in the QA workspace (not the project repo).

#### Node.js (package.json)

```dockerfile
FROM node:20-slim
WORKDIR /app
COPY package*.json ./
RUN npm ci --production || npm install --production
COPY . .
RUN npm run build 2>/dev/null || true
EXPOSE 3000
CMD ["npm", "start"]
```

#### Python (pyproject.toml / setup.py)

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml setup.py requirements.txt ./
RUN pip install --no-cache-dir -e . || pip install --no-cache-dir .
COPY . .
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

#### Go (go.mod)

```dockerfile
FROM golang:1.22-alpine AS builder
WORKDIR /app
COPY go.* ./
RUN go mod download
COPY . .
RUN go build -o /server .

FROM alpine:latest
COPY --from=builder /server /server
EXPOSE 8080
CMD ["/server"]
```

#### Rust (Cargo.toml)

```dockerfile
FROM rust:1.78-slim AS builder
WORKDIR /app
COPY Cargo.* ./
RUN mkdir src && echo "fn main() {}" > src/main.rs && cargo build --release
COPY . .
RUN cargo build --release

FROM debian:bookworm-slim
COPY --from=builder /app/target/release/server /server
EXPOSE 8080
CMD ["/server"]
```

#### Generic fallback

If the build system is unknown, use a minimal base and copy the project:

```dockerfile
FROM ubuntu:24.04
WORKDIR /app
COPY . .
# Install deps based on detected files
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl && rm -rf /var/lib/apt/lists/*
EXPOSE 8080
# CMD set per-artifact
```

Write generated Containerfiles to the workspace, not the project repo. The file should be named `Containerfile` (Podman convention) or `Dockerfile` (Docker convention) — both runtimes read either name.

## Build the image

The main session builds the image once in Phase 2. All child workers use this image.

```bash
RUNTIME="podman"  # or "docker"
IMAGE_TAG="qa-test:${CARD_ID}"

# Build from the project directory (or workspace if Containerfile was generated)
cd /path/to/project
$RUNTIME build -t "$IMAGE_TAG" .

# Verify the image exists
$RUNTIME images | grep "$IMAGE_TAG"
```

Build evidence: capture the build output (stdout + stderr). If the build fails, capture the full error — that's your Critical finding.

## Run a container (per child worker)

Each child worker starts its own container from the pre-built image.

### Port allocation

Sequential from 18081. Each worker gets a unique port:

| Worker | Port |
|---|---|
| A (functional) | 18081 |
| B (journeys) | 18082 |
| C (non-functional) | 18083 |
| D (exploratory) | 18084 |

```bash
RUNTIME="podman"
IMAGE_TAG="qa-test:${CARD_ID}"
PORT=18081  # allocated per worker
APP_PORT=3000  # the port the app listens on inside the container
MEMORY="1g"  # from qa.container_memory config
CPUS="1"     # from qa.container_cpus config

# Start the container
CONTAINER_ID=$($RUNTIME run -d \
  --name "qa-worker-${CARD_ID}-${PORT}" \
  --memory="$MEMORY" \
  --cpus="$CPUS" \
  -p "${PORT}:${APP_PORT}" \
  "$IMAGE_TAG")

echo "Container started: $CONTAINER_ID"
```

### Health check

Wait for the container to be ready before testing:

```bash
# Poll the health endpoint or TCP port for up to 30 seconds
for i in $(seq 1 30); do
  # Try health endpoint first
  if curl -sf "http://localhost:${PORT}/health" 2>/dev/null; then
    echo "Container healthy (health endpoint)"
    break
  fi
  # Try TCP port
  if ss -tlnp | grep -q ":${PORT}"; then
    echo "Container healthy (port listening)"
    break
  fi
  # Check if container is still running
  if ! $RUNTIME ps -q --filter "id=$CONTAINER_ID" | grep -q .; then
    echo "Container died during startup"
    $RUNTIME logs "$CONTAINER_ID"
    break
  fi
  sleep 1
done

# Verify it's actually responding
curl -v "http://localhost:${PORT}/" 2>&1 | head -20
```

If the container doesn't become healthy within 30 seconds:
1. Check container logs: `$RUNTIME logs "$CONTAINER_ID"`
2. Check if the app port is correct: `$RUNTIME inspect "$CONTAINER_ID" | grep -A5 ExposedPorts`
3. File a finding (Critical: "container won't start" or "app unreachable in container")

### Resource limit enforcement

Verify that resource limits are actually enforced:

```bash
# Check the container's resource limits
$RUNTIME inspect "$CONTAINER_ID" --format '{{.HostConfig.Memory}} {{.HostConfig.NanoCpus}}'

# Memory should show 1073741824 (1GB in bytes)
# NanoCpus: 1000000000 = 1 CPU
```

To test that memory limits are enforced (optional, for protocol validation):

```bash
# Start a container with a tiny memory limit and run a memory hog
$RUNTIME run --memory=128m --rm alpine sh -c 'apk add stress && stress --vm 1 --vm-bytes 256M --timeout 5s'
# Should be OOM-killed
echo "exit: $?"  # non-zero = OOM killed (expected)
```

## Container-specific edge cases

| Category | Tests |
|---|---|
| Port conflicts | Two containers on the same port — second should fail with a clear error |
| Container OOM | App uses > memory limit — container is killed (check `$RUNTIME inspect` for OOMKilled) |
| Container restart | `exec` into a running container, restart the app inside — does state survive? |
| Volume mounts | Mount a test data volume — does the app read from it? |
| Network isolation | Container can't reach host's localhost services (by design) — verify isolation |
| Signal handling | `kill -TERM` the container — does the app handle SIGTERM gracefully? |
| Image size | Large image = slow start — flag if > 1GB for a simple app |

## Cleanup

Every child worker must clean up its container after testing:

```bash
# Stop and remove the container
$RUNTIME rm -f "$CONTAINER_ID" 2>/dev/null
$RUNTIME rm -f "qa-worker-${CARD_ID}-${PORT}" 2>/dev/null

# Verify it's gone
$RUNTIME ps -a | grep "qa-test:${CARD_ID}" && echo "WARNING: orphaned containers remain" || echo "Clean: no orphaned containers"
```

The main session (Phase 7) should verify all containers are cleaned up:

```bash
# Check for any lingering qa-test containers
$RUNTIME ps -a --filter "ancestor=qa-test:${CARD_ID}" --format "{{.ID}} {{.Names}} {{.Status}}"
# If any remain, clean them up
$RUNTIME ps -aq --filter "ancestor=qa-test:${CARD_ID}" | xargs -r $RUNTIME rm -f

# Also clean up the image (optional, saves disk)
$RUNTIME rmi "qa-test:${CARD_ID}" 2>/dev/null
```

## Multi-service containers

For artifacts with multiple services (e.g., webapp + API + database):

### Using docker-compose / podman-compose

```bash
# If the project has a docker-compose.yml:
$RUNTIME compose up -d --build

# Wait for all services
$RUNTIME compose ps

# Test against the exposed ports
curl -sf http://localhost:18081  # webapp
curl -sf http://localhost:18082/api/health  # API
```

### Manual multi-container

```bash
# Start a database container
$RUNTIME run -d --name "qa-db-${CARD_ID}" \
  --memory=512m --cpus=0.5 \
  -e POSTGRES_PASSWORD=test \
  postgres:16-alpine

# Start the app container linked to the DB
$RUNTIME run -d --name "qa-app-${CARD_ID}" \
  --memory=1g --cpus=1 \
  -p 18081:3000 \
  --link "qa-db-${CARD_ID}:db" \
  -e DATABASE_URL="postgresql://postgres:test@db:5432/test" \
  "qa-test:${CARD_ID}"
```

Cleanup for multi-service:
```bash
$RUNTIME rm -f "qa-db-${CARD_ID}" "qa-app-${CARD_ID}"
$RUNTIME compose down -v  # if using compose
```

## Evidence

- Build output (stdout + stderr, exit code)
- Container inspect output (resource limits, ports, state)
- Container logs (app startup + test-period logs)
- `ps -a` showing container running during tests
- `ps -a` showing no containers after cleanup
- Health check curl output
