---
name: qa-security
description: "Use when running security probes and non-functional smoke against a running artifact. CSRF, XSS, SSRF, path traversal, command injection, session fixation, plus performance smoke and accessibility. Posts results to the swarm blackboard."
version: 1.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [qa, security, non-functional, performance, accessibility]
    related_skills: [qa-protocol]
---

# QA Security — probe and smoke

You **probe** the running artifact for vulnerabilities and run non-functional smoke checks. Each probe either passes, fails (becomes a finding), or is skipped (not applicable — note why).

## Read your assignment

Your card body contains the container image tag and port, and which checks apply (security always; performance for servers/APIs; accessibility for webapps).

## Security probes

### CSRF
```bash
curl -v -X POST http://localhost:<port>/api/profile \
  -H "Cookie: session=<valid_session>" -H "Content-Type: application/json" \
  -d '{"name": "hacked"}'
# 200 → CSRF vulnerability
```

### XSS
```bash
PAYLOAD='<script>alert(document.cookie)</script>'
curl -v -X POST http://localhost:<port>/api/users \
  -H "Content-Type: application/json" -d "{\"name\": \"$PAYLOAD\"}"
curl -s http://localhost:<port>/users/1 | grep -i "<script>"
```

### SSRF
```bash
curl -v -X POST http://localhost:<port>/api/avatar \
  -d '{"url": "http://169.254.169.254/latest/meta-data/"}'
curl -v -X POST http://localhost:<port>/api/import \
  -d '{"url": "http://localhost:8080/admin"}'
```

### Open redirect
```bash
curl -v "http://localhost:<port>/redirect?url=http://evil.com"
# Location header → evil.com = open redirect
```

### Path traversal
```bash
curl -v "http://localhost:<port>/api/files/../../../etc/passwd"
curl -v "http://localhost:<port>/api/files/..%2F..%2F..%2Fetc%2Fpasswd"
```

### Command injection
```bash
curl -v -X POST http://localhost:<port>/api/process -d '{"filename": "test.txt; cat /etc/passwd"}'
curl -v -X POST http://localhost:<port>/api/process -d '{"filename": "test.txt$(whoami)"}'
```

### Session fixation
```bash
SESSION1=$(curl -s -c - http://localhost:<port>/login | grep session | awk '{print $NF}')
curl -v -b "session=$SESSION1" -X POST http://localhost:<port>/login -d '{"user":"admin","pass":"admin"}'
# Session ID unchanged after login → session fixation
```

### Security smoke
- **IDOR:** change an ID in a request — can you read another user's data?
- **Auth bypass:** access protected resource without token, or with tampered token
- **Secrets in output:** check logs and responses for API keys, passwords, tokens
- **Dependency scan:** `npm audit`, `pip-audit`, `cargo audit`, or Trivy if available

## Performance smoke

```bash
# Response time
time curl -s -o /dev/null http://localhost:<port>/api/items
# Flag > 2s for interactive operations

# Smoke load (30s)
wrk -t2 -c10 -d30s http://localhost:<port>/api/health
# Flag p95 > 1s or error rate > 0

# Degradation under concurrency
seq 1 10 | xargs -P 10 -I{} curl -s -o /dev/null -w "%{http_code}\n" http://localhost:<port>/api/items
# Non-2xx = finding. Hang = P0.
```

## Accessibility (webapps only)

```python
# Keyboard navigation
browser_navigate(url="http://localhost:<port>")
for i in range(20):
    browser_press(key="Tab")
    # Reach every interactive element? Logical order?

# Visual contrast
browser_vision(question="Is there any text with low contrast against its background?")
```

## Post results to blackboard

```bash
hermes kanban comment <root_card_id> --author qa-security \
  --body '[swarm:blackboard] {"key": "security_findings", "value": {"csrf": "pass", "xss": "fail", "xss_evidence": "...", "perf_p95": "120ms", "a11y": "pass"}}'
```

Complete with `kanban_complete(metadata={checks_run: [...], findings: [...], checks_passed: N, checks_failed: N})`.

## Specialist handoffs

| Finding | QA action | Specialist |
|---|---|---|
| Security vuln | File finding, note "needs pentest confirmation" | AppSec |
| Perf degradation | File finding with metrics | Perf engineering |
| a11y violations | File findings with output | WCAG audit |
