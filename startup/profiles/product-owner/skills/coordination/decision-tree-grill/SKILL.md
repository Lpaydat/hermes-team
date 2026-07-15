---
name: decision-tree-grill
description: "Drive a grill's decision tree to FULL resolution, backed by beads (bd) so it never contends with the kanban dispatcher/execution engine. Creates dt:fact/dt:decision beads wired by bd deps, walks the frontier (bd ready) resolving facts by lookup + decisions by asking the user-rep, forks new branches as answers reshape the tree, and exits only when the frontier is empty — objective confidence (no self-report). Use to run grill-with-docs to completion without fake-confidence. Labels: decision-tree, dt:root, dt:fact, dt:decision."
---

# decision-tree-grill — drive the grill's decision tree to completion (beads-backed)

`grill-with-docs` runs a `grilling` interview whose mental model is a **decision tree**:
every plan branches into decisions; decisions depend on each other; an early answer reshapes
which questions come next. Confidence is real only when the tree is **fully walked** — every
branch resolved, no dangling dependencies. (mattpocock/skills#132: confidence-building =
"audit the trail, walk the path" = walk the tree.)

This skill drives that tree to completion with an **objective gate** (frontier empty), not a
self-reported 0–1 score — so the LLM cannot fake confidence. It uses **beads (bd)** as the
graph store, **not kanban**, so it never contends with the dispatcher or execution engine.

## The model

- **Root bead** = the thing being grilled (the venture, the plan). Open until the tree is done.
- **Decision/fact beads** = the tree's nodes. Each **blocks the root** (`bd dep <node> --blocks <root>`) — the root can't complete until all its nodes resolve.
- **Node types** (labels):
  - `dt:fact` — resolvable by **lookup** (read the brief, codebase, docs, research). AFK.
  - `dt:decision` — resolvable only by the **user-rep** (VB / the human). HITL.
- **Frontier** = open `dt:*` beads with no active blockers = `bd ready -l decision-tree`.
- **Forking** = resolving a node may surface new sub-decisions → create child `dt:*` beads that block the root (the answer reshaped the tree).
- **Completion** — ALL THREE required (frontier-empty alone is NOT enough; it's gameable by moot-closing):
  1. no open `dt:fact`/`dt:decision` beads remain (root's blockers all closed); AND
  2. EVERY `dt:decision` was closed with a recorded **VB answer** (`bd comment` "VB: <verbatim>") — never a PO self-judgment / "moot"; AND
  3. `CONTEXT.md` exists with ≥1 pinned term (domain-modeling fired — language actually pinned).
  All three → `bd close` the root. If (1) holds but (2) or (3) don't, the grill was **fake-completed** — re-open the offending nodes and resolve them properly. Confidence = all three met (mechanical).

## Hard rules (anti-fake-completion — learned from round-1)

- **A `dt:decision` is resolved ONLY by VB's recorded answer.** Never close one by your own judgment, convenience, or "moot." If you can't get VB's answer, `bd human <node>` (escalate, async) and leave it OPEN — never self-close.
- **Viability is NOT yours to call.** If research suggests the venture is undifferentiated / saturated / weak, that is NOT grounds to close decisions as moot or to kill the venture. It IS grounds to ADD a new `dt:decision` ("research shows N competitors + no clear differentiation — pivot / kill / proceed?") and pose it to VB. Kill, pivot, and viability are the **founder's** (VB's kill-gate) — never the griller's. **You grill; VB decides.**
- **`CONTEXT.md` is mandatory.** `domain-modeling` writes it as terms resolve. A grill that ends with no `CONTEXT.md` pinned no language — it is incomplete; re-open + re-run.
- **"Frontier empty" is necessary, not sufficient.** It is gameable (close-as-moot). The real gate is the three-part Completion above.

## Loop

```text
# 1. Seed the root + first nodes
bd create --title "dt: <venture>" --labels decision-tree,dt:root --description "<what's grilled + source brief id>"   # = <root>
for each top-level decision/fact the brief implies:
    bd create --title "dt:<fact|decision>: <...>" --labels decision-tree,dt:<fact|decision>
    bd dep <node> --blocks <root>

# 2. Walk the frontier while open dt:fact/dt:decision nodes exist (root excluded — it's the container)
while (bd list -l decision-tree | grep -qE 'dt:(fact|decision):' ); do
    pick a frontier bead (bd ready -l decision-tree; decisions can wait on the user-rep; facts resolve now):
      dt:fact     → resolve by LOOKUP (brief/codebase/research); bd comment <node> "<answer>"; bd close <node>
      dt:decision → POSE to the user-rep (VB) over the grill channel (intercom topic); WAIT for VB's reply;
                    bd comment <node> "VB: <verbatim answer>"; (domain-modeling pins any new term to CONTEXT.md + ADR if hard-to-reverse);
                    bd close <node>. NEVER self-close as "moot"/self-judge — see Hard rules (anti-fake-completion).
    FORK: if resolving surfaced new sub-decisions:
        bd create --labels decision-tree,dt:<fact|decision> ... ; bd dep <new> --blocks <root>
done

# 3. COMPLETE — no open dt:fact/dt:decision (root auto-ready). Close it; the resolved tree feeds to-spec.
bd close <root>; bd dep tree <root>
```

grilling's rule holds inside the loop: **facts are looked up, decisions are put to the
user-rep** — *"If a fact can be found, look it up rather than asking me. The decisions are
mine."* One decision/fact at a time (a firehose loses the tree structure).

## Anti-fake-confidence (the point)

Confidence is **not** a number the agent invents. It's the **graph state**: the tree is done
when the frontier is empty. An agent that "feels 0.95" with open beads is simply **not done**
— `bd ready -l decision-tree` proves it. Each pass must close real beads (recorded answer +
ADR where due) to advance; no closed beads = no progress = no confidence. This is the
beads-graph equivalent of dev↔verify's `metric_type=ground_truth`.

## Bounded + escalating

- **Depth/width caps** (default depth 4, width 12 per node): a fork beyond the cap → stop
  forking, note the residual on the parent, close it with an `[open: ...]` comment.
- **Unresolvable node** (user-rep unsure / fact unknowable) → `bd human <node>` (escalate,
  async) + leave it OPEN; it stays in the frontier as a **visible** gap, never a hidden one.
  The root can't complete until a human clears it — the tree makes the stall observable, not
  silently faked.

## Why beads, not kanban

The decision tree is a **planning artifact**, not execution work. Keeping it in bd (Dolt)
means: no kanban cards spawned → no dispatcher claims, no worker contention, no interference
with the live execution board. Label nodes `decision-tree` (NOT `ready-for-agent`) so the
beads-watchdog leaves them alone. The grilling agent queries/walks the graph directly via `bd`.

## Output

The resolved tree (`bd dep tree <root>`) + the glossary (`CONTEXT.md`) + ADRs produced along
the way ARE the pinned shared understanding. Hand them to `to-spec` — which synthesises the
spec from the conversation WITHOUT re-interviewing, because every decision is already
resolved + recorded on its bead.
