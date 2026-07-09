# Non-Functional Smoke Checks

Cheap, fast checks that catch regressions the functional claims miss. Each check passes, fails (becomes a finding), or is skipped (not applicable — note the reason).

Full penetration testing, load engineering, and WCAG certification are specialist handoffs. QA runs the smoke level only.

## Security smoke

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

# Expired token (if expiry is configurable, set it to 1s ago):
# Create a token with 1s expiry, wait 2s, try to use it
```

### Secrets in output
```bash
# Check API responses for sensitive fields:
curl -s http://localhost:$PORT/api/users | grep -iE "password|secret|token|api.?key|private"

# Check server logs:
tail -100 /var/log/<app>.log | grep -iE "password|secret|token|api.?key|private"

# Check error messages (trigger an error, see if it leaks stack traces):
curl -s http://localhost:$PORT/api/items/999999999
# A stack trace in the response = Important finding
```

### Dependency scan
```bash
# Run whichever is configured for this project:
npm audit 2>&1 | head -20           # Node.js
pip-audit 2>&1 | head -20           # Python
cargo audit 2>&1 | head -20         # Rust
trivy fs . 2>&1 | head -30          # Generic (if installed)

# Flag any HIGH or CRITICAL vulnerability as a finding.
# LOW/MODERATE = Note severity.
```

## Performance smoke

Run on servers, APIs, and daemons. Skip for CLI tools and libraries (unless the spec specifies performance requirements).

### Response time
```bash
# Time key operations:
time curl -s -o /dev/null http://localhost:$PORT/api/items
time curl -s -o /dev/null -X POST http://localhost:$PORT/api/items \
  -H "Content-Type: application/json" -d '{"name":"perf-test"}'

# Flag anything over 2 seconds for an interactive operation.
# For background/batch operations, check against the spec's stated SLA.
```

### Smoke load
```bash
# 30-second load test on the main endpoint:
wrk -t2 -c10 -d30s http://localhost:$PORT/api/health
# Or with ab:
ab -n 100 -c 10 http://localhost:$PORT/api/health

# Flag if:
# - p95 latency > 1 second
# - Error rate > 0
# - Throughput drops to near-zero under trivial load
```

### Degradation under concurrency
```bash
# Fire 10 simultaneous requests, check all succeed:
seq 1 10 | xargs -P 10 -I{} curl -s -o /dev/null -w "%{http_code}\n" \
  http://localhost:$PORT/api/items

# Any non-2xx response = finding. Any hang = Critical.
```

## Accessibility smoke (webapps only)

Skip for non-webapp artifacts.

### Automated scan
```bash
# Install axe-core if not present:
npm install -g axe-core

# Run against the running webapp:
# Option 1: Use the browser's built-in accessibility tree
# After browser_navigate + browser_snapshot, check for:
# - Missing labels on inputs
# - Missing alt text on images
# - Buttons without accessible names

# Option 2: Use axe-core via headless browser
npx @axe-core/cli http://localhost:$PORT --tags wcag2a,wcag2aa
# Flag any violations as findings (Important for WCAG A, Minor for AA).
```

### Keyboard navigation
```python
# Tab through the main user flow:
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
# Take a screenshot and check for obviously low-contrast text:
browser_vision(question="Is there any text on this page with low contrast against its background? Look for light-gray text on white, or dark text on dark backgrounds.")
```

## What to escalate to a specialist

| Finding type | QA action | Specialist handoff |
|---|---|---|
| Security vulnerability found in smoke | File finding, note "needs pentest confirmation" | AppSec / pentest team |
| Performance degradation under smoke load | File finding with metrics | Performance engineering |
| axe-core violations | File findings with axe output | WCAG compliance audit |
| Suspicious behavior but can't confirm exploit | File as Note with evidence | Security review |
