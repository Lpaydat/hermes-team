# loop_engine — the durable-board converge-loop engine

> **SPEC.md is the design authority** (§Fact-Based Loop Enhancement (v2)). This
> README is the consumer how-to + the v1→v2 migration guide. It documents the
> **actual** tool-input contract in `schemas.py` and the engine behavior in
> `tools.py` — verified against the code, not aspiration.

---

## 1. What loop_engine is

`loop_engine` is the plugin that drives an iterative **converge-loop** on the
kanban board with durable state. A workflow's `goal` is decomposed into ordered
**phases** (discover → execute → verify); each phase runs its own converge-loop
on the board — an execution card, an independent verifier card, and a
dependency-parked driver. The tool is invoked **once per promotion** of the
loop-driver card; each invocation runs ONE iteration of the outer phase-loop.

- **First invocation** — builds the topology (root card + phase sub-graphs),
  writes `loop_state` to the root blackboard, dependency-parks the driver,
  returns `status=blocked`.
- **Re-invocation** (auto-promoted once the terminal completes) — reads
  `loop_state`, reads the terminal's `dod_verdict`, and decides: DoD met →
  advance to the next phase (or workflow complete); DoD not met → replan (fresh
  execution + verifier); cap / budget / no-progress → sticky HITL escalation.

**Termination is deterministic** (plugin code, never model-enforced — SPEC
§Termination is safety-critical, therefore deterministic).

The v2 layer adds **fact-discipline**: discover grounds the goal in evidence
before phase 0, evidence gates the verdict (`dod_met` requires cited material
claims), and metric-typing catches gameable proxies (a proxy metric requires a
held-out battery). Each phase's verdict becomes a cited fact, not a self-claim.

---

## 2. The tool input contract

Every `LOOP_ENGINE` schema property (from `schemas.py`). This is THE reference
for what a consumer can pass. Top-level `required: ["goal"]`; exactly one of
`execution` or `phases` must be present (`anyOf`).

### Core

| Property | Type | Required? | Default | What it does |
|---|---|---|---|---|
| `goal` | `string` | **yes** | — | What the workflow accomplishes. Posted to the root card blackboard and used to derive the root idempotency key (`loop:{driver}:{sha1(goal)[:10]}`). **Must be byte-identical across every call for one loop** unless you use `loop_id`. The engine also accepts a `[Claim]` array (the structural fast-pass — a pre-grounded goal skips the discover worker); the schema types it `string` only. |
| `runner` | `string` | no | `"worker"` | The profile that drives the loop and that execution/verifier cards default to when they don't name their own `assignee`. Resolution order: configured runner → `worker` → `default`. Omit to use `worker`; an explicit card `assignee` overrides it. |
| `execution` | `object` | one-of | — | The ONE execution card to run this iteration (single-phase path). Parented on the root. Shape: `{assignee?, title, body, skill?}`, `required: [title, body]`. |
| `phases` | `array` | one-of | — | Ordered list of phase specs (multi-phase path). Each phase runs its own converge-loop with its own DoD. When supplied, top-level `execution`/`verifier` are not required. Phase shape: `{execution, verifier?, max_iterations?}`, `required: [execution]`. |

### v2 fact-based

| Property | Type | Required? | Default | What it does |
|---|---|---|---|---|
| `strict_fact_basis` | `boolean` | no | `false` | **T9 opt-in** — the fact-based cutover mechanism. When `true`, the loop hard-requires `metric_type` on every verifier (validation error, the loop refuses to run) AND `evidence` on every verdict (a bare verdict forces `dod_met=false` → replan). Persisted to `loop_state` so the decide-time evidence gate reads it on every re-promotion (the driver is stateless between iterations). Default `false` = zero-regression additive behavior. A per-verifier `strict_fact_basis` overrides upward (`true` wins). |
| `loop_id` | `string` | no | — | **T6** — the durable loop handle (aliased to `root_id`). On re-invocation, echo the `root_id` captured from the first response here: the engine opens that exact card and reads `loop_state` directly, with **no goal_hash derivation** (drift-immune — kills the goal-drift defect class). Omit on the FIRST call to use the goal_hash bootstrap fallback. The engine also accepts `root_id` as a synonym. A supplied `loop_id` that does not resolve fires a `loop_id_mismatch` event and falls back to goal_hash. |
| `discover` | `object` | no | engine-default | **T2** — optional discover phase-0 config `{assignee?, dod, max_iterations?}`, `required: [dod]`. When present + bare-string goal, the engine dispatches a grounding worker before `phases[0]` and parks on it. Omit to use the engine-default discover (see migration §discover). |
| `strict_dod` | `boolean` | no | `false` | **T8 opt-in** — strict-definition-of-done. When `true`, the verifier's DoD must include structured `dod_signals` (a pure-prose DoD is hard-rejected at validation). Default `false` = prose-DoD compat (a pure-prose DoD is warned but the loop proceeds). A per-verifier `strict_dod` overrides upward. |

