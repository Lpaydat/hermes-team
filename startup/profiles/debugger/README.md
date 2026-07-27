# The Debugger — debugging-team orchestrator

> **Status:** DRAFT design spec (brainstorming output, awaiting review).
> **Branch:** `design/debugging-workflow` (worktree, isolated from the in-flight `design-council` v2 work on `test/design-v2`).
> **Date:** 2026-07-13.
> **Companion workflows:** `architect/design-council` (design), `verifier/adversarial-review` (review). The debugger is the **diagnosis** orchestrator — the third leg.

---

## 1. The gap this fills

Three profiles touch defects today; none root-causes them as a durable, board-observable team loop:

| Profile | Touches defects by… | Stops at… |
|---|---|---|
| `qa` | *finding* bugs (`qa-functional`, `qa-exploratory`, `live-testing`) → emits a bug card | "reproduced, here's the bug." Has `diagnosing-bugs` **disabled**. |
| `verifier` | *failing* developer cards (`adversarial-review`) → emits a fix card | proving brokenness. Does not diagnose. |
| `developer` | *implementing* fixes (`developer-loop`) | a **leaf** worker (fanned-out-to), not an orchestrator. |

The shared `diagnosing-bugs` / `debug-mantra` skills exist but are single-agent runtimes, disabled everywhere. **The empty slot:** nothing takes "here is a defect" and systematically root-causes it through a converge loop, as a team workflow whose phases are observable, resumable, role-pure kanban cards.

## 2. Goal — the done-contract

A self-contained **debugging workflow** that plugs into hermes exactly as `design-council` and `adversarial-review` do. Primary done-contract (chosen during design):

> **Debug-to-fix by default; escalate design flaws.**
> - **Localized bug** → ship a *proven* minimal fix + a regression test + a **post-mortem (RCA)**, handed back to qa/originator to re-verify.
> - **Root cause is architectural** (no correct test seam, or spans a boundary) → an **RCA + an ADR stub** that re-enters the `architect` gate (exit B), *not* a quick patch.

This mirrors how the `architecture-gate` has a T3 "too big, hand back" path: one workflow, two exits by bug type.

## 3. Doctrine sources — consumed at *plan-time*, not run in-session

The debugger does **not** execute the diagnosis skill line-by-line in one session. It **reads** the doctrine to *produce a per-bug fixing plan* (the way the architect reads `design-council/SKILL.md` to produce a design fan-out). Three sources:

- **Matt Pocock `diagnosing-bugs`** — the 6-phase spine:
  1. *Build a feedback loop* ("this **is** the skill" — a tight pass/fail signal that goes red on *this* bug).
  2. *Reproduce + minimise* (shrink to the smallest scenario that still goes red; every remaining element load-bearing).
  3. *Hypothesise* — 3–5 ranked, **falsifiable**, each with a stated prediction.
  4. *Instrument* — one variable at a time; debugger/REPL > targeted logs > never "log everything and grep"; tag probes `[DBG-a4f2]`.
  5. *Fix + regression test* — write the regression test **before** the fix, **only if a correct seam exists**. *"If no correct seam exists, that itself is the finding — the architecture is preventing the bug from being locked down."* ← **this is the design-flaw exit signal.**
  6. *Cleanup + post-mortem* — *"the hypothesis that turned out correct is stated in the commit/PR"* + *"what would have prevented this bug?"* → architectural → hand off.
- **9arm `debug-mantra`** — the 4 mantras: *first is reproducibility* → *know the fail path* → *falsify the hypothesis (disprove first)* → *every run is a breadcrumb*.
- **9arm `post-mortem`** — the RCA artifact structure (§6.3). **Refuses to draft without all four inputs** (repro + known root cause + identified fix + validated fix) — these become the workflow's done-criteria.

The crux, per these doctrines: debugging's measure is *mostly objective* (repro red→green, suite green, no regression), and the failure mode it must guard against is **symptom-fixing** — a fix that makes the one repro pass while the root cause stays latent. The guard is **falsify-first** ("break it another way"), which is why falsification is an independent `verifier` card, not the debugger grading itself.

