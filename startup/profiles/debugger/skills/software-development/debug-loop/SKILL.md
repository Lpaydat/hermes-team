---
name: debug-loop
description: Drive a defect through a root-cause converge loop on the durable kanban board via the loop_engine tool — reproduce → hypothesise+fix → falsify → converge. Use when a defect card lands in your queue (from a qa bug report, a verifier FAIL, or a human) and you must diagnose-and-fix it as a team workflow, OR when asked to diagnose / root-cause a bug. Embeds the debugging doctrine (diagnosing-bugs 6 phases + debug-mantra 4 mantras + post-mortem structure) and maps it onto loop_engine phases a debugger can dispatch.
version: 1.0.0
metadata:
  hermes:
    tags: [debugging, diagnosis, root-cause, loop-engine, orchestration, kanban, converge-loop]
    category: software-development
---

# debug-loop — drive a defect through a root-cause converge loop

A defect that reaches you is **loop work**, not memory retrieval. You decompose it
into ordered **phases** and hand each phase to the `loop_engine` tool, which builds
the phase's execution (+ verifier) cards on the board, **parks** you until they
complete, and re-promotes you to decide: DoD met → next phase; DoD not met →
replan (fresh hypothesis); design-flaw signal → exit B; no repro → HITL block.

`loop_engine` is the **engineered loop around the model black box**; the board is
the **external state**; `kanban_chains` is the execute step; an independent
`verifier` card is the evaluator. You are the **driver** — claimed card,
stateless between promotions, re-reading board state each time. You **adapt
between dispatches**: every promotion, you re-plan the next round from the worker
results. This *is* the durable dynamic-workflow regime — no ephemeral
plan-in-code machinery.

## Leading words
* **driver** — you, the debugger, holding the breadcrumb ledger on the root
  card's blackboard and deciding each promotion.
* **parked** — your card dependency-blocked by `loop_engine`, auto-promoted when
  the phase terminal (the verifier card) completes.
* **DoD** — a phase's definition-of-done, carried in the verifier card's body and
  checked by an *independent* verifier card. Never self-graded.
* **falsify** — "break it another way"; the guard against symptom-fixing. Always
  an independent `verifier` card, never you reviewing your own hypothesis.

---

## When to use this skill

Load this skill when:
- A **defect card** lands in your queue (from `qa`, `verifier` FAIL, or a human).
- You are asked to **diagnose** or **root-cause** a bug systematically.
- A fix has been attempted and you must **prove the root cause** (not just that
  the repro went green).

Do NOT use this skill for: clear, localized one-line defects with an obvious
cause that route straight to a `developer` card (the verifier's `diagnosis-needed`
flag routes only ambiguous FAILs to you); feature work (tech-lead/architect);
or design decisions (architect).

---

## Round 0 — prepare the bug (before you call loop_engine)

1. **Read the doctrine below** (diagnosing-bugs 6 phases + debug-mantra 4 mantras)
   and the defect card. Translate the doctrine into a **per-bug fixing plan** —
   the "dynamic" part. You read the doctrine to *plan*, you do not execute it
   line-by-line in one session.
2. **Carve the worktree + branch** for the bug: `debug/<bug-id>-<slug>` (a git
   worktree on a dedicated branch, mirroring `developer-loop`'s `branch_name` +
   `worktree_path`). Thread `branch_name` and `worktree_path` into every worker
   card body so the repro test, the fix, and the regression test all land
   isolated on that branch — never `main`, never merged by you. (High-stakes
   parallel-hypothesis cards each get their own `debug/<bug-id>-<slug>/hypo-N`.)
3. **Read the defect card's fields** (§7 input seam):
   `symptom`, `repro_attempt`, `env`, `stakes` (low|high), `originator`. The
   `stakes` field selects the tier: floor (1 hypothesis) vs high-stakes
   (parallel hypothesis diverge).
4. **Seed the breadcrumb ledger** on the root blackboard: symptom, repro_attempt,
   env, stakes, originator, branch_name, worktree_path. `loop_engine` mints the
   root card (shared blackboard) on your first call.

---

## The doctrine (consumed at plan-time)

### Matt Pocock `diagnosing-bugs` — the 6-phase spine
1. **Build a feedback loop** — "this *is* the skill": a tight pass/fail signal
   that goes RED on *this* bug.
2. **Reproduce + minimise** — shrink to the smallest scenario that still goes
   red; every remaining element load-bearing.
3. **Hypothesise** — 3–5 ranked, **falsifiable** hypotheses, each with a stated
   prediction.
