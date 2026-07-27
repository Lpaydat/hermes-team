---
name: design-council
description: Run an irreversible design decision through a research-backed council with an independent DoD verifier before recording the ADR. Use when you owe an architecture decision or ADR, or when a design-it-twice comparison is called for — any design output that must not come from one agent's memory alone. Driven by the loop_engine plugin.
---

A design decision owed by the architect is **council** work, not memory
retrieval. The council is driven by **`loop_engine`** — a generic converge-loop
engine that executes a phase, has an independent **verifier** check a concrete
**definition-of-done**, and replans / advances / escalates on the structured
verdict. The ADR is built from research, critique, a defect-coverage artifact,
and a live PO discussion — never from one agent's training memory.

The iteration signal is the **DoD verdict**, not the architect's
self-confidence and not a 1–5 quality score (a leaky proxy: the v2 council
converged at 4.47/5 yet missed a latent defect). The DoD is a concrete,
checkable contract; for design phases it includes a **defect-coverage
artifact** (`behaviors[]` + `defect_traces[]`) the engine mechanically
validates — see [`references/dod-contract.md`](references/dod-contract.md).
The loop **executes → evaluates the DoD → keeps/discards → converges**,
monotonically; a `latent_defect` trace hard-blocks advance.

**Leading words.** *council* — the multi-perspective deliberation. *stakes* —
the project's value/risk tier, **declared by the PO on the design card**
(low / standard / high); sets the loop_engine phases, the cap, the
no-progress threshold, *and* the verifier shape. *floor* / *ceiling* — the
minimum and maximum council effort. *DoD* — the definition-of-done the verifier
checks (concrete items, pass/fail). *defect-coverage artifact* —
`behaviors[]` (every stated brief behavior) + `defect_traces[]` (one CITE+GAP+
FAILURE chain per behavior); the engine validates it before trusting `dod_met`.
*best-so-far* — the highest-scoring design version, persisted by the driver to
`council:best_so_far`; the revert target when a round regresses. *interview* —
a distinct post-convergence phase: a live kanban comment with the PO before the
ADR. *blackboard* — the shared root card `loop_engine` creates; the driver
persists `council:last_iteration` + `council:best_so_far` + `council:po_interview`
there. *workflow_complete* — the engine's terminal signal (last phase DoD met).

## Decompose into decisions — and check coverage

Break the design into decisions (one ADR each), one **phase** at a time. Use
the architectural dimensions as a **coverage checklist**: data model,
security/auth, infrastructure/deployment, API surface, cross-cutting. Ensure
your decision set covers each dimension that applies.

**Defect coverage — trace every stated behavior, not just the first gap.** This
is now a **required artifact** the verifier produces and the engine validates
(see [`dod-contract.md`](references/dod-contract.md) § DEFECT-COVERAGE):
enumerate **every behavior the brief or ADR states**, derive **each one's
failure implication** as a CITE+GAP+FAILURE chain, and do not stop at the first
defect — a single design can carry **multiple distinct latent defects**. The
verifier's `dod_met` is not trusted alone: the engine asserts every behavior
has a trace, no trace is fabricated, and no trace is left `latent_defect`
before it advances.

## The loop — one decision (driven by loop_engine)

1. **Assess.** Take **stakes** from the card (PO-declared). Rate complexity by
   the blast-radius instinct. Apply the **auth-guardrail** (load-bearing — the
   engine cannot enforce domain): a decision touching **security / auth /
   data-loss / irreversible-state is NEVER low** — force standard or high; a
   throwaway auth decision would ship with no gate (low = T1, no verifier).
   Stakes fixes the loop_engine phases, the cap, the no-progress threshold, and
   the verifier shape (rubric below).

   *Done when:* stakes, tier, and the loop_engine phases config are chosen.

2. **Call `loop_engine` once.** Author ONE `loop_engine({goal, runner:"architect",
   phases:[...], no_progress_threshold})` call with the tier's phases config
   from [`references/call-templates.md`](references/call-templates.md). The
   engine owns the rest: it creates the root blackboard, drives each phase's
   execute→evaluate→decide cycle, persists `council:*` state, and
   advances/escalates on the DoD verdict. You write nothing during the loop and
   do not hand-call `kanban_chains` / `kanban_block` / evaluator cards at the
   top level — the engine is the topology author on its root subtree.

   The phases (standard + high): **(0) council-converge** — the T2
   verifier-gated converge loop (each iteration's execution card nests a
   `kanban_chains` researcher+peer fan-out, then synthesizes a design-doc
   version; the verifier evaluates the DoD artifact; the driver persists
   `council:last_iteration` + `council:best_so_far`); **(1) PO-HITL interview**
   — a distinct T1 phase reached only after phase 0 `dod_met`-advance; the
   worker calls kanban comment, self-blocks `needs_input` on timeout, and is
   re-entrant; **(2) ADR-record** — a T2 phase whose verifier checks ADR
   convention only. Low = 2 T1 phases (converge + ADR, no interview, no
   verifier).

   *Done when:* `loop_engine` returned and your card is dependency-parked.

3. **On `workflow_complete`.** The engine returns `decision=workflow_complete`
   when the last phase (ADR-record) DoD is met. Confirm the ADR is on disk at
   `docs/adr/<n>-<slug>.md` with Context / Alternatives-Considered / Decision /
   Consequences / Citations, citing research + perspectives + the converge
   verdict (with the `defect_traces` that caught any gap) + `council:po_interview`.

   *Done when:* ADR on disk, all council inputs + the DoD verdict cited.

## The floor

