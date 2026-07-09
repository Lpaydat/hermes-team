# API Server Testing

Covers REST, GraphQL, gRPC, and WebSocket servers.

## Start the server

1. Build (see SKILL.md).
2. Start in background — capture the PID for teardown:
   ```bash
   SERVER_PORT=18080
   <start-command> --port $SERVER_PORT &
   SERVER_PID=$!
   # Or use terminal(background=true) for long-running servers
   ```
3. Poll until it's listening:
   ```bash
   for i in $(seq 1 30); do
     curl -sf "http://localhost:$SERVER_PORT/health" && break
     sleep 1
   done
   ```

## Confirm it's alive

```bash
curl -v http://localhost:$SERVER_PORT/health
curl -v http://localhost:$SERVER_PORT/healthz
curl -v http://localhost:$SERVER_PORT/ready
curl -v http://localhost:$SERVER_PORT/

# If OpenAPI/Swagger exists:
curl -s http://localhost:$SERVER_PORT/openapi.json | python3 -m json.tool
curl -s http://localhost:$SERVER_PORT/docs
```

## REST endpoint testing

### Basic CRUD
```bash
BASE="http://localhost:$SERVER_PORT/api"

# Create
curl -v -X POST "$BASE/items" \
  -H "Content-Type: application/json" \
  -d '{"name": "test", "value": 42}'

# Read
curl -v "$BASE/items"
curl -v "$BASE/items/1"

# Update
curl -v -X PUT "$BASE/items/1" \
  -H "Content-Type: application/json" \
  -d '{"name": "updated", "value": 99}'

# Delete
curl -v -X DELETE "$BASE/items/1"
```

### Response checks
```bash
curl -s -o /dev/null -w "%{http_code}" "$BASE/items"           # status code
curl -v "$BASE/items"                                           # body + headers
curl -o /dev/null -s -w "time_total: %{time_total}s\n" "$BASE/items"  # timing
```

## GraphQL

```bash
# Query
curl -v -X POST http://localhost:$SERVER_PORT/graphql \
  -H "Content-Type: application/json" \
  -d '{"query": "{ items { id name } }"}'

# Mutation
curl -v -X POST http://localhost:$SERVER_PORT/graphql \
  -H "Content-Type: application/json" \
  -d '{"query": "mutation { createItem(name: \"test\") { id } }"}'

# Introspection — reveals the full schema
curl -s -X POST http://localhost:$SERVER_PORT/graphql \
  -H "Content-Type: application/json" \
  -d '{"query": "{ __schema { types { name } } }"}' | python3 -m json.tool
```

## gRPC

```bash
grpcurl -plaintext localhost:$SERVER_PORT list
grpcurl -plaintext localhost:$SERVER_PORT <package.Service>/List
grpcurl -plaintext -d '{"id": 1}' localhost:$SERVER_PORT <package.Service>/Get

# Health check:
grpcurl -plaintext localhost:$SERVER_PORT grpc.health.v1.Health/Check
```

## WebSocket

```bash
# websocat:
websocat ws://localhost:$SERVER_PORT/ws

# Python:
python3 -c "
import asyncio, websockets
async def test():
    async with websockets.connect('ws://localhost:8080/ws') as ws:
        await ws.send('hello')
        print(await ws.recv())
asyncio.run(test())
"
```

## API-specific edge cases

Cases beyond the universal categories in SKILL.md:

| Category | Tests |
|----------|-------|
| Content negotiation | `Accept: application/xml`, `Accept: text/html`, missing `Content-Type` on POST |
| Payload validation | Empty body `{}`, missing required fields, extra unknown fields, wrong types (string where int expected) |
| SQL/NoSQL injection | `'; DROP TABLE--`, `{$gt: ""}`, unicode in queries |
| Pagination | `?page=0`, `?page=-1`, `?page=999999`, `?limit=0`, `?limit=-1`, missing pagination params |
| Rate limiting | Send 100 rapid requests — is there a 429? |
| CORS | `Origin: http://evil.com` — does the server reflect it? |
| Concurrent requests | 50 simultaneous POSTs via `xargs -P 50` or `ab -n 100 -c 10` |
| Large payloads | 10MB JSON body, deeply nested JSON (1000 levels), large array |
| HTTP methods | `PATCH`, `OPTIONS`, `HEAD`, `TRACE` on endpoints |
| Trailing slashes | `/items` vs `/items/` |
| Case sensitivity | `/Items` vs `/items` |

## Teardown

```bash
kill $SERVER_PID 2>/dev/null
# Or if using terminal background, use process(action='kill')
```

## Evidence

- Full `curl -v` output (request + response headers + body)
- HTTP status code
- Response time
- Server logs for the request (if available)