4. **Instrument** — one variable at a time; debugger/REPL > targeted logs >
   never "log everything and grep"; tag probes `[DBG-<bug-id>]`.
5. **Fix + regression test** — write the regression test **before** the fix,
   **only if a correct seam exists**. *"If no correct seam exists, that itself
   is the finding — the architecture is preventing the bug from being locked
   down."* ← **this is the exit-B (design-flaw) signal.**
6. **Cleanup + post-mortem** — *"the hypothesis that turned out correct is
   stated in the commit/PR"* + *"what would have prevented this bug?"* →
   architectural → hand off.

### 9arm `debug-mantra` — the 4 mantras
* **First is reproducibility** — no repro, no diagnosis.
* **Know the fail path** — trace the exact path that fails, don't guess.
* **Falsify the hypothesis (disprove first)** — try to *break* your hypothesis
   before trusting it.
* **Every run is a breadcrumb** — log every probe/observation to the ledger; the
   through-line must survive across fresh-context workers.

### 9arm `post-mortem` — the RCA artifact structure (Phase converge)
Mandatory: **Summary · Root cause · Fix · Validation.** Conditional (usually
present): Symptom · Mechanism · *How it slipped through* · Action items.
**Refuses to draft without all four inputs** (reliable repro + known root cause +
identified fix + validated fix) — these four are the workflow's done-criteria.

The crux: debugging's measure is *mostly objective* (repro red→green, suite
green, no regression). The failure mode it must guard against is
**symptom-fixing** — a fix that makes the one repro pass while the root cause
stays latent. The guard is **falsify-first**, which is why falsification is an
independent `verifier` card, not you grading yourself.

---

## Driving `loop_engine` — the phase→DoD→assignee→verifier mapping

Call `loop_engine` **once** with the whole phase plan. Each invocation runs ONE
iteration of the outer phase-loop; you are parked and re-promoted by the engine.
The engine handles: root-card creation, phase sub-graphs, dependency-parking,
the fan-in barrier, verifier verdict flow (`dod_verdict` in `run.metadata`),
advance/replan/escalate, and the layered exits (hard cap / budget /
no-progress). Your job is the **shape** of the phases + the per-promotion re-plan.

### The `goal`, `runner`
- `goal`: the defect, written as one string — the symptom + the repro_attempt +
  env + stakes + originator + the bug-id + branch/worktree. This is posted to
  the root card blackboard and derives the root idempotency key. **MUST be byte-identical across EVERY `loop_engine` call for one bug** — the key is `loop:{driver}:{goal_hash}`; rewriting the goal between promotions (appending the hypothesis/fix) changes the hash, mints a NEW root, resets `phase_index` to 0, and the loop re-runs phase 0 forever instead of converging (observed: smoke-005). Hypotheses/fixes/verdicts go in phase bodies + the ledger, NEVER in the goal.
- `runner`: **`"debugger"`** — you. Execution/verifier cards that do not name
  their own assignee inherit `debugger`; each phase below names its own assignee
  to route to the right profile.

### The phases (3 loop_engine phases encode §5's 4 debugging stages)

§5 lists four conceptual stages — reproduce, hypothesise+fix, falsify, converge.
They map onto **three** `loop_engine` phases, because **falsification is the
*verifier* of the fix phase**: a failed falsify must replan a *new hypothesis*
(loop_engine replans the current phase), which requires hypothesise+fix and
falsify to share one converge-loop. Forcing them into separate phases would make
a failed falsify re-run falsification instead of generating a new hypothesis —
broken. The mapping:

| §5 stage | loop_engine phase | execution (worker) | verifier (DoD-checker) |
|---|---|---|---|
| **Reproduce + minimise** | **phase 0** | `researcher` (archaeology) *or* `developer` (failing test) | `verifier` — "tight RED achieved" |
| **Hypothesise + fix** + **Falsify** | **phase 1** (the converge loop) | `developer` (fix + regression test for the ranked hypothesis) | `verifier` — **falsifies** ("break it another way"; repro green + correct-seam test + suite green + root cause proven) |
| **Converge / post-mortem** | **phase 2** | `debugger` (writes the RCA from the ledger) | `verifier` — "RCA has all 4 inputs + completion contract" |

#### Phase 0 — Reproduce + minimise  (`max_iterations`: 3)
- **execution.assignee**: `researcher` if the bug needs env/log archaeology
  (read logs, query prod, reproduce from artifacts); `developer` if it needs a
  failing-test harness. Decide at plan-time; possibly chain both. Seed the
  execution body with the defect's `repro_attempt`, `env`, and the
  branch/worktree.
- **execution DoD intent**: produce the tightest RED signal — a reliable,
  minimised repro (runnable test or exact steps), every remaining element
  load-bearing.