### Loop-control

| Property | Type | Required? | Default | What it does |
|---|---|---|---|---|
| `max_iterations` | `integer` | no | `5` | Hard iteration cap for the verifier-gated converge loop. The loop replans while `dod_met` is false and the count is under the cap; on reaching the cap without DoD met it escalates to a sticky HITL block. Ignored in T1 mode (no verifier) and when `phases` is supplied (each phase carries its own `max_iterations`). |
| `budget` | `integer` | no | `None` | Workflow-wide cost-unit budget. Each completed iteration consumes one cost unit. When exhausted before the DoD is met, the loop escalates to HITL (sticky `needs_input` block + `loop_escalated` event) rather than terminating. Omit / `null` for no budget guard (the hard cap still bounds the loop). |
| `no_progress_threshold` | `integer` | no | `2` | Escalate when the verifier verdict is byte-identical across this many consecutive iterations (the replan is not making progress). Set higher to tolerate more repetition; set large to effectively disable. |

### The `verifier` object — and a schema-surfacing caveat

The schema's `verifier` (and each phase's `verifier`) lists only
`{assignee, title, body, skill}`. The v2 engine **also reads and validates**
these fields off the verifier object:

| Verifier-spec field | Type | What it does |
|---|---|---|
| `metric_type` | `"ground_truth" \| "proxy"` | **T4** — declares the kind of metric gating this phase. `ground_truth` = a mechanical, infallible check (test pass/fail, grep, count); needs no battery. `proxy` = a gameable judgment (LLM-rubric, human rating); **requires** `battery`. Under `strict_fact_basis`, an absent `metric_type` is a validation error (the loop refuses to run). |
| `battery` | `{path: string, runner: string}` | **T5/B6** — the held-out battery spec, required when `metric_type="proxy"`. The engine dispatches a SEPARATE independent battery card (assigned to `battery.runner`, never the phase exec) as a terminal gate; both the verifier AND the battery must pass. A proxy verifier without a well-formed battery is a validation error. |
| `dod_signals` | `[DoDSignal]` | **T8** — a non-empty array of `{artifact_type, locator, expectation?}` declaring a machine-checkable DoD. Absent = compat warn (loop proceeds); under `strict_dod`, absent = hard-fail. Present-but-malformed always hard-fails. |
| `strict_fact_basis` | `boolean` | per-verifier override of the workflow-wide flag (`true` wins). |
| `strict_dod` | `boolean` | per-verifier override of the workflow-wide flag (`true` wins). |
| `artifact_required` | `boolean` | opt-in DoD-artifact gate (the design-council converge use case). When `true`, the engine independently asserts the verdict carries complete `behaviors[]` + `defect_traces[]` with no unfixed latent defect. Default `false` (generic; defers to `dod_met`). |

> **CONTRACT GAP (verifier-spec level):** these fields are NOT yet listed in the
> schema's `verifier.properties`. They pass through (JSON Schema's
> `additionalProperties` defaults to `true`) and the engine validates them, but
> an agent inspecting the schema sees only `{assignee, title, body, skill}`. This
> is the **same invisible-field gap class** as the `1h5` top-level fix, one
> nesting level down. **Your consumer skill template MUST instruct passing them
> explicitly** — the debug-loop smoke proved a weak-context driver drops fields
> that live only in prose. Until the schema surfaces them, the skill's literal
> call template is load-bearing (see §5 Worked example).

### What the verifier RETURNS — the `dod_verdict`

The verifier card completes with a `dod_verdict` in `run.metadata` via
`kanban_complete(metadata={'dod_verdict': ...})`:

```
dod_verdict = {
  dod_met: bool,                         // DoD satisfied (gated by evidence — see below)
  score: number,                         // DoD-quality 0..1 (informational; NOT routed on)
  gaps: [{dimension, issue}],            // what's missing (fed to the replan)
  recommendation: "advance"|"replan"|"escalate",
  evidence: [Claim],                     // v2 — every material claim + its citations
}
```

