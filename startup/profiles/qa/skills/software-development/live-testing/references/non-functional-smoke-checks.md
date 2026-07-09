# Non-Functional Smoke Checks (v3.0)

Cheap, fast checks that catch regressions the functional claims miss. Each check passes, fails (becomes a finding), or is skipped (not applicable — note the reason).

Full penetration testing, load engineering, and WCAG certification are specialist handoffs. QA runs the smoke level only.

## Security smoke (always)

Run on every artifact that accepts input or has authentication.

### IDOR (Insecure Direct Object Reference)
```bash
# Create two users, get tokens for both:
TOKEN_A=$(curl -s -X POST http://localhost:$PORT/auth -d '{"user":"a","pass":"a"}' | jq -r .token)
TOKEN_B=$(curl -s -X POST http://localhost:$PORT/auth -d '{"user":"b","pass":"b"}' | jq -r .token)

# Create a resource as user A:
RESOURCE_ID=$(curl -s -X POST http://localhost:$PORT/api/items \
  -H "Authorization: Bearer $TOKEN_A" \
  -d '{"name":"secret"}' | jq -r .id)

# Try to access it as user B:
curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer $TOKEN_B" \
  http://localhost:$PORT/api/items/$RESOURCE_ID
# Expected: 403 or 404. If 200 → Critical finding (IDOR).
```

### Auth bypass
```bash
# No token:
curl -s -o /dev/null -w "%{http_code}" http://localhost:$PORT/api/items
# Expected: 401 or 403

# Tampered token (drop a character):
curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer ${TOKEN_A%?}" \
  http://localhost:$PORT/api/items
# Expected: 401
```

### Secrets in output
```bash
# Check API responses for sensitive fields:
curl -s http://localhost:$PORT/api/users | grep -iE "password|secret|token|api.?key|private"

# Check error messages (trigger an error, see if it leaks stack traces):
curl -s http://localhost:$PORT/api/items/999999999
# A stack trace in the response = Important finding
```

### Dependency scan
```bash
npm audit 2>&1 | head -20           # Node.js
pip-audit 2>&1 | head -20           # Python
cargo audit 2>&1 | head -20         # Rust
trivy fs . 2>&1 | head -30          # Generic (if installed)
# Flag any HIGH or CRITICAL vulnerability as a finding.
```

## Security depth (v3.0 — new)

Run on all artifacts that accept input or have authentication. These go beyond the basic smoke checks to actively probe common vulnerability classes.

### CSRF (Cross-Site Request Forgery)
```bash
# POST without CSRF token, using only a session cookie:
curl -v -X POST http://localhost:$PORT/api/profile \
  -H "Cookie: session=<valid_session_cookie>" \
  -H "Content-Type: application/json" \
  -d '{"name": "hacked"}'
# If 200 → CSRF vulnerability (Critical)
# Expected: 403 or rejection without CSRF token
```

### XSS (Cross-Site Scripting)
```bash
PAYLOAD='<script>alert(document.cookie)</script>'
# Inject script payload via input:
curl -v -X POST http://localhost:$PORT/api/users \
  -H "Content-Type: application/json" \
  -d "{\"name\": \"$PAYLOAD\"}"
# Check if it's stored and rendered unescaped:
curl -s http://localhost:$PORT/users/1 | grep -i "<script>"
# If found → stored XSS (Critical)

# Reflected XSS — check if query params are reflected unescaped:
curl -s "http://localhost:$PORT/search?q=<script>alert(1)</script>" | grep -i "<script>"
```

### SSRF (Server-Side Request Forgery)
```bash
# If the server fetches URLs (avatar import, webhook, URL preview):
curl -v -X POST http://localhost:$PORT/api/avatar \
  -H "Content-Type: application/json" \
  -d '{"url": "http://169.254.169.254/latest/meta-data/iam/security-credentials/"}'
# If server fetches it → SSRF (Critical)
# Also test: http://localhost:xxxx (internal services), file:///etc/passwd
```

### Open redirect
```bash
curl -v "http://localhost:$PORT/redirect?url=http://evil.com"
# If Location header points to evil.com → open redirect (Important)
# Also test: url=//evil.com, url=javascript:alert(1)
```

### Path traversal
```bash
curl -v "http://localhost:$PORT/api/files/../../../etc/passwd"
curl -v "http://localhost:$PORT/api/files/..%2F..%2F..%2Fetc%2Fpasswd"
curl -v "http://localhost:$PORT/api/files/....//....//....//etc/passwd"
# If /etc/passwd contents returned → path traversal (Critical)
```