- **verifier.assignee**: `verifier` (independent).
- **verifier DoD** (in the verifier body): "A reliable, minimal repro exists
  that goes RED on this bug and GREEN when fixed. It is minimised to the
  smallest scenario that still fails, with every remaining element load-bearing.
  The repro is recorded on the blackboard (ledger #0) as a runnable test or
  exact, machine-checkable steps. If no repro is possible from the provided
  env/logs, set `recommendation: escalate` with gaps naming exactly what is
  needed (env access / prod logs / repro steps) — this routes to the HITL block."
- **No-repro path**: when the verifier escalates, `loop_engine` sticky-blocks
  your card (`needs_input`) — that IS the §6.1 HITL blocked card. Do not fire
  intercom. Comment the bead `human`, mint `bead-human-<bug-id>`, leave blocked.

#### Phase 1 — Hypothesise + fix + falsify  (`max_iterations`: 5, the main loop)
This is the converge loop. Each iteration = one ranked hypothesis.
- **execution.assignee**: `developer` (the only code-shipping profile).
- **execution skill**: force-load `developer-loop` (fresh-context fix card on
  the bug's worktree+branch). The body carries: the ranked hypothesis + its
  falsifiable prediction, the repro from ledger #0, the branch/worktree, and the
  instruction to write the regression test **before** the fix (only if a correct
  seam exists — if not, report `no-correct-seam` in the completion metadata,
  which is the exit-B signal).
- **verifier.assignee**: `verifier` (independent — **never self-grade**).
- **verifier DoD** (in the verifier body — this *is* the falsify step):
  "Evaluate the parent execution's fix. (1) The repro now goes GREEN. (2) A
  regression test exists at a **correct seam** (not a symptom-seam). (3) The full
  suite is green with no new regression. (4) **Falsify**: try to break it another
  way — exercise adjacent inputs/configs/paths the fix did not target. The root
  cause is *proven* (the fix addresses the cause, not the symptom). Return
  `dod_verdict`: `dod_met=true`/`recommendation=advance` only if all four hold;
  `dod_met=false`/`recommendation=replan` with concrete gaps if the fix is a
  symptom-fix or the repro is not green; `recommendation=escalate` with gaps
  naming `no-correct-seam` or `root-cause-spans-boundary` if the design-flaw
  signal is present (→ exit B)."
- **On replan** (`dod_met=false`): `loop_engine` mints a fresh developer card
  (next ranked hypothesis) + a fresh verifier card, and re-parks you. You
  re-inject the breadcrumb ledger (prior hypotheses tried + why they failed) so
  the developer doesn't retry a dead hypothesis.
- **High-stakes tier**: if `stakes=high`, dispatch N parallel hypothesis cards
  (design-it-twice style) instead of one — each its own `hypo-N` worktree. The
  survivor's branch becomes the fix branch; discarded branches are cleaned up.

#### Phase 2 — Converge / post-mortem (RCA)  (`max_iterations`: 2)
- **execution.assignee**: `debugger` (you — inherits `runner=debugger`; you pick
  up your own converge card in a fresh worker context and read the ledger from
  the root blackboard).
- **execution DoD intent**: write the RCA / post-mortem document at
  `docs/postmortems/<bug-id>-<slug>.md` following the 9arm structure (Summary ·
  Root cause · Fix · Validation mandatory; Symptom · Mechanism · How it slipped
  through · Action items conditional). Blameless; **code-identifiers
  first-class**; mechanism-over-narrative; **honest validation coverage**. State
  the correct hypothesis (Matt Pocock Phase 6) and answer "what would have
  prevented this bug?".
- **verifier.assignee**: `verifier`.
- **verifier DoD**: "The post-mortem at `docs/postmortems/<bug-id>-<slug>.md`
  contains all four mandatory inputs (reliable repro + known root cause +
  identified fix + validated fix). It cites code-identifiers (function names,
  file paths, commit SHAs). The completion-contract metadata is present. Return
  `dod_verdict`: `dod_met=true`/`advance` if so; `replan` with gaps naming the
  missing input otherwise. (A post-mortem of a hypothesis is worse than none —
  refuse to advance until all four are present.)"
- **DoD-met on phase 2 (the last phase) → workflow complete.** You then
  `kanban_complete` with the completion-contract metadata (§7).

---

## The bifurcation — exit B (design flaw)

Take exit B when the root cause has **no correct test seam** (Matt Pocock Phase 5)
**or** the verifier's falsify probe keeps finding the cause **spans a boundary /
cross-cutting concern** (not localizable). This surfaces *inside* the loop (the
phase-1 verifier sets `recommendation=escalate` with `no-correct-seam` or
`root-cause-spans-boundary` in the gaps), not from a separate triage.

When exit B fires:
1. **Do not quick-patch.** Write the **RCA** (root cause, why it's
   architectural, what boundary it spans) + an **ADR stub** at
   `docs/adr/<bug-id>-<slug>.md` proposing the architectural prevention.
2. **Route to the architect gate**: create an architect gate card carrying the
   RCA + ADR stub, and block+route it (the gate's T2/T3 path). Record the gate
   bead id in the completion contract.
3. The completion-contract `verdict` = `escalated-design`.

---

## The three refinements (mechanics)

### HITL = a blocked card, not intercom (§6.1)
When the repro cannot be built (no env access, no logs, no artifacts), you do
**not** fire an `intercom` ask. `loop_engine`'s escalation path
sticky-blocks your card (`kind=needs_input`) — that IS the durable HITL card.
Augment it: tag the bead `human`, write an `ESCALATE:`-style comment naming
*exactly* what is needed (env / logs / access / repro steps), mint the
idempotent `bead-human-<bug-id>` operator card, and **leave it blocked** (never
self-complete). A debugging card may wait hours for prod logs; the durable
blocked-card regime is observable, async, and survives sessions. You
auto-resume on promotion when the human unblocks.

### Worktree + branch per bug (§6.2)
At Round 0 you carve `debug/<bug-id>-<slug>` and thread both into every worker
card. The repro test, the fix, and the regression test land isolated on that
branch — never `main`, never merged by you. For the high-stakes parallel
hypothesis diverge, each hypothesis card gets its own
`debug/<bug-id>-<slug>/hypo-N` worktree (parallel fixes cannot share a working
tree); the survivor merges into the bug branch, the rest are cleaned up. The
post-mortem cites the branch/PR.

### Post-mortem at converge (§6.3)
Phase 2 writes the RCA at `docs/postmortems/<bug-id>-<slug>.md` (mirrors
`docs/adr/`). Structure per 9arm (above). Refuses to draft without all four
inputs — the phase-2 verifier enforces this as the DoD.

---

## Completion-contract metadata (§7 output seam)

On workflow complete (`kanban_complete`), write this structured metadata (the
board seam downstream cards inherit):

```json
{
  "verdict": "fixed | escalated-design | blocked-hitl",
  "bug_id": "<bug-id>",
  "branch_name": "debug/<bug-id>-<slug>",
  "worktree_path": "<path>",
  "regression_test": "<test path or 'no-seam: documented in RCA'>",
  "postmortem_path": "docs/postmortems/<bug-id>-<slug>.md",
  "root_cause_summary": "<one line>",
  "gate_bead": "<architect gate bead, if verdict=escalated-design>"
}
```

**Routing:**
- `fixed` → qa re-verify / originator.
- `escalated-design` → architect gate (carries the RCA + ADR stub).
- `blocked-hitl` → stays blocked for the human (no `done` completion).

---

## Plateau / layered exits

`loop_engine`'s layered exits are deterministic (plugin code, not
model-enforced) — termination never depends on you remembering to stop:
- **Hard cap** per phase (3 / 5 / 2 above): phase exhausts its cap without DoD →
  sticky HITL block.
- **No-progress**: identical verifier verdicts across consecutive iterations →
  sticky HITL block.
- After `N` consecutive non-converging rounds (start `N=3`), escalate to a human
  (can't crack) **or** take exit B (likely a design flaw).

When the engine escalates, it emits a `loop_escalated` event naming exactly what
the human owes. Unblock → resume.

---

## Hard rules (recap — never violate)
- **NEVER write product code** — fixes ship via dispatched `developer` cards.
- **NEVER self-grade a fix** — falsification is an independent `verifier` card.
- **NEVER fire intercom for a missing repro** — HITL is a sticky blocked card.
- **NEVER merge the bug branch to main** — it lands on `debug/<bug-id>-<slug>`.
- **ALWAYS write the post-mortem at converge** (all four inputs).
- **ALWAYS take exit B** when the root cause has no correct seam / spans a boundary.
- **ALWAYS use the board (`loop_engine` + cards), not subagents, for fan-out.**
- **ALWAYS pass the EXACT SAME `goal` string to every `loop_engine` call for one bug** — it derives the loop's idempotency key. Any drift (added hypothesis/fix/verdict) mints a new root and resets `phase_index` to 0 → the loop re-runs phase 0 forever and never reaches RCA. Mutate phase bodies + ledger between calls; never the goal.