**Evidence gates `dod_met`** (the core of B4/T3): a "done" verdict carrying an
un-cited material claim does NOT advance — the engine forces `dod_met=false` and
`recommendation="replan"`. Under `strict_fact_basis`, a verdict with NO
`evidence` key also trips. Additively, a bare v1 verdict (no `evidence` key)
passes unchanged when `strict_fact_basis=false` — zero-regression.

### The Citation / Claim primitive (T1)

The shared fact representation, used by BOTH discover (input grounding) and the
evidence gate (output evidence):

```
Citation = { artifact_type: <enum>, locator: <string>, quote?: <string> }
Claim     = { text: <string>, citations: [Citation], material?: <bool=true> }
```

- **`artifact_type`** open enum (seed): `file_line`, `test_output`,
  `grep_result`, `commit_sha`, `url`, `adr_doc`, `probe_result`,
  `error_string`. Extensible via `schemas.register_artifact_type()` (`count` is
  registered at module load for DoD signals).
- **`material`** (default `true`) — a material claim MUST carry ≥1 citation;
  an un-cited material claim is the hard-fail primitive. Set `material=false`
  for a non-load-bearing framing statement.
- The engine enforces **structure only** (type ∈ enum, locator non-empty). The
  independent verifier card **re-opens** each citation (reads `file:line`,
  re-runs the probe, checks the sha) per the existing independent-verifier trust
  model.

---

## 3. v1 → v2 migration

What changed, and what a v1 consumer must do.

### discover (T2) — engine-default, always-on

A **discover phase-0 card is minted for EVERY loop** (SPEC §2: "always-on,
engine-governed phase 0... v1 callers get it automatically, +1 phase"). The
card's lifecycle is adaptive:

| Goal form | `discover:{...}` configured? | Behavior |
|---|---|---|
| bare string | yes | **DISPATCH** — the discover worker grounds the goal; driver parks on it; user phases run after a scope-clear verdict. |
| bare string | no | **FAST-PASS** — discover card minted as a resolved skeleton (`discover_state="unconfigured"`); no worker dispatched; falls through to `phases[0]`. |
| `[Claim]` (pre-grounded) | any | **FAST-PASS** — discover card minted as a resolved skeleton (`discover_state="skipped"`); the goal claims become the context brief; no worker dispatched. |

**v1 consumer action:** none required — a bare-goal v1 caller gets the discover
skeleton automatically (zero behavior change, +1 visible phase-0 card). To
actually run grounding, pass `discover:{assignee, dod, max_iterations?}` and a
bare-string goal.

### evidence (T3) — cited claims gate the verdict

The verifier `dod_verdict` should carry `evidence: [Claim]` (cited material
claims). The engine enforces:

- **Additive (default):** a verdict with `evidence` present is validated — an
  un-cited material claim forces `dod_met=false` → replan. A bare v1 verdict
  (no `evidence` key) passes unchanged.
- **Under `strict_fact_basis`:** `evidence` becomes HARD-REQUIRED — a verdict
  with no `evidence` key trips the gate → `dod_met=false` → replan. Nothing
  advances on assertion.

**v1 consumer action:** have your verifier skills return `evidence: [Claim]`
(re-open each citation before setting `dod_met`). If you don't opt into
`strict_fact_basis`, a bare verdict still works — but un-cited material always
trips once `evidence` is present.

### metric_type (T4) — declare the metric kind

Each verifier declares `metric_type: "ground_truth" | "proxy"` as a **spec
field** on the verifier object (sibling to `assignee`/`title`/`body` — NOT body
prose).

- `ground_truth` — a mechanical, infallible check (test pass/fail, grep, count).
  No battery needed.
- `proxy` — a gameable judgment (LLM-rubric, human rating). **`battery:{path,
  runner}` is REQUIRED** — a proxy verifier without a well-formed battery is a
  validation error; the loop refuses to run (proxy-without-battery IS the
  overfitting failure the layer exists to prevent).
- **Absent `metric_type`** is accepted (default-compat, treated as
  `ground_truth`) UNLESS `strict_fact_basis` is on — then it's a validation
  error.

**v1 consumer action:** add `metric_type` to each verifier spec. Most
verifiers are `ground_truth`. If you have a judgment-based DoD, declare `proxy`
+ a `battery`. See the schema-surfacing caveat in §2.

### battery (T5) — the held-out independent gate

A proxy phase gets a **separate battery card** (terminal independent gate). The
engine dispatches it to `battery.runner` (never the phase exec agent —
independence is load-bearing). The battery is itself a verifier: it re-grades
the phase output against the disjoint battery artifact at `battery.path` and
completes with its own evidence-cited `dod_verdict`.

- **Both the verifier AND the battery must pass** for the phase to advance.
- **Battery fail → replan** the phase with the battery's gaps fed back (the
  proxy leaked; re-converge). Bounded by the same deterministic layered exits.