### Command injection
```bash
# If the app processes filenames or shell inputs:
curl -v -X POST http://localhost:$PORT/api/process \
  -H "Content-Type: application/json" \
  -d '{"filename": "test.txt; cat /etc/passwd"}'
curl -v -X POST http://localhost:$PORT/api/process \
  -H "Content-Type: application/json" \
  -d '{"filename": "test.txt$(whoami)"}'
curl -v -X POST http://localhost:$PORT/api/process \
  -H "Content-Type: application/json" \
  -d '{"filename": "test.txt| id"}'
# If command output appears in response → command injection (Critical)
```

### Session fixation
```bash
# Get a pre-login session ID:
SESSION1=$(curl -s -c - http://localhost:$PORT/login | grep session | awk '{print $NF}')
# Login with that session:
curl -v -b "session=$SESSION1" -c - -X POST http://localhost:$PORT/login \
  -d '{"user":"admin","pass":"admin"}'
# Get post-login session ID:
SESSION2=$(curl -s -b "session=$SESSION1" -c - http://localhost:$PORT/dashboard | grep session | awk '{print $NF}')
# If SESSION1 == SESSION2 → session fixation (Important)
# Expected: server rotates session ID on login
```

## Expanded edge case checks (v3.0 — 14 new categories)

Run the applicable categories based on artifact type. See `references/testing-landscape.md` for detailed test commands.

### Data integrity
```bash
# Create → update → delete cycle, verify state at each step:
ID=$(curl -s -X POST "$BASE/items" -H "Content-Type: application/json" -d '{"name":"test"}' | jq -r .id)
curl -s -X PUT "$BASE/items/$ID" -H "Content-Type: application/json" -d '{"name":"updated"}'
curl -s "$BASE/items/$ID" | jq -r .name  # should be "updated"
curl -s -X DELETE "$BASE/items/$ID"
curl -s -o /dev/null -w "%{http_code}" "$BASE/items/$ID"  # should be 404

# Concurrent writes — two updates to same record:
curl -s -X PUT "$BASE/items/$ID" -d '{"name":"a"}' &
curl -s -X PUT "$BASE/items/$ID" -d '{"name":"b"}' &
wait
curl -s "$BASE/items/$ID" | jq -r .name  # should be "a" or "b", not corrupted
```

### Idempotency
```bash
# Same POST twice — should not create duplicates:
RESULT1=$(curl -s -X POST "$BASE/charge" -H "Idempotency-Key: key123" -d '{"amount":100}')
RESULT2=$(curl -s -X POST "$BASE/charge" -H "Idempotency-Key: key123" -d '{"amount":100}')
# RESULT1 and RESULT2 should have the same ID — no double charge
```

### Cache invalidation
```bash
# Create a resource, GET it (cached), update it, GET again:
curl -s -X POST "$BASE/items" -d '{"name":"original"}' | jq -r .id
curl -s "$BASE/items/$ID"  # cached
curl -s -X PUT "$BASE/items/$ID" -d '{"name":"updated"}'
curl -s "$BASE/items/$ID" | jq -r .name  # should be "updated", not "original"
```

### Graceful shutdown
```bash
# Start a long request, send SIGTERM mid-flight:
curl -s -X POST "$BASE/slow-endpoint" &
REQUEST_PID=$!
sleep 0.5
kill -TERM $SERVER_PID
wait $REQUEST_PID
echo "Request exit: $?"  # Did it complete or was it cut off?
# Check: did the server finish in-flight work? Did it leave corrupt state?
```

### Connection pool exhaustion
```bash
# Fire many concurrent slow requests:
seq 1 100 | xargs -P 100 -I{} curl -s -o /dev/null -w "%{http_code}\n" "$BASE/slow-endpoint"
# Check: do requests hang? Does the server recover after?
```

### Locale/i18n
```bash
# Test date/number/currency formatting:
curl -s -H "Accept-Language: de-DE" "$BASE/format?number=1234.56"
# German: "1.234,56" — US: "1,234.56"
curl -s -H "Accept-Language: ja-JP" "$BASE/format?date=2024-01-15"
# Japanese: "2024年01月15日"
```

### Unicode normalization
```bash
# Composed (é = U+00E9) vs decomposed (e + combining accent = U+0065 U+0301):
# Register with composed, login with decomposed — same user?
COMPOSED=$(python3 -c "print('caf\\u00e9')")
DECOMPOSED=$(python3 -c "print('cafe\\u0301')")
curl -s -X POST "$BASE/register" -d "{\"username\":\"$COMPOSED\"}"
curl -s -X POST "$BASE/login" -d "{\"username\":\"$DECOMPOSED\"}"
# Should succeed (same user) — if fails, normalization bug
```

