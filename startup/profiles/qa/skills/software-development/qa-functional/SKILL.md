---
name: qa-functional
description: "Use when testing functional claims against a running artifact. Two-pass: smoke all claims fast, then deep-test passing ones with 36 edge case categories. Posts verdicts to the swarm blackboard."
version: 1.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [qa, functional, claims, edge-cases, two-pass]
    related_skills: [qa-protocol]
---

# QA Functional — prove every claim

The **claim** is the atom: a specific, pass/fail assertion extracted from the spec. Every claim gets a **verdict** — _proven_, _disproven_, or _untested_ — backed by evidence you personally observed.

## Read your assignment

Your card body contains the claims checklist (with P0–P4 risk ranking), the container image tag and port, or the workspace path for stateless artifacts.

## Two-pass

### Pass 1 — Smoke all claims

Run the happy path for every claim. Quick PASS/FAIL. If a core claim's happy path fails, file immediately (P0) and skip its edge cases.

**Done when:** every claim has a smoke verdict.

### Pass 2 — Deep-test passing claims

Apply edge cases to claims that passed smoke. Depth by risk:

| Risk | Depth |
|---|---|
| P0/P1 | 10+ edge cases, degradation probes, concurrent access |
| P2 | 5 edge cases |
| P3/P4 | Smoke only (done in Pass 1) |

**Done when:** every claim has a final verdict with evidence.

## Universal edge cases (10)

1. **Empty/zero/null** — empty string, 0, null/None, empty list, missing fields
2. **Boundary** — very long strings, max int, buffer sizes (1024, 4096, 65535), off-by-one
3. **Special characters** — unicode (é, 日本語, 🎉), quotes, backslashes, null bytes, injection strings
4. **Concurrency** — simultaneous requests, race conditions, parallel writes
5. **Restart** — kill mid-operation, restart, reconnect
6. **Resource exhaustion** — disk full, too many open files, OOM (cautiously)
7. **Network failure** — timeout, connection refused, DNS failure, slow network
8. **Time/date** — timezone changes, DST, epoch boundaries, future/past dates
9. **Auth** — unauthenticated, wrong credentials, expired tokens, role escalation
10. **Rapid input** — double-submit, rapid clicks, replay attacks

## Expanded edge cases (14)

Apply based on artifact type:

| # | Category | Applies to |
|---|---|---|
| 11 | **Data integrity** — create→update→delete cycles, cascade, orphaned records | API, daemon, DB-backed |
| 12 | **Idempotency** — same request twice = same result | API, payments, webhooks |
| 13 | **Cache invalidation** — stale data after update | API, webapps, CDNs |
| 14 | **Graceful shutdown** — SIGTERM mid-request | API, daemons |
| 15 | **Connection pool exhaustion** — all connections used, new request hangs | API, daemons |
| 16 | **Locale/i18n** — date/number/currency format differences | API, webapps, CLI |
| 17 | **Unicode normalization** — composed vs decomposed chars | API, webapps, libraries |
| 18 | **GraphQL depth** — deeply nested query DoS | GraphQL APIs |
| 19 | **API versioning** — v1 vs v2 backward compat | API servers |
| 20 | **Pagination drift** — new records during pagination | API, webapps |
| 21 | **Rate limiting** — threshold, reset, 429 | API servers |
| 22 | **WebSocket reconnection** — disconnect → reconnect → state sync | API, daemons, webapps |
| 23 | **Upgrade/migration** — schema migration breaks data | API, daemons, DB-backed |
| 24 | **Recovery** — crash → restart → state intact | All stateful |

## Program type dispatch

Load the matching reference from the `live-testing` skill directory for type-specific test patterns: `references/cli-testing.md`, `references/api-server-testing.md`, `references/webapp-testing.md`, `references/tui-testing.md`, `references/mobile-app-testing.md`, `references/blockchain-testing.md`, `references/daemon-testing.md`, `references/library-testing.md`.

## Post verdicts to blackboard

```bash
hermes kanban comment <root_card_id> --author qa-functional \
  --body '[swarm:blackboard] {"key": "functional_verdicts", "value": {"claim_1": {"verdict": "proven"}, "claim_2": {"verdict": "disproven", "severity": "P1", "evidence": "..."}}}'
```

Complete with `kanban_complete(metadata={verdicts: [...], findings: [...], claims_tested: N, claims_proven: N})`.

Every disproven claim MUST have evidence — actual output, not your summary. Short evidence goes inline in the blackboard JSON; long evidence goes to `/tmp/qa-evidence/<card-id>/` with the path in the blackboard.
