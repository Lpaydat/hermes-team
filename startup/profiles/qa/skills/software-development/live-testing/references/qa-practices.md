# QA Industry Practices Reference (2024–2025)

Condensed from research across Atlassian's testing taxonomy, Cucumber BDD docs, Guru99's testing-type reference, ISTQB, and Session-Based Exploratory Testing (SBET). Consult this when designing a test plan, justifying a dimension, or deciding what to escalate vs. handle in-house.

## Testing dimensions and ownership

| Dimension | QA owns | Specialist handoff |
|-----------|---------|-------------------|
| Functional | Full (claim→verdict loop) | — |
| Security | IDOR, auth bypass, secrets in output, dependency scan | Pentest, fuzzing, AppSec audit |
| Performance | Response time, 30s smoke load, degradation check | Load tuning, capacity planning, k6/Locust profiles |
| Accessibility | axe-core scan, tab-order, contrast check | WCAG compliance certification |
| Reliability | Graceful degradation (DB down, upstream 500, disk full) | — |
| Data integrity | Create→update→delete cycle, concurrency corruption | — |
| Compatibility | Supported browser/OS/device matrix | — |
| Usability | Flag confusing/error-prone paths as observations | UX/design review |

**Rule:** QA does cheap, fast checks that catch obvious regressions. Anything requiring tuning, certification, or a multi-hour run = filed bead / specialist handoff.

## Testing depth taxonomy mapped to pipeline ownership

| Level | What | Pipeline owner |
|-------|------|----------------|
| Unit | Single function | **Verifier** (runs dev's test suite pre-merge) |
| Integration | Module↔module, service↔DB | **Verifier** |
| Regression | "Did I break old stuff" | **Verifier** (runs suite) |
| Smoke | "Is it alive + core works" | **QA** (Step 3+4 of test loop) |
| Sanity | "Does this specific thing basically work" | **QA** (Step 4) |
| Functional | Per-feature business requirement | **QA** (claim→verdict) |
| End-to-end / journey | Full user flow through real system | **QA** (Step 6) |
| Acceptance | Meets business/user needs | **QA** (claim→verdict + journey) |
| Exploratory (SBET) | Charter-driven creative probing | **QA** (Step 7) |
| Load / Stress / Spike | Performance under volume | Specialist (QA does smoke-load only) |
| Security (pentest/fuzz) | Vulnerability hunting | Specialist (QA runs scanners only) |

## User-journey testing

Complementary to claim-based, not alternative:
- **Claims** = "does each feature work in isolation?"
- **Journeys** = "can a real user actually accomplish their goal end-to-end?"

Journeys find bugs that claims miss: session lost between steps, state not carried, dead-end after success, cross-feature interaction failures. Extract 1–3 per persona from the spec and execute them live.

## Exploratory testing (SBET model)

Session-Based Exploratory Testing: pick a **charter** (a one-sentence mission bounding the exploration), spend a bounded effort probing, log findings. This is QA's irreplaceable manual superpower — it finds what the spec didn't anticipate.

Charter examples:
- "Probe the file-upload feature for size, type, and encoding edge handling"
- "Probe the auth flow for token expiry, refresh, and concurrent session behavior"
- "Probe the payment flow for partial failure, timeout, and retry scenarios"

## QA vs. Verifier boundary

The **verifier** proves the code is built right (unit tests green, diff clean, mutation testing passes). It operates on **code** pre-merge.

The **QA agent** proves the right thing was built and survives contact with reality. It operates on the **live artifact** post-merge. Fundamentally different evidence.

What QA does that the verifier can't:
1. Runs the real assembled artifact, not tests against code
2. End-to-end user journeys (multi-step flows)
3. Exploratory / creative probing (bugs no pre-written test anticipates)
4. Failure-mode / graceful-degradation testing with real dependencies (DB down, upstream 500, disk full)
5. Cross-cutting dimension checks (security/perf/a11y smokes)
6. Spec-vs-artifact verification (did the dev build the right thing?)
7. Real environment + integration reality (does it run on the target OS? do real dependencies behave?)

What QA should NOT duplicate:
- Running the dev's unit/integration test suite (verifier's job)
- Reviewing code diffs (QA doesn't read code by design)
- Full load/perf engineering or security pentesting (specialist handoff)
