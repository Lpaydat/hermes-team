---
name: qa-security
description: "Use when running security depth checks and non-functional smoke tests against a running artifact. Tests CSRF, XSS, SSRF, path traversal, command injection, session fixation, plus performance smoke and accessibility. Posts results to the swarm blackboard. Loaded by the security worker in a QA swarm."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [qa, security, non-functional, performance, accessibility, chaos]
    related_skills: [qa-protocol]
---

# QA Security — security depth + non-functional smoke

You run security depth checks and non-functional smoke tests against the running artifact. These catch vulnerabilities and regressions that functional claim testing misses.

## Read your assignment

Your card body contains:
- The container image tag and port (or workspace path)
- Which checks apply (security always; performance for servers/APIs; accessibility for webapps)

## Security depth

### CSRF (Cross-Site Request Forgery)
```bash
# POST without CSRF token — should be rejected
curl -v -X POST http://localhost:<port>/api/profile \
  -H "Cookie: session=<valid_session>" \
  -H "Content-Type: application/json" \
  -d '{"name": "hacked"}'
# If 200 → CSRF vulnerability
```

### XSS (Cross-Site Scripting)
```bash
# Inject script in every input field
PAYLOAD='<script>alert(document.cookie)</script>'
curl -v -X POST http://localhost:<port>/api/users \
  -H "Content-Type: application/json" \
  -d "{\"name\": \"$PAYLOAD\"}"
# Fetch the page that renders it — is the script unescaped?
curl -s http://localhost:<port>/users/1 | grep -i "<script>"
```

### SSRF (Server-Side Request Forgery)
```bash
# Does the server fetch arbitrary URLs?
curl -v -X POST http://localhost:<port>/api/avatar \
  -d '{"url": "http://169.254.169.254/latest/meta-data/"}'
# Does it fetch localhost?
curl -v -X POST http://localhost:<port>/api/import \
  -d '{"url": "http://localhost:8080/admin"}'
```

### Open redirect
```bash
curl -v "http://localhost:<port>/redirect?url=http://evil.com"
curl -v "http://localhost:<port>/redirect?url=//evil.com"
# If Location header points to evil.com → open redirect
```

### Path traversal
```bash
curl -v "http://localhost:<port>/api/files/../../../etc/passwd"
curl -v "http://localhost:<port>/api/files/..%2F..%2F..%2Fetc%2Fpasswd"
```

### Command injection
```bash
curl -v -X POST http://localhost:<port>/api/process \
  -d '{"filename": "test.txt; cat /etc/passwd"}'
curl -v -X POST http://localhost:<port>/api/process \
  -d '{"filename": "test.txt$(whoami)"}'
```

### Session fixation
```bash
# Get session ID before login, login with it, check if ID rotated
SESSION1=$(curl -s -c - http://localhost:<port>/login | grep session | awk '{print $NF}')
curl -v -b "session=$SESSION1" -X POST http://localhost:<port>/login -d '{"user":"admin","pass":"admin"}'
# If session ID unchanged after login → session fixation
```

### Security smoke (from v2.0)
- **IDOR:** change an ID in a request — can you read another user's data?
- **Auth bypass:** access protected resource without token, or with tampered token
- **Secrets in output:** check logs and responses for API keys, passwords, tokens
- **Dependency scan:** `npm audit`, `pip-audit`, `cargo audit`, or Trivy if available

## Performance smoke

### Response time
```bash
time curl -s -o /dev/null http://localhost:<port>/api/items
# Flag anything over 2 seconds for interactive operations
```

### Smoke load
```bash
wrk -t2 -c10 -d30s http://localhost:<port>/api/health
# or: ab -n 100 -c 10 http://localhost:<port>/api/health
# Flag if p95 > 1s or error rate > 0
```

### Degradation under concurrency
```bash
seq 1 10 | xargs -P 10 -I{} curl -s -o /dev/null -w "%{http_code}\n" http://localhost:<port>/api/items
# Any non-2xx = finding. Any hang = P0.
```

## Accessibility (webapps only)

### Keyboard navigation
```python
browser_navigate(url="http://localhost:<port>")
for i in range(20):
    browser_press(key="Tab")
    # Can you reach every interactive element? Logical order?
```

### Visual contrast
```python
browser_vision(question="Is there any text with low contrast against its background?")
```

## Post results to blackboard

```bash
hermes kanban comment <root_card_id> --author qa-security \
  --body '[swarm:blackboard] {"key": "security_findings", "value": {"csrf": "pass", "xss": "fail", "xss_evidence": "...", "perf_p95": "120ms", "a11y": "pass"}}'
```

## Complete with metadata

```python
kanban_complete(
    summary="Security: 7 depth checks + 3 perf + 2 a11y. 1 finding (XSS stored in user profile).",
    metadata={
        "checks_run": ["csrf", "xss", "ssrf", "open_redirect", "path_traversal", "command_injection", "session_fixation", "idor", "auth_bypass", "secrets", "dep_scan", "perf_timing", "perf_load", "a11y_keyboard", "a11y_contrast"],
        "findings": [{"severity": "P0", "type": "xss", "evidence": "..."}],
        "checks_passed": 14,
        "checks_failed": 1
    }
)
```

## What to escalate to a specialist

| Finding | QA action | Specialist |
|---|---|---|
| Security vuln in smoke | File finding, note "needs pentest confirmation" | AppSec |
| Perf degradation | File finding with metrics | Perf engineering |
| a11y violations | File findings with axe output | WCAG audit |
