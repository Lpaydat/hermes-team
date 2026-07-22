---
name: debug-loop
description: Drive a defect through a root-cause converge loop on the durable kanban board via the loop_engine tool — reproduce → hypothesise+fix → falsify → converge. Use when a defect card lands in your queue (from a qa bug report, a verifier FAIL, or a human) and you must diagnose-and-fix it as a team workflow, OR when asked to diagnose / root-cause a bug. Embeds the debugging doctrine (diagnosing-bugs 6 phases + debug-mantra 4 mantras + post-mortem structure) and maps it onto loop_engine phases a debugger can dispatch.
version: 1.1.0
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

> **discover (v2) grounds this for you:** the engine runs an always-on **discover**
> phase before phase 0 (engine default — you get it automatically). It absorbs
> much of this Round-0 grounding (doctrine-read, worktree carve, ledger seed) and
> re-plans from the discoveries if the goal is under-specified. You MAY configure
> a custom `discover:{assignee, dod}` spec in the `loop_engine` call to sharpen
> the grounding for a particular bug class, but discover runs regardless.

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

### The canonical `loop_engine` call — copy this template VERBATIM

A weak-context driver copies **call templates** (literal examples) far more
reliably than it follows prose directives — observed on a real-board smoke: the
prose-only `strict_fact_basis=True` wiring was ignored and the engine defaulted
to `False`, so T9's hard-reject was never armed (`loop_state.strict_fact_basis=
false`). The fix: the load-bearing fields are baked into the template below as
**literal kwargs**, not just described in prose. **Copy the call verbatim**;
mutate only the `<...>` placeholders and the phase bodies.

```python
loop_engine(
    strict_fact_basis=True,  # T9 opt-in — REQUIRED. Do not omit, do not set False.
                             # Arms the fact-discipline layer: metric_type + evidence
                             # become HARD-REQUIRED (validated + enforced), not
                             # advisory. Engine default is False; copying this literal
                             # here is what makes the cutover real. It is the FIRST
                             # kwarg on purpose — the one field a weak-context driver
                             # quietly drops if it lives only in prose.
    goal="<defect: symptom + repro_attempt + env + stakes + originator + bug-id + branch/worktree — BYTE-IDENTICAL across every call for one bug>",
    runner="debugger",
    loop_id="<root_id from the first response — echo it back on every re-invocation; re-capture on loop_id_mismatch>",
    phases=[phase_0, phase_1, phase_2],  # Phase 0 reproduce · Phase 1 fix+falsify · Phase 2 RCA.
                                         # Each verifier declares metric_type="ground_truth"  ← as a
                                         # SPEC FIELD (sibling to assignee/title/body), NOT body prose.
                                         # Returns evidence:[Claim] (cited + re-opened).
    # discover={...},  # optional — engine-default discover runs regardless.
)
```

**⚠ Two load-bearing gotchas (observed on a real-board smoke):**

1. **`metric_type` is a verifier-SPEC FIELD, not body prose.** Write it as a key
   inside each `verifier:{}` dict (`"metric_type": "ground_truth"`), parallel to
   `assignee`/`title`/`body`. Mentioning "metric_type: ground_truth" *inside the
   body text* does NOT satisfy the validator — under `strict_fact_basis=True` the
   engine hard-rejects with *"phases[N].verifier.metric_type is required under
   strict_fact_basis"*. The field is validated at `_validate_metric_type`
   (`verifier.get("metric_type")`), which never reads the body.

2. **`loop_engine` needs a task context (interactive-session escape hatch).** The
   plugin's `_my_card_id()` reads `kwargs.get("task_id")` first, then falls back
   to `HERMES_KANBAN_TASK`. When you are a dispatcher-spawned worker, the env var
   is set for you and the tool schema carries `task_id` — just call the tool. But
   when you are driving the loop from an **interactive CLI session** (no env var,
   `task_id` absent from your tool schema because the tool layer strips it), the
   tool returns *"Cannot determine current task ID"*. The escape hatch: **mint a
   driver card yourself** (`kanban_create` assigned to `debugger`, get its id),
   then **call the plugin function directly via `execute_code`**, passing
   `task_id="<your-driver-card-id>"` in kwargs:

   ```python
   import importlib, os
   os.environ["HERMES_KANBAN_TASK"] = "<driver-card-id>"   # belt-and-braces
   os.environ["HERMES_KANBAN_BOARD"] = "<board-slug>"
   PLUGINS = "/home/<user>/.hermes-teams/startup/plugins"
   import sys; sys.path.insert(0, PLUGINS)
   le = importlib.import_module("loop_engine.tools")
   result = le.loop_engine(args_dict, task_id="<driver-card-id>", _profile="debugger")
   ```

   This bypasses the schema-stripping tool layer while honoring the exact same
   contract. (Root cause: `model_tools.py` passes `task_id=<process-env-captured>`
   to the plugin, NOT a per-call value, so the tool schema deliberately omits it.)
   Re-invoke the same way on every promotion (capture `root_id` from the first
   response, echo it as `loop_id`).

   **⚠ Park-failure-is-cosmetic (observed on every interactive smoke).** The
   engine's `_park_driver` calls `block_task(expected_run_id=_run_id())`, and
   `_run_id()` reads `HERMES_KANBAN_RUN_ID` — which is **unset** in an
   interactive session. Every invocation returns the park-failure error
   (`"driver not in running/ready state, or run_id mismatch (expected None)"`)
   even though the root card, execution card, verifier card, AND the
   `terminal → driver` dependency link were all created successfully. The
   dispatcher's `recompute_ready` advances the loop regardless: when the
   terminal completes, the dependency link promotes the driver, the
   dispatcher claims it under a new `run_id`, and the cycle continues. **Do
   not set `HERMES_KANBAN_RUN_ID` to a stale value** (that makes it worse —
   the card's actual `current_run_id` won't match). Leave it unset. Treat the
   park-failure error as success: **poll the terminal card's status** (via
   the board DB or `kanban_show`) until it reaches `done`, then re-invoke
   `loop_engine` (with `loop_id=root_id`) to read the verdict and advance.
   The loop converges through dispatcher-driven promotions, not through your
   direct park calls.

The sections below document what each field *does*; the template above is what
you actually *pass*. `strict_fact_basis=True` stays the first kwarg in every
example call in this skill — copy it literally each time.

### The v2 fact-based contract (`metric_type` + `evidence` + `loop_id` + `strict_fact_basis`)

The engine ships a **fact-discipline layer** (the v2 hard cutover). Your verifiers
do not just *assert* a verdict — they **declare** the kind of check and **return**
the evidence for it. Three fields govern this; `metric_type` + `evidence` are
**required** (a verifier omitting them fails the cutover), `loop_id` is the
drift-immune identity (recommended). The cutover is only advisory until a consumer
opts in — the debug-loop skill does so by passing **`strict_fact_basis=True`**
(workflow-wide), which is what makes the `metric_type` + `evidence` directives
below *enforced* (hard-rejected) rather than aspirational:

- **`metric_type`** (per verifier spec, T4): every verifier declares
  `ground_truth` (a mechanical, infallible check — test pass/fail, or a
  structural/citation check) or `proxy` (an LM-judged / gameable check).
  **All three debug-loop phases are `ground_truth`** — their DoD is test
  pass/fail (reproduce RED, fix + regression GREEN, falsification holds) or, for
  the RCA phase, the four mandatory inputs present + code-identifiers re-openable
  — not a judged "quality" score. A `proxy` verifier that names no
  `battery:{path, runner}` is a **validation error**: the loop refuses to run
  (proxy-without-battery IS the overfitting failure the layer exists to prevent).
  `ground_truth` needs no battery; the debugger never declares proxy.
- **`evidence`** (per `dod_verdict`, T3): every verdict carries
  `evidence: [Claim]`, and every **material** claim in it is **cited** — a
  `Claim` with `citations: [{artifact_type, locator, quote?}]`. The verifier
  **re-opens** each citation (reads the `file_line`, re-runs the
  `test_output`, checks the `commit_sha`) and quotes what it found. An un-cited
  material claim forces `dod_met=false` → replan. This is what makes "the fix is
  done" a fact, not a self-claim. Cite the repro test + its RED/GREEN output, the
  regression test at its correct seam, the green suite run, the falsification
  probe — each as a cited `Claim`.
- **`loop_id`** (T6, recommended): the durable identity of the loop is the
  **`root_id`** (the root card id the engine returns on the first call), NOT the
  goal hash. **Capture `root_id` from the first response and echo it back as
  `loop_id`** on every re-invocation. If the engine returns a
  `loop_id_mismatch` flag, **re-capture `root_id`** (the goal drifted or the root
  was re-minted) before continuing. This retires the byte-identical-goal
  fragility: `goal_hash` is now a bootstrap fallback only.
- **`strict_fact_basis`** (T9 — the opt-in MECHANISM, set workflow-wide on the
  `loop_engine` call): the debug-loop skill passes **`strict_fact_basis=True`** —
  it is the first consumer to make the fact-discipline layer *real*. The engine
  default is `False` (additive, zero-regression: an absent `metric_type` is
  accepted, a verdict with no `evidence` key passes). With the flag on, the layer
  HARD-REQUIRES both: (1) **`metric_type`** at the validate-seam — a verifier spec
  *without* `metric_type` is a **validation error**, the loop refuses to run (you
  already declare `ground_truth` on every verifier, so this is the safety net
  under you, not a new burden); (2) **`evidence`** at the evidence-gate — a
  verdict *without* an `evidence` key forces `dod_met=false` (bare "the fix is
  done" assertions do not advance; un-cited material already trips per T3,
  preserved). The engine never forces the cutover unilaterally — this flag is the
  debugger's explicit opt-in.

> **discover (T2) is engine-default:** the engine grounds the goal in evidence
> before phase 0 (it absorbs much of Round-0 prep — doctrine-read, worktree
> carve, ledger seed). You get it automatically; no skill change required. You
> MAY configure a custom `discover:{assignee, dod}` spec in the `loop_engine`
> call to sharpen the grounding for a particular bug class, but discover runs
> regardless.

### The `goal`, `runner`
- `goal`: the defect, written as one string — the symptom + the repro_attempt +
  env + stakes + originator + the bug-id + branch/worktree. This is posted to
  the root card blackboard and derives the root idempotency key. **MUST be byte-identical across EVERY `loop_engine` call for one bug** — the key is `loop:{driver}:{goal_hash}`; rewriting the goal between promotions (appending the hypothesis/fix) changes the hash, mints a NEW root, resets `phase_index` to 0, and the loop re-runs phase 0 forever instead of converging (observed: smoke-005). Hypotheses/fixes/verdicts go in phase bodies + the ledger, NEVER in the goal.
- `runner`: **`"debugger"`** — you. Execution/verifier cards that do not name
  their own assignee inherit `debugger`; each phase below names its own assignee
  to route to the right profile.
- `loop_id` (`root_id`, T6 — the drift-immune identity): the engine returns
  `root_id` on the first call. **Capture it and pass it back as `loop_id`** on
  every re-invocation — the loop is keyed on `root_id`, not the goal hash. If the
  engine returns `loop_id_mismatch`, re-capture `root_id` (the goal drifted or
  the root was re-minted) and continue. This is the structural fix for the
  byte-identical-goal fragility below; the goal-hash discipline is the
  disaster-recovery fallback.

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
| **Hypothesise + fix** + **Falsify** | **phase 1** (the converge loop) | `developer` (fix + regression test for the ranked hypothesis) | `verifier` — **falsifies** ("break it another way"; repro green + correct-seam test + suite green + root cause proven) **+ code-quality review** (style, fix-logic correctness, alternatives, no new debt) |
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
- **verifier.metric_type**: `ground_truth` — a RED/GREEN repro is a mechanical,
  infallible signal (no battery needed). The verifier RETURNS `evidence:[Claim]`:
  cite the repro test (`file_line`) + its RED output (`test_output`), re-opening
  each before setting `dod_met`.
- **No-repro path**: when the verifier escalates, `loop_engine` sticky-blocks
  your card (`needs_input`) — that IS the §6.1 HITL blocked card. Do not fire
  kanban. Comment the bead `human`, mint `bead-human-<bug-id>`, leave blocked.

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
- **verifier DoD** (in the verifier body — this *is* the falsify step, **plus a
  code-quality review** to match the implement-loop's maker/checker depth):
  "Evaluate the parent execution's fix. (1) The repro now goes GREEN. (2) A
  regression test exists at a **correct seam** (not a symptom-seam). (3) The full
  suite is green with no new regression. (4) **Falsify**: try to break it another
  way — exercise adjacent inputs/configs/paths the fix did not target. The root
  cause is *proven* (the fix addresses the cause, not the symptom). (5)
  **Code-quality review** (reuse the verifier profile's code-review capability —
  a full review, not just falsify): the fix is clean and idiomatic
  (style/cleanliness); the fix *logic* is correct (addresses the cause with the
  smallest sound change, no incidental behaviour change); alternatives were
  considered (at least one named alternative was rejected for a stated reason —
  read it from the developer's completion metadata, do not re-derive); no new
  debt is introduced (no TODOs, workarounds, or escape hatches papering over the
  cause). Return `dod_verdict`: `dod_met=true`/`recommendation=advance` only if
  all five hold; `dod_met=false`/`recommendation=replan` with concrete gaps if
  the fix is a symptom-fix, the repro is not green, OR a code-quality gap is
  material — cite it (`file_line` for style, the rejected alternative,
  introduced debt); `recommendation=escalate` with gaps naming `no-correct-seam`
  or `root-cause-spans-boundary` if the design-flaw signal is present (→ exit B)."
- **verifier.metric_type**: `ground_truth` — repro GREEN, regression test at a
  correct seam, full suite green, and falsification all pass/fail mechanically
  (no battery needed). The verifier RETURNS `evidence:[Claim]`: cite the now-green
  repro (`test_output`), the regression test at its seam (`file_line`), the green
  suite run (`test_output`), and the falsification probe (`probe_result` /
  `test_output`) — re-opening each. An un-cited "fix is done" claim forces
  `dod_met=false` → replan (no symptom-fix advances on assertion).
  **The (5) code-quality review does NOT change `metric_type`** — the declared
  gate stays `ground_truth` (the mechanical pass/fail the engine grades); the
  review is an *additional maker/checker duty instructed in the card body*,
  reusing the verifier's existing code-review capability. Its findings are
  reported as **cited evidence gaps** (`file_line` for style, the rejected
  alternative, introduced debt) that force `dod_met=false` → replan — still a
  fact, not a judged "quality score", so no `proxy`/`battery` is introduced and
  the v2 cutover invariant holds.
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
- **verifier.metric_type**: `ground_truth` — the RCA DoD is a **structural /
  citation check** (the four mandatory inputs present + code-identifiers cited and
  re-openable), not an LM-judged "quality" score. The four inputs are facts
  already established by the converged prior phases (repro achieved in phase 0,
  fix + falsification passed in phase 1); the verifier confirms the document
  records them faithfully. No battery needed. The verifier RETURNS
  `evidence:[Claim]`: cite the post-mortem path (`file_line`) + the code-identifiers
  it names (function/`file_line`, `commit_sha`), re-opening each. (If a future
  bug class made RCA quality a genuine judgment, that phase would declare
  `proxy` + a `battery:{path, runner}` — but the debugger's RCA DoD does not.)
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

### HITL = a blocked card, not a blocking call (§6.1)
When the repro cannot be built (no env access, no logs, no artifacts), you do
**not** create a blocked card ask. `loop_engine`'s escalation path
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
- **NEVER block the card for a missing repro** — HITL is a sticky blocked card.
- **NEVER merge the bug branch to main** — it lands on `debug/<bug-id>-<slug>`.
- **ALWAYS write the post-mortem at converge** (all four inputs).
- **ALWAYS take exit B** when the root cause has no correct seam / spans a boundary.
- **ALWAYS use the board (`loop_engine` + cards), not subagents, for fan-out.**
- **ALWAYS pass the EXACT SAME `goal` string to every `loop_engine` call for one bug** — it derives the loop's bootstrap idempotency key. Any drift (added hypothesis/fix/verdict) mints a new root and resets `phase_index` to 0 → the loop re-runs phase 0 forever and never reaches RCA. Mutate phase bodies + ledger between calls; never the goal. **PREFER `loop_id` (root_id)** — capture + echo `root_id`; it keys the loop directly so goal-hash drift cannot reset it. Handle `loop_id_mismatch` by re-capturing `root_id`.
- **ALWAYS declare `metric_type` on every verifier** — `ground_truth` for all three debug-loop phases (test pass/fail + the RCA's structural/citation check). Never `proxy` without a `battery:{path, runner}`.
- **ALWAYS return evidence-cited `dod_verdict`s** — every material claim cited (`file_line` / `test_output` / `commit_sha` / `probe_result`) and re-opened by the verifier. Un-cited material forces `dod_met=false` → replan; nothing advances on assertion.
- **ALWAYS pass `strict_fact_basis=True`** (workflow-wide) on your `loop_engine` call — opts the debugger into the T9 hard cutover: every verifier hard-requires `metric_type` (validation error without it; the loop refuses to run) and every verdict hard-requires `evidence` (a bare / no-`evidence` verdict forces `dod_met=false` → replan). The engine default is `False` (additive); this skill flips it so the `metric_type` + `evidence` rules above are *enforced*, not advisory.