### GraphQL depth/complexity
```bash
# Deeply nested query — should be rejected or limited:
curl -s -X POST "$BASE/graphql" -H "Content-Type: application/json" -d '{
  "query": "{ user { posts { comments { author { posts { comments { author { posts { comments { author { id } } } } } } } } } } }"
}'
# If it processes without error/limit → DoS vulnerability (Important)
```

### API versioning
```bash
# Compare v1 and v2 behavior:
curl -s "$BASE/v1/items" | jq .
curl -s "$BASE/v2/items" | jq .
# Are breaking changes documented? Does v1 still work?
```

### Pagination cursor drift
```bash
# Get page 1, insert a new record, get page 2:
PAGE1=$(curl -s "$BASE/items?page=1&limit=5" | jq -r '.[].id')
curl -s -X POST "$BASE/items" -d '{"name":"inserted"}'
PAGE2=$(curl -s "$BASE/items?page=2&limit=5" | jq -r '.[].id')
# Check: is the inserted record duplicated or skipped on page 2?
```

### Rate limiting
```bash
# Send rapid requests, check for 429:
for i in $(seq 1 100); do
  curl -s -o /dev/null -w "%{http_code}\n" "$BASE/items"
done | sort | uniq -c
# Should see 429 after threshold. Check: does limit reset after window?
```

### WebSocket reconnection
```bash
# Connect, receive state, disconnect, reconnect, verify state sync:
python3 -c "
import asyncio, websockets
async def test():
    async with websockets.connect('ws://localhost:$PORT/ws') as ws:
        await ws.send('hello')
        state1 = await ws.recv()
    # Reconnect
    async with websockets.connect('ws://localhost:$PORT/ws') as ws:
        state2 = await ws.recv()
        print(f'State synced: {state1 == state2}')
asyncio.run(test())
"
```

### Upgrade/migration
```bash
# If the artifact has a DB with schema migrations:
# 1. Start old version, insert test data
# 2. Stop, start new version (runs migrations)
# 3. Verify old data is accessible and correct
# This requires having both versions — if not available, note as untested.
```

### Recovery
```bash
# Start the server, create data, kill -9, restart, verify data:
curl -s -X POST "$BASE/items" -d '{"name":"persist-test"}' | jq -r .id
kill -9 $SERVER_PID
# Restart
$START_COMMAND &
# Wait for health
curl -s "$BASE/items/$ID" | jq -r .name  # should be "persist-test"
```

## Performance smoke

Run on servers, APIs, and daemons. Skip for CLI tools and libraries (unless the spec specifies performance requirements).

### Response time
```bash
time curl -s -o /dev/null http://localhost:$PORT/api/items
time curl -s -o /dev/null -X POST http://localhost:$PORT/api/items \
  -H "Content-Type: application/json" -d '{"name":"perf-test"}'
# Flag anything over 2 seconds for an interactive operation.
```

### Smoke load
```bash
wrk -t2 -c10 -d30s http://localhost:$PORT/api/health
# Or with ab:
ab -n 100 -c 10 http://localhost:$PORT/api/health
# Flag if: p95 latency > 1s, error rate > 0, throughput near-zero under trivial load
```

### Degradation under concurrency
```bash
seq 1 10 | xargs -P 10 -I{} curl -s -o /dev/null -w "%{http_code}\n" \
  http://localhost:$PORT/api/items
# Any non-2xx response = finding. Any hang = Critical.
```

## Accessibility smoke (webapps only)

Skip for non-webapp artifacts.

### Automated scan
```bash
# After browser_navigate + browser_snapshot, check for:
# - Missing labels on inputs
# - Missing alt text on images
# - Buttons without accessible names

# Or use axe-core via headless browser:
npx @axe-core/cli http://localhost:$PORT --tags wcag2a,wcag2aa
# Flag any violations (Important for WCAG A, Minor for AA).
```

### Keyboard navigation
```python
browser_navigate(url="http://localhost:$PORT")
for i in range(20):
    browser_press(key="Tab")
    snapshot = browser_snapshot()
    # Can you reach every interactive element?
    # Does focus move in a logical order?
    # Is the focused element visually indicated?
```

### Visual contrast
```python
browser_vision(question="Is there any text on this page with low contrast against its background?")
```

## What to escalate to a specialist

| Finding type | QA action | Specialist handoff |
|---|---|---|
| Security vulnerability found in smoke/depth | File finding, note "needs pentest confirmation" | AppSec / pentest team |
| Performance degradation under smoke load | File finding with metrics | Performance engineering |
| axe-core violations | File findings with axe output | WCAG compliance audit |
| Suspicious behavior but can't confirm exploit | File as Note with evidence | Security review |
