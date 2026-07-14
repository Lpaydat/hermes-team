# Kanban-Native Loops: Card-as-Loop-State-Machine (v2)

How the five-phase loop runs when the generator and evaluator are separate Hermes profiles (`developer`, `verifier`) coordinating through cards.

> Status: **active design** — verified against platform source and adopted 2026-07-03 (consultation report: /tmp/hermes-dev-workflow-recommendation.md). Supersedes the v1 "provisional" draft, whose central premise was factually wrong. The developer/verifier profiles were built ahead of the consultation's T1/T2 pain triggers by explicit operator decision (2026-07-03); the pain-first discipline survives as the routing gates below and the cap-raise preconditions in §Concurrency. Not yet load-tested: complete the commissioning run (§9) before routing real work here.

## The corrected premise: the trace is NOT gone

v1 assumed the developer's execution trace dies with its session. False, twice over:

1. **Harness transcripts persist on disk by default** — claude: `~/.claude/projects/<cwd-encoded>/<session-id>.jsonl` (full trace: thinking, tool_use, tool_result), resumable cross-process via `claude -p -r <id>`; codex: `~/.codex/sessions/.../rollout-*.jsonl`; opencode: `opencode export`.
2. **Hermes persists every profile session** in per-profile `state.db` (FTS5-indexed), readable cross-profile via `session_search(profile=...)`; `kanban_complete` stamps `worker_session_id` into card run metadata (on complete only — block paths must include the session id in the block comment).

So trace-first iteration (SKILL.md Iterate rules) survives async mode unchanged. The only new requirement is the capture convention: **every harness invocation copies its transcript to `~/vault/traces/<board>/<card-id>/attempt-<n>.jsonl`** before the card completes or blocks.

## Roles

| Role | Who | Trace access |
|------|-----|-------------|
| Planner | tech-lead (in-session, at card creation) | — |
| Generator | `developer` profile → **invokes harness as a tool** (never codes raw; vendor-tuned loops are the point) | Its own session + harness resume |
| Evaluator | `verifier` profile (fans out `[probe]` worker cards via kanban_chains) | **Trace-blind by default** (independence); reads diff + files + executed tests + completion report; opens transcript only on tamper suspicion |
| Escalation | tech-lead | **Trace-aware**: accumulated comments → grep `attempt-N.jsonl` for the divergence point → `session_search(profile=developer)` |

Role separation is unchanged from SKILL.md: planner never codes, generator never grades (mechanical gates only), evaluator proves-it's-broken with evidence.

## The flow

```
bead ready
  → beads-watchdog → tech-lead card (sole beads→kanban bridge, idempotency-keyed)
  → tech-lead (in-session): Discover + Plan
      contract.md (20-27 assertions) committed to repo, evals_cmd defined
      → kanban_chains(chains=[[...]])   ← creates dev+verifier cards atomically,
                                                   links tech-lead as dependent on verifier,
                                                   blocks with kind=dependency
  → developer works card (developer-loop skill): harness-as-tool, mechanical gates,
      trace to ledger, commit to branch, structured completion report
  → verifier works card (adversarial-review v6, chains-native): Stage 1 EXECUTE tests/evals/build
      inline (fast-fail on mechanical Criticals) → Stage 2 fans out [probe] worker cards via its
      own kanban_chains call (fresh-eyes AC prover ∥ static code-review axes ∥ delta check on
      iter ≥2) and dependency-parks → Stage 3 on auto-promotion: synthesize → gap probes →
      mutation checks → verify-findings pass → AC gate
      → PASS → bd merge-slot (--holder verifier --wait): rebase → re-run suite on rebased
               candidate → merge → release → complete card with stamped verdict → completion
               boundary closes the bead
      → FAIL → findings comment on dev card headed `REVIEW-ITERATION: <N>` (cards have no
               mutable metadata — the comment IS the counter, the review-card chain the fallback)
               + fix card (assignee=developer, parents=[review card], workspace = the dev's
               ORIGINAL worktree, body carries Review-Iteration/Chain-Root/Resume-Session/
               Branch/Worktree) + fresh review card as the fix card's child
               → developer retries via WARM RESUME (claude -p -r <session_id>) with findings
      → iteration ≥ 3 → verifier blocks ITS OWN card needs_input (foreign block is
               structurally rejected) + creates tech-lead escalation card linking the chain
      → SPEC GAP → same own-block + escalation card for tech-lead (contract-vs-code →
                   tech-lead re-contracts; contract-vs-intent → routes to product-owner)
```

## Choreography: parent/child cards — NOT the native review status

