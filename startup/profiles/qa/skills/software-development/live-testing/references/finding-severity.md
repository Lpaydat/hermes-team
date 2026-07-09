# Finding Severity Rubric

Every QA finding gets a severity. This lets the developer prioritize fixes and the tech-lead decide what blocks shipping.

## Severity levels

### Critical — blocks shipping

The artifact cannot ship with this issue. Core functionality is broken, data is at risk, or security is compromised.

| Category | Examples |
|---|---|
| Core feature broken | Signup crashes, API returns 500 on valid input, CLI exits non-zero on success, app won't start |
| Data loss | Delete removes the wrong record, update overwrites unrelated data, crash corrupts state |
| Security hole | Auth bypass, IDOR (user B reads user A's data), SQL injection works, secrets in output |
| Data corruption | Concurrent writes corrupt records, restart loses committed data |
| Build failure | Artifact won't build from source |

**Action:** File as kanban card to `developer`. Block the QA card as dependency. The feature cannot ship until this is resolved.

### Important — should fix before ship

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

### Minor — can ship with

The artifact works correctly but has a cosmetic or low-impact issue. Shipping is fine.

| Category | Examples |
|---|---|
| Cosmetic | Off-by-one in pagination display, inconsistent button styling, typo in error message |
| Non-critical edge case | Extremely unlikely input (10000-char filename) causes a minor display glitch |
| Performance (minor) | p95 is 1.5s (under 2s threshold but not snappy) |
| Accessibility (WCAG AA) | Color contrast slightly below AA threshold on a non-essential element |

**Action:** File as kanban card to `developer` or note in the test report. Ship is not blocked.

### Note — observation, not a bug

The artifact behaves correctly, but something is worth flagging to the team. Not actionable as a bug fix.

| Category | Examples |
|---|---|
| UX feedback | Flow is confusing, error message is unhelpful but technically correct |
| Spec ambiguity | Spec says "should" but behavior is ambiguous — clarify with PO |
| Environmental limitation | Couldn't test on iOS simulator (no macOS available), couldn't test with real Redis (only in-memory) |
| Specialist recommendation | "Security smoke passed but this auth flow is complex — recommend a pentest before public launch" |

**Action:** Note in the test report. Optionally file as a kanban card to `product-owner` if it's a spec issue.

## Decision flow

```
Is the core feature broken or is there a security hole?
  → YES → Critical
  → NO → Does a non-core feature or edge case fail?
           → YES → Does it affect the main user journey?
                    → YES → Important
                    → NO → Minor
           → NO → Is it a cosmetic or low-impact issue?
                    → YES → Minor
                    → NO → Note (observation/feedback)
```

## Severity in re-test

When re-testing a fix:
- A **resolved** finding keeps its original severity for tracking, but gets status _resolved_.
- A **regression** (fix introduced a new issue in the same area) is filed as a new finding. If it's in a core area, it inherits Critical.
- A finding that survives 3 fix attempts is escalated to tech-lead regardless of severity.
