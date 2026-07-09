# Testing Landscape — Complete Reference

What lies beyond the 10 universal edge case categories and the current 8-phase protocol. Use when designing a test plan (Phase 1), expanding edge case coverage (Phase 3), or deciding whether a testing dimension is QA's responsibility or a specialist handoff.

## Edge case universe (beyond the 10 universal categories)

### Data & State
- **Data migration** — schema changes break existing data (add NOT NULL column to populated table). Applies to: API servers, daemons, DB-backed apps.
- **Schema versioning** — old clients send old schema, new server expects new. Applies to: API servers, libraries.
- **Orphaned records** — delete parent, child remains (delete user but posts remain; FK not cascading). Applies to: API servers, daemons.
- **Cascade delete** — deleting one record triggers mass deletion — intended or not? Applies to: API servers, daemons.
- **Transaction isolation** — concurrent transactions see stale/dirty data (two users book the last seat). Applies to: API servers, daemons, brokers.
- **Deadlock** — two operations wait on each other (transfer A→B and B→A simultaneously lock both rows). Applies to: API servers, daemons.
- **Idempotency** — same request twice produces different results (POST /charge called twice = double charge). Applies to: API servers, payment systems.
- **Pagination cursor drift** — new records inserted during pagination (page 1 shows items 1-10, item 11 inserted before page 2 → skip or duplicate). Applies to: API servers, webapps.
- **Cache invalidation** — stale data served from cache after update (update user name, but GET returns old name). Applies to: API servers, webapps, CDNs.
- **Cache stampede** — cache expires, 1000 requests hit DB simultaneously. Applies to: API servers, daemons.

### API & Protocol
- **API versioning** — v1 endpoint behaves differently from v2. Applies to: API servers.
- **Rate limiting** — requests above threshold blocked or delayed (100 req/min → 429 on 101st; does limit reset correctly?). Applies to: API servers.
- **Content negotiation** — server returns different format based on Accept header. Applies to: API servers.
- **HTTP method override** — `X-HTTP-Method-Override: DELETE` on a POST — does server honor it? Bypass auth? Applies to: API servers.
- **GraphQL depth/complexity** — deeply nested query causes DoS. Applies to: GraphQL APIs.
- **WebSocket reconnection** — client disconnects, reconnects — state sync? Applies to: API servers, daemons, webapps.
- **Partial request** — client sends half a request, disconnects. Applies to: API servers.