The platform's `review` task status + review-dispatch path (`kanban_db.py:7317`) is **dead code**: no production tool can move a card into `review`, the force-loaded `sdlc-review` skill doesn't exist (the spawned reviewer crashes at startup), the reviewer is hardwired to the developer's own profile, and the reject path is unimplemented. Do not use it; do not hand-SQL cards into `review`.

The parent/child path is verified working: `recompute_ready` auto-promotes child cards when parents complete (every dispatcher tick) and pipes the parent's completion summary + metadata into the child's prompt. The security envelope (`_enforce_worker_task_ownership`) permits exactly what the loop needs — any worker may comment on any card (forgery-proof author), create cards, link, read — while structurally blocking foreign complete/block/unblock. **Never route around these guards with conventions; they are a deliberate anti-prompt-injection control.**

Retry cap: the iteration count is a COMMENT convention — the verifier heads each findings comment `REVIEW-ITERATION: <N>` and stamps `Review-Iteration: <N+1>` into the fix card's body (kanban cards have no mutable metadata field, and `kanban_create` accepts no metadata — verified in platform source; `consecutive_failures` counts spawn crashes only). The review-card chain under the dev card is the fallback count. Watchdog audit tick (count iterations ≥3 without an escalation card; reconcile done dev cards against still-open beads): **TODO — not yet implemented in beads-watchdog.sh**; until it is, the verifier's escalation discipline is the only enforcement.

## Card schema

**Cards are created by the `kanban_chains` tool** — do NOT call `kanban_create` manually for developer or verifier cards. The tool creates both atomically (developer card + verifier card as its child), links your card as dependent on the verifier, and blocks you with `kind=dependency`. See SKILL.md Execute phase for usage.

What the tool creates (for reference — the tool handles this internally):

**Developer card** — title: `[dev] <outcome>`. Body: full contract (ACs, evals_cmd, bead_id, constraints, harness). Workspace: `dir:<project path>`.

**Verifier card** — title: `[verify] <outcome>`. Child of developer card. Body: contract_ref, evals_cmd, bead_id, review axes.

**Fix card** (created by verifier on FAIL — this IS manual, the verifier creates it directly via `kanban_create`): assignee=developer, parent=review card, workspace = the ORIGINAL developer worktree (`workspace_kind: dir` + `workspace_path`); body: `Review-Iteration: <N>`, `Chain-Root: <original dev card id>`, `Resume-Session: <session_id>`, `Branch:`, `Worktree:`, findings pointer, same contract_ref/evals_cmd.

**Reviewer card** — child of developer (or fix) card. Body: `contract_ref`, `evals_cmd`, review axes, base SHA + branch; round-1 cards embed the head SHA, iteration cards take the new head from the parent fix card's completion metadata (auto-injected on promotion — the head doesn't exist yet when the card is created). Deliberately NOT given: transcript path prominence, developer session history (trace-blind default).

**Contract-vs-criteria delineation** (resolves the v1 contradiction): the card EMBEDS the operational contract_ref + evals_cmd (execution needs); it REFERENCES the bead for acceptance criteria and scope (planning truth).

## Beads/kanban ownership contract

| System | Layer | Source of truth for |
|--------|-------|-------------------|
| Beads | Planning | WHAT: scope, acceptance criteria, ordering, milestones |
| Kanban | Execution | WHO and WHEN: which agent, card lifecycle, handoffs |

Rules (1-5 unchanged from v1, two additions):

