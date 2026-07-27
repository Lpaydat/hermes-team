# API Prototype Verification — curl assertion pitfalls

When writing ad-hoc verification scripts for FastAPI/Flask prototypes, two
assertion patterns produce systematic false negatives. Both surfaced while
building the MCP Auth prototype (2026-07-24) and cost a debug round-trip.

## Pitfall 1 — FastAPI emits compact JSON (no space after colon)

FastAPI's default JSON serializer omits the space after `:` and `,`.

```
Response:  {"active":true,"scope":"srv:tool:read","idp":"entra"}
NOT:       {"active": true, "scope": "srv:tool:read", "idp": "entra"}
```

A `grep '"active": true'` assertion FAILS on the compact form even though the
response is correct.

**Fix:** never space-match on JSON values. Either:

1. **Preferred — parse + assert structurally** (spacing-proof and type-safe):
   ```bash
   echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['active']==True"
   ```

2. If you must grep, match the compact form: `grep '"active":true'`.

## Pitfall 2 — `curl -sf` swallows HTTP 4xx/5xx error bodies

`curl -f` (fail silently) discards the response body on HTTP errors (>= 400)
and returns non-zero. You cannot assert on the error message of a deliberate
rejection — e.g. testing that the token endpoint refuses an unapproved server.

```bash
# WRONG — -sf discards the 403 body, so "not approved" is never found
BODY=$(curl -sf -X POST .../oauth/token -d '{...pending server...}')
echo "$BODY" | grep "not approved"   # FAILS — body is empty

# RIGHT — drop -f so the error body is captured
BODY=$(curl -s -X POST .../oauth/token -d '{...pending server...}')
echo "$BODY" | grep "not approved"   # passes — {"detail":"server X is not approved"}
```

**Rule of thumb:**
- `curl -sf` for **happy-path** assertions (a 4xx/5xx IS a test failure).
- Plain `curl -s` for **negative-path** assertions (you are deliberately
  triggering and inspecting an error response).

## Pitfall 3 — DOM clicks may not reflect async state mutations

When browser-testing the HTML viewer accompanying an API prototype, a
`browser_click` may register the click but not visibly update the DOM before
the snapshot is taken (async fetch + re-render race). More reliable:

1. `browser_navigate` → check `browser_console` returns zero JS errors.
2. Instead of clicking a button, call the page's own handler directly:
   ```js
   approveServer('srv_x').then(()=>{window.__r=STATE})
   ```
   Then read back `window.__r` to confirm the state mutation landed.

This bypasses the click→render race and gives deterministic state inspection.
Note: `browser_console(expression=...)` lets you run arbitrary JS in the page
context — use it to invoke the page's async functions against live state and
read back computed styles or data attributes for visual assertions.