### Security (beyond smoke)
- **CSRF** — cross-site request forgery (POST form from evil.com with victim's cookie). Applies to: webapps, API servers with cookie auth.
- **XSS** — script injection in output (`<script>alert(1)</script>` in user name, rendered in profile). Applies to: webapps.
- **SSRF** — server makes request to attacker-controlled URL (avatar URL = `http://169.254.169.254/latest/meta-data/`). Applies to: API servers, webapps.
- **Open redirect** — redirect URL taken from user input without validation (`/redirect?url=http://evil.com`). Applies to: webapps, API servers.
- **Path traversal** — `../` in file path escapes intended directory. Applies to: API servers, CLI tools, daemons.
- **Command injection** — user input passed to shell (filename `; rm -rf /` passed to `os.system()`). Applies to: CLI tools, daemons, API servers.
- **Session fixation** — attacker sets session ID before login. Applies to: webapps, API servers.
- **Race condition in auth** — TOCTOU: check permission then act, state changes between. Applies to: API servers, payment systems.

### Distributed Systems
- **Clock skew** — different servers have different clocks (token expires at 12:00 on server A, 12:05 on server B). Applies to: API servers, daemons, distributed systems.
- **Split-brain** — network partition causes two leaders. Applies to: daemons, brokers, distributed DBs.
- **Network partition** — nodes can't communicate but keep serving. Applies to: daemons, API servers, brokers.
- **Circuit breaker** — protection mechanism trips — does it recover? Applies to: API servers, daemons, microservices.
- **Retry storm** — failed request retried by multiple layers simultaneously. Applies to: API servers, daemons.
- **Thundering herd** — all instances restart simultaneously and hit DB. Applies to: API servers, daemons.
- **Zombie processes** — child processes don't die after parent exits. Applies to: daemons, CLI tools.
- **FD leak** — file descriptors not closed (run for 1 hour → "Too many open files"). Applies to: daemons, API servers.
- **Memory leak** — memory grows unbounded over time (run for 24h under load → OOM kill). Applies to: daemons, API servers.

### Input & Encoding
- **Unicode normalization** — `é` (composed) vs `é́` (decomposed) treated differently. Applies to: API servers, webapps, libraries.
- **Collation** — sort order differs by locale (`ä` sorts after `a` in German, after `z` in Swedish). Applies to: API servers, libraries.
- **Locale/i18n** — date/number/currency format differs (`1,000.00` US vs `1.000,00` DE). Applies to: API servers, webapps, CLI tools.
- **File encoding** — UTF-8 vs UTF-16 vs Latin-1. Applies to: API servers, CLI tools, libraries.
- **MIME type mismatch** — file extension says .jpg, content is .exe. Applies to: API servers, webapps.

### Lifecycle
- **Graceful shutdown** — SIGTERM during active request (server killed mid-write → partial data?). Applies to: API servers, daemons.
- **Startup race** — service starts before dependencies are ready. Applies to: API servers, daemons.
- **Config reload** — hot-reload config without restart. Applies to: daemons, API servers.
- **Connection pool exhaustion** — all connections in use, new request waits. Applies to: API servers, daemons.

## Testing type taxonomy

### Functional
| Type | Post-merge live? |
|------|-----------------|
| Unit | No (verifier) |
| Integration | No (verifier) |
| Functional | **Yes** |
| End-to-end / journey | **Yes** |
| Smoke | **Yes** |
| Sanity | **Yes** |
| Regression | Conditional (QA spot-checks, verifier owns suite) |
| Acceptance | **Yes** |
| Exploratory | **Yes** |

### Non-functional
| Type | Post-merge live? |
|------|-----------------|
| Performance / load | **Yes** (smoke level) |
| Stress | Conditional (specialist for deep) |
| Security / pentest | **Yes** (smoke level) |
| Accessibility | **Yes** (webapps, smoke level) |
| Usability | **Yes** (observations, not verdicts) |
| Compatibility | **Yes** |
| Reliability | **Yes** |
| Data integrity | **Yes** |
| Recovery | **Yes** |
| Compliance | Conditional (specialist for certification) |

### Structural (not QA's job)
| Type | Post-merge live? |
|------|-----------------|
| Code coverage | No (verifier/dev) |
| Mutation testing | No (verifier) |

### Change-related
| Type | Post-merge live? |
|------|-----------------|
| Regression | Conditional |
| Upgrade / migration | **Yes** |
| A/B / canary | Conditional (requires staging) |

## v3.0 integration status

The following items were gaps in v2.0.0 and are now integrated into the v3.0 protocol:

| Gap | v3.0 status | Where |
|---|---|---|
| Security depth (CSRF, XSS, SSRF, path traversal, command injection, session fixation) | INTEGRATED | Phase 5, `references/non-functional-smoke-checks.md` §Security depth |
| Data integrity | INTEGRATED | Phase 3 expanded edge cases, `references/non-functional-smoke-checks.md` |
| Idempotency | INTEGRATED | Phase 3 expanded edge cases |
| Cache invalidation | INTEGRATED | Phase 3 expanded edge cases |
| Graceful shutdown | INTEGRATED | Phase 3 expanded edge cases, Phase 6 degradation |
| Connection pool exhaustion | INTEGRATED | Phase 3 expanded edge cases |
| Locale/i18n | INTEGRATED | Phase 3 expanded edge cases |
| Unicode normalization | INTEGRATED | Phase 3 expanded edge cases |
| GraphQL depth/complexity | INTEGRATED | Phase 3 expanded edge cases |
| API versioning | INTEGRATED | Phase 3 expanded edge cases |
| Pagination cursor drift | INTEGRATED | Phase 3 expanded edge cases |
| Rate limiting | INTEGRATED | Phase 3 expanded edge cases |
| WebSocket reconnection | INTEGRATED | Phase 3 expanded edge cases |
| Upgrade/migration | INTEGRATED | Phase 3 expanded edge cases |
| Recovery | INTEGRATED | Phase 3 expanded edge cases, Phase 6 |
| Chaos engineering (smoke level) | INTEGRATED | Phase 6 graceful degradation |
| Visual regression | OPTIONAL | BackstopJS/pixelmatch if available |
| Contract testing | OPTIONAL | Microservices only |

## What we're missing (gaps remaining after v3.0)

| Gap | Why it matters | QA owns or specialist? |
|-----|----------------|----------------------|
| **Security depth** (CSRF, XSS, SSRF, path traversal, command injection, session fixation) | Smoke checks IDOR + auth bypass + secrets. Missing active injection attacks. | **QA owns smoke-level**. Deep pentest = specialist. |
| **Data integrity** (create→update→delete cycles, concurrent writes, cascade) | We test individual claims but don't verify state consistency after operations. | **QA owns** |
| **Idempotency** (same request twice = same result) | Critical for payments, retries, webhooks. | **QA owns** |
| **Cache invalidation** (stale data after update) | Common production bug. | **QA owns** |
| **Graceful shutdown** (SIGTERM during active request) | Does server finish in-flight work? | **QA owns** |
| **Connection pool exhaustion** | Common scaling failure. | **QA owns** (smoke) |
| **Locale/i18n** (date/number/currency formats) | Affects global users. | **QA owns** |
| **Unicode normalization** (composed vs decomposed) | Login/registration mismatch. | **QA owns** |
| **GraphQL depth/complexity** (DoS via nested queries) | GraphQL-specific. | **QA owns** (for GraphQL) |
| **Upgrade/migration testing** (schema migration breaks data) | Critical for releases. | **QA owns** |
| **Chaos engineering** (kill deps, inject latency, partition) | Netflix pattern. Our degradation touches this but not systematically. | **QA owns smoke-level**. Deep chaos = specialist. |
| **Visual regression** (pixel-diff between builds) | For webapps. We do screenshots but not automated comparison. | Conditional — practical if BackstopJS available. |
| **Contract testing** (inter-service API drift) | Verifier checks code-level contracts. Runtime drift? | Conditional — microservices only. |
| **Recovery testing** (crash → restart → state intact) | Does the system self-heal? | **QA owns** |

## Chaos engineering — minimum for QA

### Kill a dependency
```bash
DB_PID=$(pgrep -f "postgres\|mysql\|redis\|mongod" | head -1)
curl -s http://localhost:$PORT/api/items &
sleep 0.5
kill -9 $DB_PID
curl -s -o /dev/null -w "%{http_code}" http://localhost:$PORT/api/items
# Restart and verify recovery
sudo systemctl start postgresql; sleep 2
curl -s http://localhost:$PORT/api/items
```

### Inject latency
```bash
sudo tc qdisc add dev eth0 root netem delay 500ms
time curl -s -o /dev/null -w "%{http_code}" http://localhost:$PORT/api/items
sudo tc qdisc del dev eth0 root
```

### Simulate network partition
```bash
sudo iptables -A OUTPUT -d <dependency_ip> -j DROP
curl -s http://localhost:$PORT/api/items
sudo iptables -D OUTPUT -d <dependency_ip> -j DROP
```

## Security testing depth — concrete payloads

### CSRF
```bash
curl -v -X POST http://localhost:$PORT/api/profile \
  -H "Cookie: session=<valid_session_cookie>" \
  -H "Content-Type: application/json" \
  -d '{"name": "hacked"}'
# If 200 → CSRF vulnerability
```

### XSS
```bash
PAYLOAD='<script>alert(document.cookie)</script>'
curl -v -X POST http://localhost:$PORT/api/users \
  -H "Content-Type: application/json" \
  -d "{\"name\": \"$PAYLOAD\"}"
curl -s http://localhost:$PORT/users/1 | grep -i "<script>"
# If found → stored XSS
```

### SSRF
```bash
curl -v -X POST http://localhost:$PORT/api/avatar \
  -d '{"url": "http://169.254.169.254/latest/meta-data/iam/security-credentials/"}'
# If server fetches it → SSRF
```

### Open redirect
```bash
curl -v "http://localhost:$PORT/redirect?url=http://evil.com"
# If Location header points to evil.com → open redirect
```

### Path traversal
```bash
curl -v "http://localhost:$PORT/api/files/../../../etc/passwd"
curl -v "http://localhost:$PORT/api/files/..%2F..%2F..%2Fetc%2Fpasswd"
```

### Command injection
```bash
curl -v -X POST http://localhost:$PORT/api/process \
  -d '{"filename": "test.txt; cat /etc/passwd"}'
curl -v -X POST http://localhost:$PORT/api/process \
  -d '{"filename": "test.txt$(whoami)"}'
```

### Session fixation
```bash
SESSION1=$(curl -s -c - http://localhost:$PORT/login | grep session | awk '{print $NF}')
curl -v -b "session=$SESSION1" -X POST http://localhost:$PORT/login -d '{"user":"admin","pass":"admin"}'
SESSION2=$(curl -s -b "session=$SESSION1" -c - http://localhost:$PORT/dashboard | grep session | awk '{print $NF}')
# If SESSION1 == SESSION2 → session fixation
```

## Test planning methodologies

| Method | Predictability for agent | Notes |
|--------|--------------------------|-------|
| **Risk-based testing** | HIGH | Risk ranking is algorithmic (likelihood × impact). Deterministic, reproducible. Best for agent. |
| **SBET** | MEDIUM | Charter is deterministic, exploration is creative. Structure helps. |
| **Heuristic testing** | MEDIUM | Our 10 universal edge cases ARE heuristics. Coverage depends on which apply. |
| **Rapid Software Testing** | LOW | Heavily human-judgment-based. Agent can apply heuristics but "critical thinking" is hard. |

**Recommendation:** Risk-based testing as the planning framework (Phase 1), with SBET charters for high-risk areas (Phase 6).