1. One bead = one card CHAIN (dev card + its review/fix descendants). Never two independent chains per bead, never one chain spanning beads.
2. Card body REFERENCES the bead — acceptance criteria are read from beads.
3. Only the completion boundary writes back to beads (the verifier's pass-merge-complete is that boundary).
4. Beads-watchdog is the only beads→kanban bridge (idempotency keys mandatory).
5. Beads reflects committed scope, not real-time execution status. Kanban is the granular record; beads goes stale during active work — accepted.
6. **`kanban.auto_decompose: false` in the dispatcher gateway's OWN profile config** — the `kanban:` block of `startup/profiles/<profile>/config.yaml`, the SAME config source as the caps (verified: `_resolve_auto_decompose_settings` in `gateway/kanban_watchers.py` reads it via the same `_load_config()` → `cfg.get("kanban")` path as the caps; no per-board toggle exists; set 2026-07-03, re-read every tick so a flip takes effect on the next dispatcher tick without a restart). Belt-and-braces: cards enter at todo/ready, never triage — the decomposer only touches triage.
7. **Product-owner amendment**: product-owner owns bead CONTENT — it files beads from discovery and is the only role that changes what a bead promises. Tech-lead owns the contract derived from a bead. Verifier-found gaps split mechanically: *contract-vs-code* → tech-lead (re-contract); *contract-vs-intent* (the bead promises the wrong thing) → tech-lead routes to product-owner, who owns bead content. Nobody re-contracts anyone else's artifact.

## Merge story: serialized merge-owner (no auto-merge queue)

`bd merge-slot` (shipped in bd 1.0.4 — Gastown's Refinery serialization primitive) + verifier-as-merge-owner:

- Developers NEVER merge; every card ends on its branch.
- Verifier, on pass: acquire slot → rebase onto main → **re-run evals + full suite on the rebased candidate** (the DoltHub rule: a queue that trusted reported green auto-merged failing tests) → merge → release slot. Rebase conflicts = review FAIL (conflict resolution is code-writing → fix card to developer).
- Skip bisection below ~4 concurrent developers; serialization is the strategy.

## When to route here vs harness-direct

Kanban-native IS the flow for implementation work (loops-engineering Execute phase: "the ONLY flow") — durable cards, auditable chains, per-profile caps now 6 so parallel beads genuinely parallelize. Harness-direct survives only for user-supervised spikes outside the loop (merged under tech-lead + user approval per merge-protocol.md). Never dispatch an ambiguous card. Historical routing table: orchestration-models.md.

## Concurrency & budget

- Dispatcher caps live in the **lock-holding gateway's OWN profile config** — the `kanban:` block of `startup/profiles/<profile>/config.yaml` — NOT the global `startup/config.yaml` and NOT `~/.hermes/config.yaml`. The dispatching gateway is whichever profile gateway holds the machine-global `startup/kanban/.dispatcher.lock` (non-deterministic — any profile gateway can win it), and it reads its own profile config at boot. Because the lock-holder is non-deterministic, **all profile configs must agree** on kanban caps for a cap change to take effect regardless of which gateway dispatches. Current per-profile: `max_in_progress_per_profile: 6`, `dispatch_stale_timeout_seconds: 14400`. Caps are read at gateway boot — edit every profile's `config.yaml`, then restart the lock-holding gateway.
- Raising the per-profile cap above 1 (the T2 parallelism decision) requires: ≥3 genuinely independent leaf beads starving >48h, ≥1 clean end-to-end loop completed, and a file-safety check on the target beads (hotspot files serialize work regardless of agent count). Re-evaluation criteria from the 2026-07-03 consultation, preserved here deliberately.
- Every card sets `max_runtime_seconds`; every harness call inside follows the harness-commands.md budget recipe (timeout + turn cap + post-hoc cost flag). Cost lands in the completion report → board-level spend is greppable.

## §9 Commissioning (do this before routing real work)

The dispatch path's lifetime record before commissioning: 0 completions in 29 runs (config debt, not architecture). Prove the substrate with one throwaway loop:

0. Preconditions: each profile's `startup/profiles/<profile>/config.yaml` has the `kanban:` block (caps + `auto_decompose: false`) and the lock-holding gateway has been RESTARTED since (caps load at boot); `bd merge-slot create` run once in the target project; developer + verifier profiles resolvable (`hermes profile list`).
1. Pick a trivial, real, single-file bead (or write one) on a project board.
2. tech-lead calls `kanban_chains` (creates dev+verifier cards atomically, links tech-lead as dependent on verifier, blocks with kind=dependency).
3. Watch: dispatcher claims dev card → developer completes with trace + report + branch/worktree metadata → verification card auto-promotes with the handoff → verifier executes, verdicts, merges via slot → bead closed.
4. Verify afterwards: `worker_session_id` stamped, transcript in `~/vault/traces/<board>/<card-id>/`, `session_search(profile=developer)` finds the session, the parent handoff carried branch_name/worktree_path, journal entry written.
5. Any step fails → fix the config/choreography and rerun. Do not route real work until one commissioning loop is fully green.
6. Round 2 of commissioning (recommended): seed a card designed to FAIL review once — verify the findings comment, fix-card choreography (original worktree + warm resume), fresh review card promotion, and the second-round merge all work.

## Open questions (empirical — revisit after ~10 real loops)

1. Median wall-clock per iterate round (kill criterion: >45 min sustained → retreat to harness-direct + verifier-only, keep the trace ledger).
2. Cost per card vs harness-direct equivalent (kill criterion: >3× without a parallelism win).
3. Does `review_iteration` convention hold without a platform counter, or does the watchdog audit catch drift often enough to justify an upstream feature request?
4. Reviewer finding quality: % of findings the developer round actually resolves (target: retry rounds shrink, not churn).
