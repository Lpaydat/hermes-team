# QA Workflow Approaches — Design Document (v3.0)

Synthesized from 3 research streams (big tech patterns, Hermes system analysis, QA industry practices). Each approach includes concept, how it works, pros/cons, and when to use it.

## Approach 1: Single-Session Sequential (Small Artifacts)

All 8 phases in one session. No subagents, no containers. Simplest, works for small artifacts (CLI, library, <10 claims, stateless).

**When to use:** Small artifacts only. For medium+ artifacts, context pressure (35–75K tokens) buries Phase 7 synthesis.

## Approach 2: Verifier Hybrid — delegate_task for heavy phases (Small-Medium)

Main session: Phase 0–2 (receive, plan, build+smoke). delegate_task fan-out for Phase 3–5 (parallel). Main session: Phase 6–7 (explore, synthesize, verdict).

Solves: context pressure (subagents absorb raw output), shared artifact (delegate_task shares host). Fix loop uses kanban (durable).

**When to use:** Small-medium artifacts where context pressure is a concern but the artifact can be built in-session and doesn't need container isolation.

## Approach 3: Kanban Fan-Out + Containers (Medium-Large) — v3.0 DEFAULT

Main session: Phase 0–2 (receive, plan, build + containerize). Create child kanban cards per test aspect. Each child starts its own container from the pre-built image. QA blocks, auto-resumes when all complete.

Solves: context pressure (each child has fresh context), durability (kanban cards survive crashes), isolation (containers prevent port/DB/file conflicts), build-once (image built once, all workers use it).

**When to use:** Medium-large artifacts (API servers, webapps with auth, 10+ claims, stateful). This is the v3.0 default for medium/large.

**How it works:**
1. Main session builds artifact and container image (`podman build -t qa-test:<card-id> .`)
2. Main session creates 2–4 child kanban cards (one per test aspect)
3. Main session `kanban_block(reason="dependency: waiting for N child test workers")`
4. Dispatcher picks up child cards, spawns QA workers
5. Each worker: `podman run -d -p <port>:<app-port> qa-test:<card-id>` → health check → run tests → write evidence to ledger → `podman rm -f` → complete with summary
6. All children complete → parent auto-promotes
7. Main session reads evidence ledger, synthesizes verdict (Phase 7)

## Approach 4: Batch by Claim (not by phase)

Split by claim batch — each subagent gets ~5 claims + associated journeys + edge cases. Better coverage coherence (functional + journey + edges together per batch). But journeys spanning batches are awkward, non-functional smoke doesn't split by claim.

**When to use:** Many independent claims where batching by claim gives better coherence than batching by phase.

## Approach 5: Staged Pipeline (sequential subagents with handoff)

Phase 3 (claims) → Phase 4 (journeys, only if claims pass) → Phase 5 (smoke). Respects dependency: journeys test features claims proved work. No parallelism but natural fail-fast (skip journeys if claims broken).

**When to use:** When phases have strong dependencies and fail-fast is more important than parallelism.

## Approach 6: Two-Pass (smoke pass + deep pass) — v3.0 INTEGRATED

Pass 1: fast happy-path smoke of all claims. Pass 2: deep testing only of passing claims. Fails fast on broken happy paths.

**When to use:** Always (v3.0 default with `qa.two_pass: true`). Integrated into Phase 3 — smoke all claims first, deep-test only passing ones.

## Approach 7: Canary Testing (test against deployed instance)

Artifact already deployed to staging. QA tests against the URL. No build phase. Tests the REAL deployed artifact (catches deployment/config issues). Requires deployment pipeline.

**When to use:** When a staging/canary environment exists. Not applicable for CLI/TUI/library.

## Approach 8: Fresh-Eyes Adversarial (verifier's independence pattern)

Main session runs full protocol. Then dispatches a fresh-eyes subagent with deliberately restricted context (ONLY spec+claims+connection, NEVER QA's findings). Compare verdicts. Disagreements = high-priority findings.

**When to use:** High-stakes artifacts (payments, security-critical, production-facing).

## Approach 9: Risk-Based Priority — v3.0 INTEGRATED

Rank claims by risk (likelihood × impact). P0/P1 → full depth (10+ edge cases, journeys, degradation). P2 → medium depth. P3/P4 → smoke only.

**When to use:** Always (v3.0 default with `qa.risk_based: true`). Integrated into Phase 1 — claims are risk-ranked during planning, depth is determined by risk level.

## Approach 10: Evidence-Ledger Architecture — v3.0 INTEGRATED

Every test result written to disk immediately. Protocol resumable from any phase. Read `overall-summary.json` on re-dispatch → skip completed phases, re-run only incomplete. Fully crash-resilient.

**When to use:** Always for medium/large artifacts. The evidence ledger at `~/vault/qa-evidence/<qa-card-id>/` is written by all child workers and read by the main session for Phase 7 synthesis.

## Summary Comparison

| Approach | Parallelism | Context isolation | Crash recovery | Build-once | Best for |
|---|---|---|---|---|---|
| 1. Single-session | No | No | No | Yes | Small artifacts |
| 2. Verifier hybrid | Yes | Yes | Partial | Yes | Small-medium artifacts |
| 3. Kanban + containers | Yes | Yes | Yes | Yes (image) | Medium-large artifacts (v3.0 default) |
| 4. Batch by claim | Yes | Yes | Partial | Yes | Many independent claims |
| 5. Staged pipeline | No | Yes | Partial | Yes | Dependent phases |
| 6. Two-pass | Partial | Yes | Partial | Yes | Fail-fast screening (v3.0 integrated) |
| 7. Canary | Yes | Yes | Yes | N/A | Deployed artifacts |
| 8. Fresh-eyes | Yes | Yes | Partial | Yes | High-stakes |
| 9. Risk-based | Yes | Yes | Partial | Yes | Mixed-risk features (v3.0 integrated) |
| 10. Evidence-ledger | Yes | Yes | Yes | Yes | Large/long-running (v3.0 integrated) |

## v3.0 recommended path

The v3.0 protocol integrates approaches 6, 9, and 10 into the 8-phase spine, and uses approach 3 (kanban + containers) as the default execution strategy for medium/large artifacts:

- **Small:** Approach 1 (single session) with approaches 6, 9, 10 integrated into the phases.
- **Small-medium:** Approach 2 (delegate_task hybrid) with approaches 6, 9, 10 integrated.
- **Medium-large:** Approach 3 (kanban + containers) with approaches 6, 9, 10 integrated.
- **High-stakes:** Add approach 8 (fresh-eyes) as a verification layer.
- **Deployed:** Use approach 7 (canary) when staging is available.