**v1 consumer action:** none, unless you declare `proxy`. Ground-truth / v1
verifiers (no `metric_type`) never get a battery card — zero-regression.

### root_id / loop_id (T6) — drift-immune identity

The durable identity of a loop is `root_id` (the root card's task id), NOT the
goal hash.

- **First call:** omit `loop_id`. The engine mints the root via the goal_hash
  bootstrap fallback and returns `root_id` in the response.
- **Re-invocation:** echo `root_id` back as `loop_id`. The engine opens that
  exact card and reads `loop_state` directly — no goal_hash derivation, no
  goal-byte sensitivity. This **kills the goal-drift defect class** (a rewritten
  goal no longer mints a fresh root and resets `phase_index` to 0).
- **`loop_id_mismatch`:** if a supplied `loop_id` does not resolve (stale /
  garbage), the engine fires a `loop_id_mismatch` event and falls back to
  goal_hash. Re-capture `root_id` and continue.

**v1 consumer action:** capture `root_id` from the first response; echo it as
`loop_id` on every re-invocation. The goal_hash discipline (byte-identical goal)
becomes the disaster-recovery fallback, not the primary path.

### strict_fact_basis (T9) — the opt-in cutover

**Opt-in. Default `false`** (zero-regression, additive). Set `true` to HARD-REQUIRE:

1. **`metric_type`** at the validate-seam — a verifier spec without `metric_type`
   is a validation error; the loop refuses to run.
2. **`evidence`** at the evidence-gate — a verdict without an `evidence` key
   forces `dod_met=false` (nothing advances on assertion; un-cited material
   already trips per T3, preserved).

The engine **never forces the cutover unilaterally** — this flag is the
consumer's explicit opt-in.

> **Lesson from the smokes:** the agent only passes `strict_fact_basis` reliably
> because the SCHEMA surfaces it (the `1h5` fix). The same applies to
> `metric_type` / `battery` / `dod_signals` — except those are NOT yet in the
> schema's verifier.properties (see §2 caveat). **Ensure your consumer's skill
> instructs passing them as literal kwargs in the call template**, not just in
> prose.

### strict_dod (T8) — opt-in DoD-checkability

**Opt-in. Default `false`** (prose-DoD compat — a pure-prose DoD is warned but
the loop proceeds). Set `true` to HARD-REQUIRE structured `dod_signals` on each
verifier (a pure-prose DoD is hard-rejected at validation). Present-but-malformed
signals always hard-fail (the consumer opted into structure by providing the
key).

### Citation / Claim (T1) — the shared fact primitive

`Citation{artifact_type, locator, quote?}` + `Claim{text, citations[],
material?}`. `artifact_type` enum: `file_line`, `test_output`, `grep_result`,
`commit_sha`, `url`, `adr_doc`, `probe_result`, `error_string` (+ `count`,
extensible via `register_artifact_type`). See §2 for the full shape.

---

## 4. Zero-regression vs hard-cutover

| Tier | Fields / behaviors | Default | v1 consumer impact |
|---|---|---|---|
| **Default (additive)** | discover always-on (skeleton card); evidence gate fires only when `evidence` is present; `metric_type` absent = accepted; battery cards never materialize without `proxy`; `loop_id` absent = goal_hash fallback | on | **A v1 consumer works unchanged.** +1 visible discover skeleton card; everything else byte-for-byte. |
| **Opt-in** | `strict_fact_basis` (hard-requires `metric_type` + `evidence`); `strict_dod` (hard-requires `dod_signals`) | `false` | **Unchanged unless you flip the flag.** When on, the loop refuses to run / forces replan on the respective gaps. |
| **Required-when-declared** | `metric_type="proxy"` → `battery:{path, runner}` REQUIRED | fires on declaration | **Only if you declare `proxy`.** Ground-truth / undeclared verifiers are unaffected. |

**Bottom line:** a v1 consumer works unchanged UNLESS it opts into
`strict_fact_basis`. The fact-based cutover is per-consumer opt-in, not a
unilateral engine flip.

---

## 5. Worked example — the debug-loop canonical call

The reference v2 consumer is the **debug-loop** skill
(`startup/profiles/debugger/skills/software-development/debug-loop/SKILL.md`).
It passes `strict_fact_basis=True` (workflow-wide) as the **first kwarg** —
the one field a weak-context driver quietly drops if it lives only in prose.
Each verifier declares `metric_type="ground_truth"` (a SPEC field, not body
prose) and returns `evidence:[Claim]`.

```python
loop_engine(
    strict_fact_basis=True,   # T9 opt-in — REQUIRED. Arms the fact-discipline
                              # layer: metric_type + evidence become HARD-REQUIRED.
                              # FIRST kwarg on purpose.
    goal="<defect: symptom + repro_attempt + env + stakes + bug-id + branch — BYTE-IDENTICAL across calls>",
    runner="debugger",
    loop_id="<root_id from the first response — echo on every re-invocation>",
    phases=[
        # phase 0 — reproduce
        {"execution": {..., "assignee": "developer"},
         "verifier": {"title": "...", "body": "<DoD: tight RED achieved>",
                      "metric_type": "ground_truth", "assignee": "verifier"},
         "max_iterations": 3},
        # phase 1 — hypothesise + fix + falsify (the converge loop)
        {"execution": {..., "assignee": "developer", "skill": "developer-loop"},
         "verifier": {"title": "...", "body": "<DoD: repro GREEN + correct-seam regression + suite green + falsify>",
                      "metric_type": "ground_truth", "assignee": "verifier"},
         "max_iterations": 5},
        # phase 2 — converge / post-mortem (RCA)
        {"execution": {..., "assignee": "debugger"},
         "verifier": {"title": "...", "body": "<DoD: all 4 RCA inputs present + code-identifiers cited>",
                      "metric_type": "ground_truth", "assignee": "verifier"},
         "max_iterations": 2},
    ],
    # discover={...},  # optional — engine-default discover runs regardless.
)
```

Key points (proven on a real-board smoke):

1. **`strict_fact_basis=True` is the first kwarg** — copy it literally. The
   engine default is `false`; the schema surfaces it (post-`1h5`), but a
   weak-context driver still drops it if it's only in prose.
2. **`metric_type` is a verifier-SPEC FIELD**, not body prose. Write it inside
   each `verifier:{}` dict, parallel to `assignee`/`title`/`body`. Mentioning
   "metric_type: ground_truth" inside the body does NOT satisfy the validator.
3. **Capture `root_id` from the first response; echo it as `loop_id`** on every
   re-invocation. Handle `loop_id_mismatch` by re-capturing `root_id`.
4. **Verifiers return `evidence:[Claim]`** — cite the repro test, the regression
   test, the green suite, the falsification probe. Each citation re-opened
   (reads `file:line`, re-runs `test_output`, checks `commit_sha`).

See the debug-loop SKILL.md for the full phase→DoD→assignee→verifier mapping.

---

## 6. Install — the 4 enable gates

For the `loop_engine` tool to reach a worker session, all four enable gates
must be open (T7 — the install-defect class that blocked the debugger smoke):

1. **Plugin enabled** — the plugin is listed in the plugins config
   (`plugins.enabled` / the plugin manifest is active).
2. **Global enable** — loop_engine is enabled at the global/deployment level
   (not disabled by a global flag).
3. **Profile toolset** — the driving profile's toolset includes `loop_engine`
   (the profile must declare the tool / inherit the plugin's tools).
4. **Plugin symlink** — a symlink to the plugin exists in
   `startup/profiles/<profile>/plugins/loop_engine` so the profile's
   `PluginManager.discover_and_load()` finds it (the discovery gate — the one
   most easily missed).

If any gate is closed, the tool is invisible to the worker session (no error,
just absent from the tool list). Verify by loading via the REAL
`PluginManager.discover_and_load()` against a throwaway profile, not by
direct-import (T7 install-smoke pattern).

---

## 7. Design authority

**SPEC.md** (`startup/plugins/loop_engine/SPEC.md`) is the design authority —
§Fact-Based Loop Enhancement (v2) is the settled design (wayfinder map
`hermes-teams-j3z`; each subsection links its resolved design ticket via
`bd show <id>`). This README is the consumer how-to; when they disagree, SPEC
wins.