Every ADR is the output of at least one council round — **≥1 research card +
≥1 peer-architect perspective**, with you parked throughout, never memory-only.
Low stakes meets this with the minimum (T1: 1 converge phase = 1 research + 1
peer, 1 iteration, no verifier, no PO interview). At low stakes the floor IS
the ceiling; the verifier is not spawned (loop_engine T1 spine).

## The ceiling

Caps are **stakes-scaled** (rubric below). Convergence is the verifier's
`dod_met` (every item pass + every behavior traced + no critical/important
gap), validated by the engine's artifact gate. **Ceiling hit without convergence
no longer auto-ships a residual-risks ADR** — the engine escalates to a sticky
`needs_input` card (`hard_cap`) naming exactly what the human owes. That is a
strengthening: a design that cannot meet the DoD within the cap is escalated,
not rubber-stamped.

## Keep/discard — the best-so-far version

Each converge iteration produces a design-doc version. The driver persists
**`council:best_so_far`** (the highest-scoring version's snapshot) to the root
blackboard. A **regressing** iteration (lower score) does NOT overwrite
best-so-far; the next replan execution worker reads `council:last_iteration` +
`council:best_so_far` and **revises from best-so-far**, discarding the regressed
version. The design monotonically improves. (Backstop: even if best-so-far
tracking fails, the artifact gate re-traces every behavior each iteration, so a
reintroduced `latent_defect` forces `dod_met=false` → replan regardless.)

## Rubric — stakes sets the phases, cap, no-progress threshold, and verifier

| Stakes (PO-declared) | loop_engine phases | Cap (max_iterations) | no_progress_threshold | Verifier |
|---|---|---|---|---|
| **Low** (prototype / internal / throwaway) | `[converge T1, ADR T1]` | MAX_PHASE_STEPS=1 (each phase runs once) | n/a | **none** (T1 spine). Auth-guardrail refuses low for auth/security/data-loss. |
| **Standard** (default) | `[converge cap3, interview T1, ADR cap2]` | 3 | 3 | **single judge** (`verifier`, `dod-verdict` skill) |
| **High** (revenue / safety / brand / hard-to-reverse) | `[converge cap5, interview T1, ADR cap2]` | 5 | 3 | **ensemble of 3** (verifier-side `kanban_chains` fan-out; union `latent_defect`s, `dod_met`=AND) |

The verifier's **noise floor**: minor-severity gaps alone do not block
convergence. High-stakes ensemble convergence requires `dod_met` = AND of the
three judges (a `latent_defect` flagged by ANY judge blocks).

The PO **interview** is a distinct **post-convergence** phase (phase 1),
reached only after the converge phase `dod_met`-advances — never a per-iteration
escalation. (At high stakes, the per-round PO *review* is different — that is
an `after`-step in the execute fan-in judging product fit, not a HITL
escalation.)

## Calling loop_engine

The three `loop_engine({goal, runner:"architect", phases:[...]})` call shapes
(low / standard / high), with the exact execution + verifier + interview + ADR
card bodies (defect-coverage DoD, fabrication guard, re-entrant interview,
3-judge ensemble), are in
[`references/call-templates.md`](references/call-templates.md). The DoD
contract (items + `dod_verdict` schema + engine validation) is in
[`references/dod-contract.md`](references/dod-contract.md).

Inline essentials:

- **`strict_fact_basis: true` is the FIRST kwarg** (loop_engine v2, literal not
  prose) — arms the fact-discipline layer: `metric_type` + `evidence` become
  hard-required. A weak-context driver drops it if it lives only in prose.
- **Capture `root_id` from the first response; echo it as `loop_id`** on every
  re-invocation — drift-immune identity (a rewritten goal no longer resets the
  loop). The goal_hash is the disaster-recovery fallback, not the primary path.
- **Optionally pass `discover:{dod}`** to ground the goal in the brief's stated
  behaviors + constraints before converge (a phase-0 grounding worker). Omit for
  the engine-default fast-pass skeleton (zero-regression).
- **The converge verifier is `metric_type: "proxy"` + a `battery`** pointing at
  `verifier/secrets/dc-val-battery-secrets.md` — the engine dispatches the
  held-out battery as a **phase terminal** (both verifier AND battery must pass).
  The ADR-record verifier is `metric_type: "ground_truth"` (mechanical; no battery).
- **Explicit `assignee` on every card spec** is load-bearing — `runner` falls
  back to `worker`/`default` (no such profile dirs), so omitting `assignee`
  stalls. Set `assignee:"architect"` on execution cards, `assignee:"verifier"`
  on verifier cards.
- **Researcher skill names**: use `skills:["docs-verification"]` for
  auth/security decisions (it holds the ground-truth references) and
  `skills:["research-scout"]` or `["deep-research"]` for general research.
  There is **no skill named `"research"`**.
- **Converge execution body** must read `council:last_iteration` +
  `council:best_so_far` from the root blackboard (the engine injects the root
  card id into the body footer) for keep/discard + gap-targeted replan.
- **Converge verifier body** embeds the DoD as the `behaviors[]` +
  `defect_traces[]` artifact with the fabrication guard, completes via
  `kanban_complete(metadata={"dod_verdict":{...}})`, and honors the contract
  (`recommendation` must not be `advance` unless `dod_met` is true). The
  standing `dod-verdict` skill on the verifier profile backs this up.
- **Interview body** is re-entrant: on resume, if `council:po_interview` is
  already on the root blackboard, complete immediately; else kanban comment,
  and on timeout / `[target_not_connected]` `kanban_block(kind="needs_input")`
  on yourself — never proceed without PO input.