## 4. Architecture — the debugger is an orchestrator profile, not a worker

The `debugger` is a **third orchestrator profile**: `architect`→design, `verifier`→review, `debugger`→diagnosis. Like the architect, it **does not write product code** (pure orchestrator). The "debugging team" is the existing profiles, dispatched per phase:

| Phase | Worker (card `assignee`) | Why that profile |
|---|---|---|
| **Reproduce + minimise** | `researcher` (env/log archaeology) *or* `developer` (build the failing test) | the first tight RED signal |
| **Hypothesise + fix** | `developer` (the only code-shipping profile) | a fresh-context `developer-loop` card |
| **Falsify** | `verifier` (independent) | **never self-grade** — "break it another way" |
| **Synthesize / converge / post-mortem** | `debugger` (the orchestrator) | holds the breadcrumb ledger; writes the RCA |

**Dispatch mechanism:** `kanban_chains`, adapting between dispatches (the durable dynamic-workflow regime — see §9). The breadcrumb ledger (repro, ranked hypotheses, falsify verdicts) lives on the **blackboard** (root card) and is re-injected into the debugger on each promotion, so the through-line reasoning survives even though each worker runs in a fresh context.

This is the faithful hermes pattern: `design-council` fans out research + peer + evaluator → the architect synthesizes; `adversarial-review` fans out verification probes → the verifier synthesizes. The debugger fans out repro + fix + falsify → synthesizes the RCA.

## 5. The loop

```
DEFECT CARD → debugger queue   (from: qa bug report | verifier FAIL | human)
   │  debugger reads the doctrine (§3) + the bug → carves the bug's worktree+branch
   ▼  → translates doctrine into a PER-BUG FIXING PLAN   ← the "dynamic" part
┌──────────────────────────────────────────────────────────────┐
│ ROUND 0 — REPRO                                              │
│   dispatch → researcher (archaeology) OR developer (failing  │
│               test); minimise to smallest red scenario        │
│   GATE: a tight RED signal on the blackboard (ledger #0)      │
│   no repro possible → BLOCK the card for HITL (NOT kanban): │
│     tag bead human, ESCALATE: comment naming what's needed    │
│     (env / logs / access / repro steps), mint bead-human-<id> │
│     card stays BLOCKED until the human unblocks → resume      │
└────────────────────────────┬─────────────────────────────────┘
   debugger promoted ─── reads results, RE-PLANS (adapt-between-dispatches)
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ THE LOOP — debugger re-plans each round from results         │
│   FLOOR (ordinary bug):   1 hypothesis+fix card → developer   │
│   HIGH-STAKES (hard bug): N parallel hypothesis cards (diverge)│
│                           → developer, each its own worktree+ │
│                              branch; survivor merges into the  │
│                              bug branch, the rest cleaned up   │
│   then ALWAYS:            FALSIFY card(s) → verifier           │
│   debugger synthesizes: keep survivor / discard symptom-fix /  │
│                          loop again                            │
└──────────────────┬─────────────────────────┬──────────────────┘
                   │                         │
         no correct seam /                 round converged
         root cause spans                 (root cause proven +
         a boundary                        fix validated)
                   │                         │
                   ▼                         ▼
┌──────────────────────┐      ┌─────────────────────────────────┐
│ ESCALATE — exit B    │      │ CONVERGE (debugger)             │
│  write RCA + ADR stub│      │  write post-mortem (RCA) doc →  │
│  → architect gate    │      │    docs/postmortems/<id>-<slug> │
│  (block + route)     │      │  fix shipped on bug branch      │
└──────────────────────┘      │  regression test locked         │
                              └───────────────┬─────────────────┘
                                              ▼
                          completion-contract seam → qa re-verify / originator

  PLATEAU: N consecutive rounds fail to converge → escalate to human
           (can't crack) OR take exit B (likely a design flaw)
```

## 6. The three refinements (mechanics)

