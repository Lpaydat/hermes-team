# Finding Severity Rubric

## P0 — Launch blocker
Data loss, security hole, core feature completely broken, data corruption. No workaround. Blocks shipping.

## P1 — Major breakage
Core journey broken with no workaround. Auth broken, payment broken, rate limiting bypassable. Should fix before ship.

## P2 — Degraded
Journey broken WITH workaround, or edge case producing wrong results. Non-core feature broken. Can ship if documented.

## P3 — Minor
Cosmetic, low-impact. Misaligned UI, missing label, verbose error message. Can ship.

## P4 — Suggestion
Observation, not a bug. UX feedback, spec ambiguity, testability gap. File for backlog.

## Deduping rule (synthesizer)

When multiple workers independently find the same root cause, group them as ONE finding in the triage report. Note how many workers confirmed it. Example:

```
P1: SSRF — /api/test passes arbitrary URLs to Playwright (confirmed by 3 workers: functional, security, exploratory)
```

Not 3 separate P1 cards for the same vulnerability.
