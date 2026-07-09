# Finding Severity Rubric (v3.0)

Every QA finding gets a severity. This lets the developer prioritize fixes and the tech-lead decide what blocks shipping. The severity system maps to Google's Buganizer P0–P4 priority levels for cross-org clarity.

## Severity levels

### Critical (P0/P1) — blocks shipping

The artifact cannot ship with this issue. Core functionality is broken, data is at risk, or security is compromised.

| Category | Examples |
|---|---|
| Core feature broken | Signup crashes, API returns 500 on valid input, CLI exits non-zero on success, app won't start |
| Data loss | Delete removes the wrong record, update overwrites unrelated data, crash corrupts state |
| Security hole | Auth bypass, IDOR (user B reads user A's data), SQL injection works, secrets in output |
| Data corruption | Concurrent writes corrupt records, restart loses committed data |
| Build failure | Artifact won't build from source |

**P0:** Launch blocker / data loss / security hole. Blocks everything.
**P1:** Major journey broken, no workaround. Blocks the main user flow.

**Action:** File as kanban card to `developer`. Block the QA card as dependency. The feature cannot ship until this is resolved.

### Important (P2) — should fix before ship

The artifact works but has a meaningful degradation. Shipping is possible but not recommended without fixing.

| Category | Examples |
|---|---|
| Broken edge case | Unicode in names causes display error, large input causes slowdown, timezone handling wrong |
| Wrong error handling | Returns 500 instead of 400 on bad input, error message is misleading, crash on malformed input |
| Performance issue | p95 > 2s on interactive operation, degrades under 10 concurrent requests |
| Broken user journey | Flow can't be completed due to a non-core step failing (e.g., can't delete after creating) |
| Accessibility (WCAG A) | Missing input labels, no keyboard focus indicator, images without alt text |
| Security (moderate) | Stack trace in error response, verbose logging of sensitive data, dependency with HIGH CVE |

**Action:** File as kanban card to `developer`. Include in the test report. The team decides whether to fix before ship or defer.

### Minor (P3) — can ship with

The artifact works correctly but has a cosmetic or low-impact issue. Shipping is fine.

| Category | Examples |
|---|---|
| Cosmetic | Off-by-one in pagination display, inconsistent button styling, typo in error message |
| Non-critical edge case | Extremely unlikely input (10000-char filename) causes a minor display glitch |
| Performance (minor) | p95 is 1.5s (under 2s threshold but not snappy) |
| Accessibility (WCAG AA) | Color contrast slightly below AA threshold on a non-essential element |

**Action:** File as kanban card to `developer` or note in the test report. Ship is not blocked.

### Note (P4) — observation, not a bug

The artifact behaves correctly, but something is worth flagging to the team. Not actionable as a bug fix.

| Category | Examples |
|---|---|
| UX feedback | Flow is confusing, error message is unhelpful but technically correct |
| Spec ambiguity | Spec says "should" but behavior is ambiguous — clarify with PO |
| Environmental limitation | Couldn't test on iOS simulator (no macOS available), couldn't test with real Redis (only in-memory) |
| Specialist recommendation | "Security smoke passed but this auth flow is complex — recommend a pentest before public launch" |
| Testability feedback | Missing health endpoint, stateful sessions prevent clean test isolation, no way to reset state |

**Action:** Note in the test report. File as a kanban card to `tech-lead` if it's a testability or design issue. Optionally file to `product-owner` if it's a spec issue.

## P0–P4 mapping summary

| Our severity | Google P-level | Meaning | Blocks ship? |
|---|---|---|---|
| Critical | P0 | Launch blocker / data loss / security hole | YES |
| Critical | P1 | Major journey broken, no workaround | YES |
| Important | P2 | Journey broken, workaround exists | Recommended |
| Minor | P3 | Minor / cosmetic | No |
| Note | P4 | Suggestion / nice-to-have | No |

## Decision flow

```
Is the core feature broken or is there a security hole?
  → YES → Is it a launch blocker / data loss / security hole?
           → YES → Critical (P0)
           → NO  → Critical (P1) — major journey broken, no workaround
  → NO → Does a non-core feature or edge case fail?
           → YES → Does it affect the main user journey?
                    → YES → Important (P2)
                    → NO → Minor (P3)
           → NO → Is it a cosmetic or low-impact issue?
                    → YES → Minor (P3)
                    → NO → Note (P4) — observation/feedback
```

## Severity in re-test

When re-testing a fix:
- A **resolved** finding keeps its original severity for tracking, but gets status _resolved_.
- A **regression** (fix introduced a new issue in the same area) is filed as a new finding. If it's in a core area, it inherits Critical.
- A finding that survives 3 fix attempts is escalated to tech-lead regardless of severity.