### 6.1 HITL as a blocked card, not kanban
When the repro cannot be built (no env access, no logs, no artifacts), the debugger does **not** create a blocked card ask. It **blocks the card** the way the `architecture-gate` does at T2 escalation: tag the bead `human`, write an `ESCALATE:`-style comment naming *exactly* what is needed, mint the idempotent `bead-human-<bug-id>` operator card, and **leave the card blocked** (never self-complete). A debugging card may wait hours for prod logs or env access; the durable blocked-card regime is observable, async, and survives sessions — intercom (a live in-session ask, as `design-council` uses for the PO interview) is the wrong tool. The debugger auto-resumes on promotion when the human unblocks.

### 6.2 Worktree + branch per bug
At Round 0 the debugger carves `debug/<bug-id>-<slug>` (a git worktree on a dedicated branch, mirroring `developer-loop`'s `branch_name` + `worktree_path`) and threads both into every worker card. The repro test, the fix, and the regression test all land isolated on that branch — never `main`, never merged by the debugger. For the **high-stakes parallel-hypothesis diverge**, each hypothesis card gets its own worktree+branch (`debug/<bug-id>-<slug>/hypo-N`) — parallel fixes cannot share a working tree. The survivor's branch becomes the fix branch handed off for review/merge; the discarded branches are cleaned up. The post-mortem cites the branch/PR.

### 6.3 The post-mortem (RCA) document
CONVERGE writes a real engineering record at `docs/postmortems/<bug-id>-<slug>.md` (mirroring how ADRs live in `docs/adr/`), following the 9arm `post-mortem` structure:

- **Mandatory blocks:** Summary · Root cause · Fix · Validation.
- **Conditional, usually present:** Symptom · Mechanism · *How it slipped through* · Action items.
- **Discipline:** blameless; **code-identifiers first-class** (function names, file paths, commit SHAs — the index future-you greps); mechanism-over-narrative; **honest validation coverage** ("if you only tested one config, say so"); no hedging.
- **Refuses to draft without all four inputs** (reliable repro + known root cause + identified fix + validated fix). These four are the workflow's **done-criteria** — a post-mortem of a hypothesis is worse than none.

Matt Pocock Phase 6 contributes the two closing disciplines: state the *correct hypothesis* in the commit/PR, and answer *"what would have prevented this bug?"* — which is what feeds exit B (architectural prevention → ADR → gate).

## 7. Input / output seams

**Input — defect card** (from `qa` bug report | `verifier` FAIL | human), carrying:
```json
{ "symptom": "...", "repro_attempt": "...|none", "env": "...", "stakes": "low|high", "originator": "<profile/card-id>" }
```

**Output — completion-contract metadata** (the board seam downstream cards inherit):
```json
{
  "verdict": "fixed | escalated-design | blocked-hitl",
  "bug_id": "...",
  "branch_name": "debug/<bug-id>-<slug>",
  "worktree_path": "...",
  "regression_test": "<test path or 'no-seam: documented in RCA'>",
  "postmortem_path": "docs/postmortems/<bug-id>-<slug>.md",
  "root_cause_summary": "<one line>",
  "gate_bead": "<architect gate bead, if verdict=escalated-design>"
}
```
**Routing:** `fixed` → qa re-verify / originator; `escalated-design` → architect gate (carries the RCA + ADR stub); `blocked-hitl` → stays blocked for the human (no `done` completion).

## 8. Stakes tiers, bifurcation, convergence

- **Stakes tiers (v1: two):**
  - **Floor** (ordinary bug): 1 hypothesis+fix card → developer; 1 falsify → verifier. Default.
  - **High-stakes** (hard / "super-computer" class): parallel hypothesis diverge (design-it-twice style) → developer swarm; falsify swarm → verifier. Opt-in by the `stakes` field on the defect card.
  - *(A middle "standard" tier can be added later if the floor/high split proves too coarse.)*
- **Bifurcation criterion (→ exit B):** take the design-flaw exit when the root cause has **no correct test seam** (Matt Pocock Phase 5) **or** the verifier's falsify probe keeps finding the cause **spans a boundary / cross-cutting concern** (not localizable). It surfaces *inside* the loop, not from a separate triage.
- **Convergence:** root cause proven (survives falsify) **and** fix validated (repro green, suite green, no new regression) **and** a correct-seam regression test exists.
- **Plateau:** after `N` consecutive non-converging rounds, escalate to a human (can't crack) **or** take exit B (likely a design flaw). `N` to be tuned during validation (start at 3).

## 9. Relationship to the dynamic-workflow research (enhance `kanban_chains`, not a new plugin)

A parallel multi-agent research effort (3 dynamic-workflow repos + a local `kanban_chains` code map, adversarially reviewed) concluded:

- `kanban_chains` is **static + atomic** by design (the whole DAG fixed at call-time in one transaction); its run_id-salted idempotency key **actively blocks** mid-dispatch append.
- The dynamism durable loops need is **already achieved by adapting *between* dispatches** — the orchestrator is re-dispatched after promotion and decides the *next* `kanban_chains` call from worker results. `design-council` and `adversarial-review` already do this.
- A new VM-sandbox dynamic-workflow plugin (the pi/codex model) is **architecturally incompatible** with hermes's durable/resumable model (you can't snapshot a VM across sessions; those repos explicitly don't persist/resume). **Rejected.**
- hermes has **no** ephemeral plan-in-code orchestration tool today — but the durable loops (debugging, UX/UI, design-council) don't need one.

**Conclusion for the debugger:** its per-bug planning + adapt-between-dispatches *is* the durable dynamic-workflow regime, delivered with `kanban_chains`. No new plugin, no blocked design. The `kanban_chains` micro-enhancements that would most help this loop are documented as a **future fast-path** (Appendix A), to be built when the loop surfaces the need — not v1.

## 10. Out of scope (v1)

- The `kanban_chains_extend` / `next_steps` hook / per-fan-out budget enhancements (Appendix A — deferred until the loop proves the need).
- A new ephemeral dynamic-workflow plugin (rejected, §9).
- The UX/UI workflow (separate spec, same pattern).
- Loading/bundling the `diagnosing-bugs` / `debug-mantra` / `post-mortem` skills into the profile (an implementation concern; the doctrine content is already captured in §3).

## 11. Profile skills & `config.yaml` (transform conformance)

The debugger is an **orchestrator profile** cloned from `base` and specialized per the `transform` skill. The template is `architect` (same role-shape: orchestrator, doesn't write product code, writes a durable artifact). Per `transform`: keep it **lean** — enable only what the role needs, disable the rest; never copy the whole catalog.

### 11.1 Enabled (the debugger's kit)
- **`diagnosing-bugs`** (mattpocock) — the one debugging-doctrine skill, enabled from base's reserve by *omitting* it from `skills.disabled` (it already lives at `base/config.yaml:20`). This is the debugger's analogue of the architect's "design doctrine three."
- **`debug-loop`** (authored, the profile's own `skills/software-development/debug-loop/SKILL.md`) — the orchestration loop (§5). It **embeds the 9arm essentials** — the 4 mantras (`debug-mantra`) and the post-mortem structure (§6.3) — because those are *not* committed canonically anywhere (the only copies live in ephemeral task worktrees). One self-contained doctrine skill, no external dependency.
- **Base meta kept** (frozen/not disabled): `transform`, `bundled-skills-opt-out`, `report-to-base`.

### 11.2 Delete vs disable — the trash goes; the legit-but-not-yours stays off

**DELETE — remove from the profile entirely** (trash / one-time / totally unrelated / redundant with hermes's own model). These have no place in a debugging orchestrator:

- *One-time / bootstrap / migration (dead after first use):* `setup-matt-pocock-skills`, `migrate-to-shoehorn`, `setup-pre-commit`, `git-guardrails-claude-code` (Claude-Code hooks — hermes has `approvals` + `command_allowlist`).
- *Totally unrelated domain:* `writing-beats`, `writing-fragments`, `writing-shape` (story/article writing), `edit-article`, `teach`, `scaffold-exercises` (courseware).
- *Redundant with hermes's own mechanisms:* `ask-matt` (router — the kanban decomposer + `find-skills` cover it), `qa` (mattpocock's GitHub-issue QA — hermes has a dedicated `qa` profile), `writing-great-skills` (hermes has `hermes-agent-skill-authoring`).
- *Niche, not hermes's model:* `obsidian-vault` (hermes uses `docs/adr` / `docs/postmortems`), `wizard` (one-off bash-procedure generator).

**DISABLE — keep the file, off** (legit skills that are simply another profile's job; a future debugger life might re-enable one, so don't burn the file):

```yaml
skills:
  disabled:
    # -- mattpocock family: legit, but not the debugger's job (the trash ones above are DELETED, not listed here) --
    - design-an-interface
    - request-refactor-plan
    - ubiquitous-language
    - claude-handoff
    - code-review            # verifier reviews; debugger falsifies via verifier, never self-reviews
    - find-skills
    - grill-me
    - grill-with-docs
    - grilling               # HITL is a blocked card (§6.1), not a live grilling
    - handoff
    - implement              # pure orchestrator; fixes ship via dispatched developer cards
    - loop-me
    - prototype
    - research               # debugger dispatches research to the researcher profile
    - resolving-merge-conflicts
    - tdd                    # the developer writes tests on the dispatched fix card
    - to-spec
    - to-tickets             # feature decomposition is tech-lead/architect territory
    - triage
    - wayfinder              # platform decomposition is the architect gate's T3
    # -- the architect's design doctrine three: NOT this profile (debugger escalates design) --
    - codebase-design
    - domain-modeling
    - improve-codebase-architecture
    # -- delivery / delegation / loops doctrine: the debug-loop skill embeds its own dispatch --
    - team-delegation
    - team-observability
    - live-testing
    - wayfinding-auto
    - qa-build
    - qa-exploratory
    - qa-functional
    - qa-journeys
    - qa-protocol
    - qa-security
    - requesting-code-review
    - hermes-agent-skill-authoring
    - web-research
    # -- parity blanket disables (defense in depth) --
    - claude-code
    - codex
    - decision-mapping
    - obsidian
    - opencode
    - ponytail
    - ponytail-audit
    - ponytail-debt
    - ponytail-gain
    - ponytail-help
    - ponytail-review
```

**Scope / mechanism:** these mattpocock skills live in `shared-skills/mattpocock/` and are symlinked into profiles. **Delete from the `debugger` profile's `skills/` dir** (scoped — `rm` the profile's symlinks/copies during/after the transform birth). Deleting from `shared-skills/mattpocock/` would clean *all* profiles, but mattpocock is a third-party pack — `npx skills update` restores removed skills unless you fork the pack or pin an exclude. **Recommend: debugger-scoped delete now; shared cleanup as a separate team-wide call.**

### 11.3 `config.yaml` skeleton (mirrors `architect` + `developer`)
```yaml
model:
  default: glm-5.2
  provider: zai
  base_url: https://api.z.ai/api/coding/paas/v4
  context_length: 1000000
toolsets:
  - hermes-cli
  - kanban
  - loop_engine   # REQUIRED — debug-loop drives the converge loop via the loop_engine tool (declared at profile level; see config note on _toggle_plugin_toolset wiring)
agent:
  api_max_retries: 10
  reasoning_effort: xhigh        # debugging is reasoning-heavy (parity with architect + qa)
kanban:
  max_in_progress_per_profile: 2 # orchestrator parks on chains → low active concurrency (tunable)
  dispatch_stale_timeout_seconds: 14400
skills:
  disabled: [ ... §11.2 ... ]
approvals:
  mode: 'off'                    # autonomous orchestrator (parity with architect)
  cron_mode: deny
command_allowlist:               # parity with architect
  - execute_code
  - copy/move file into sensitive credential/SSH/shell-rc path
  - script execution via -e/-c flag
  - recursive delete
plugins:
  enabled: [ kanban, kanban_chains, loop_engine ]   # loop_engine REQUIRED — debugger is its first consumer (debug-loop skill drives the converge loop via the loop_engine tool)
  disabled: []
  entries:
    kanban: { allow_tool_override: true }
    kanban_chains: { allow_tool_override: false }
    loop_engine: { allow_tool_override: false }
onboarding:
  seen: { tool_progress_prompt: true }
```

### 11.4 `transform` conformance
- **Birth path:** create the profile by cloning `base` and running `/transform` with the debugger job brief (derived from this spec). Transform produces the SOUL/config/skills/description + the required markers — do **not** hand-assemble a partial profile.
- **Required artifacts transform leaves behind (implementation checklist):**
  - `SOUL.md` — specialty written **only** between `<!-- SPECIALTY:BEGIN -->` / `<!-- SPECIALTY:END -->`; the `CONSTITUTION` block and `## Team coordination` section left byte-for-byte unchanged.
  - `.no-bundled-skills` marker present.
  - `.bootstrap_complete` written (date + one-line specialty) so it doesn't re-transform.
  - `hermes profile describe debugger --text "…"` set — the kanban decomposer routes by description, not name.
- **`Never`-list respected:** no CONSTITUTION/Team-coordination/`.env`/meta-skill edits; no whole-catalog copy; no global-scope installs; no rewriting third-party skills; `.no-bundled-skills` not deleted.

### 11.5 Judgment calls (yours to override)
- **`team-delegation` disabled** to mirror the architect (the `debug-loop` skill embeds its own `kanban_chains` dispatch, as `design-council` does). *Re-enable* if you want the debugger to load the delegation-craft reference while the new skill matures.
- **`diagnosing-bugs` over `systematic-debugging`** — both are root-cause doctrines; chose the one already in base's reserve (zero-cost enable) over copying `systematic-debugging` from the catalog. Swap if you prefer the 4-phase `systematic-debugging` framing.
- **`max_in_progress_per_profile: 2`** — orchestrators park (blocked) while workers run, so active concurrency is naturally low. Tunable; raise to 3 (verifier parity) if it starves.

## Appendix A — `kanban_chains` future fast-path (not v1)

When the debugging loop's per-round re-dispatch cost becomes the bottleneck (a ~60s dispatch tick means each adapt-round pays a full park→tick→worker→complete→re-promote cycle), three cheap, high-value enhancements — all preserving the atomic-creator contract:

1. **`kanban_chains_extend`** — a *sibling* tool (the creator stays clean) that appends cards to an existing topology and re-parks the caller, bypassing the run_id-salted idempotency key. Fixes the documented swarm-repair friction in `adversarial-review` *and* lets the debugger schedule a follow-on probe without a full re-dispatch.
2. **`next_steps` completion hook** — a worker declares follow-on work in its completion metadata; a `kanban_task_completed` hook (the loader already has `register_hook`) consumes it to spawn cards. Data-dependent fan-out without a VM.
3. **Per-fan-out budget gating** — `maxCost`/`maxTokens` → abort (mirrors the pi repos' `BudgetExceededError`). Pure cost-explosion guard.

Build order: (1) first, (2) alongside, (3) cheap; race-cancel only if a concrete "fan out N, take first winner" loop demands it (`reclaim_task` already terminates a running worker PID, per the research).

## Appendix B — open questions (to resolve during plan/review)

- **Plateau `N`:** start at 3 consecutive non-converging rounds; tune during validation.
- **Repro assignee:** `researcher` vs `developer` for Round 0 — decide by whether the bug needs archaeology (researcher) or a failing-test harness (developer). Possibly both, chained.
- **Post-mortem location:** `docs/postmortems/` proposed (mirrors `docs/adr/`); confirm the venture convention.
- **Trivial bugs:** even a one-line fix dispatches a `developer` card (pure-orchestrator). Accept the round-trip, or allow a narrow inline trivial-patch at the floor tier? *Current design: dispatch always.*
- **Stakes declared by whom:** the `stakes` field on the defect card — set by qa/verifier/human at creation. Confirm.
- **Verifier-FAIL routing:** does *every* `verifier` FAIL route to the debugger (diagnose-then-fix), or only the ambiguous ones — with clear, localized defects still routing straight to the `developer`? Proposed split rule: the verifier stamps the FAIL card with a `diagnosis-needed` flag (set when the defect's cause isn't obvious from the finding); only flagged FAILs route to the debugger.
