---
name: qa-functional
description: "Use when testing functional claims against a running artifact. Proves or disproves each claim with the two-pass approach (smoke all first, deep-test passing ones). Applies 36 edge case categories. Posts verdicts to the swarm blackboard. Loaded by the functional worker in a QA swarm."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [qa, functional, claims, edge-cases, two-pass]
    related_skills: [qa-protocol]
---

# QA Functional — prove every claim by running it

You test functional claims against the running artifact. Every claim gets a verdict: _proven_, _disproven_, or _untested_.

## Read your assignment

Your card body contains:
- The claims checklist (from the orchestrator's plan)
- The container image tag and port (or workspace path for stateless artifacts)
- The risk ranking (P0-P4) for each claim

## Two-pass approach

### Pass 1 — Smoke all claims (fast)

For each claim, run the happy path only. Quick PASS/FAIL.

If a core claim's happy path fails, file immediately (P0) and skip its edge cases — a disproven core claim blocks everything downstream.

**Done when:** every claim has a smoke verdict.

### Pass 2 — Deep test passing claims

For each claim that passed smoke, apply edge cases. Depth is determined by risk:

| Risk | Depth | Edge cases |
|---|---|---|
| P0/P1 | Full | 10+ edge cases, degradation probes, concurrent access |
| P2 | Standard | 5 edge cases |
| P3/P4 | Smoke only | Happy path (already done in Pass 1) |

**Done when:** every claim has a final verdict with evidence.

## Universal edge case categories (10)

Apply systematically to each claim:

1. **Empty/zero/null input** — empty string, 0, null/None, empty list, missing fields
2. **Maximum/boundary input** — very long strings, max int, buffer boundaries (1024, 4096, 65535), off-by-one
3. **Special characters** — unicode (é, 日本語, 🎉), quotes, backslashes, null bytes, SQL/HTML injection strings
4. **Concurrency** — simultaneous requests, race conditions, parallel file access
5. **Restart/reconnect** — kill mid-operation, restart, reconnect after server restart
6. **Resource exhaustion** — disk full, too many open files, OOM (test cautiously)
7. **Network failure** — timeout, connection refused, DNS failure, slow network
8. **Time/date** — timezone changes, DST, epoch boundaries, future/past dates
9. **Authorization/auth** — unauthenticated, wrong credentials, expired tokens, role escalation
10. **Rapid repeated input** — double-submit, rapid clicks, replay attacks

## Expanded edge case categories (14)

Apply based on artifact type:

| # | Category | What to test | Applies to |
|---|---|---|---|
| 11 | **Data integrity** | Create→update→delete cycles, concurrent writes, cascade, orphaned records | API, daemon, DB-backed |
| 12 | **Idempotency** | Same request twice = same result | API, payments, webhooks |
| 13 | **Cache invalidation** | Stale data after update | API, webapps, CDNs |
| 14 | **Graceful shutdown** | SIGTERM mid-request — in-flight work finished? | API, daemons |
| 15 | **Connection pool exhaustion** | All connections used, new request hangs | API, daemons |
| 16 | **Locale/i18n** | Date/number/currency format differences | API, webapps, CLI |
| 17 | **Unicode normalization** | Composed vs decomposed chars — login mismatch | API, webapps, libraries |
| 18 | **GraphQL depth** | Deeply nested query DoS | GraphQL APIs |
| 19 | **API versioning** | v1 vs v2 behavior — backward compat | API servers |
| 20 | **Pagination drift** | New records during pagination — skip or duplicate | API, webapps |
| 21 | **Rate limiting** | Threshold, reset, 429 response | API servers |
| 22 | **WebSocket reconnection** | Disconnect → reconnect → state sync | API, daemons, webapps |
| 23 | **Upgrade/migration** | Schema migration breaks existing data | API, daemons, DB-backed |
| 24 | **Recovery** | Crash → restart → state intact | All stateful |

## Program type dispatch

Load the matching reference from the `live-testing` skill directory for type-specific test patterns:

| Type | Reference |
|---|---|
| CLI | `references/cli-testing.md` |
| API server | `references/api-server-testing.md` |
| Webapp | `references/webapp-testing.md` |
| TUI | `references/tui-testing.md` |
| Mobile | `references/mobile-app-testing.md` |
| Blockchain | `references/blockchain-testing.md` |
| Daemon | `references/daemon-testing.md` |
| Library | `references/library-testing.md` |

## Post results to blackboard

After testing, post structured results to the root card:

```bash
hermes kanban comment <root_card_id> --author qa-functional \
  --body '[swarm:blackboard] {"key": "functional_verdicts", "value": {"claim_1": {"verdict": "proven", "evidence": "..."}, "claim_2": {"verdict": "disproven", "evidence": "...", "severity": "P1"}}}'
```

## Complete with metadata

```python
kanban_complete(
    summary="Functional: 15 claims tested, 13 proven, 2 disproven (1x P1, 1x P2)",
    metadata={
        "verdicts": [{"claim_id": 1, "verdict": "proven"}, ...],
        "findings": [{"severity": "P1", "claim": "...", "evidence": "..."}],
        "claims_tested": 15,
        "claims_proven": 13
    }
)
```

## Evidence

- Short evidence (curl output, exit codes) → inline in blackboard JSON
- Long evidence (full logs) → `/tmp/qa-evidence/<card-id>/` + path in blackboard
- Every disproven claim MUST have evidence — actual output, not your summary
