# The Exploration Gap — R&D Between Spec and Architecture

## The structural gap

The pipeline documented in `pipeline-diagrams.md` goes:

```
grill (validates the problem) → spec → architect (designs ONE approach) → to-tickets
```

Nobody asks: **"of the fundamentally different ways to approach this problem, which is the right one?"**

- The **grill** stress-tests the *problem* — "are we solving the right thing for the right user?"
- The **architect** optimizes the *implementation* — "how do we build this?"

Between them, the *approach* is never explored. The architect's `design-council` already fans out research and weighs alternatives — but **within one approach space**, not **across** approaches. Given "build a POS with offline sync," it researches "what's the best sync architecture?" It does NOT research "should this be sync vs. local-first CRDT vs. server-authoritative thin client?" — those produce different specs, different products.

The architect cannot question the spec it was handed. Its job is to design within it.

## Where R&D belongs

Between the PO's spec and the architect card:

```
grill → spec → [EXPLORATION GATE] → architect → to-tickets
```

PO-owned, like the grill. Exploration may change the spec itself (kill the idea, pivot direction, merge with an existing tool) — that's a product decision, which is the PO's domain.

### Trigger: novelty/risk/approach-uncertainty, NOT every feature

- The problem can be solved by **fundamentally different approaches**
- The **riskiest assumption** is unvalidated
- The **landscape is unknown** (what exists, prior art, competitor patterns)
- User said "I think I want X but I'm not sure" or "how do others solve this?"

Skip for low-stakes, well-understood features (CRUD forms). Matches the user's documented hatred of unnecessary complexity.

## Profile vs. skill — skill wins

The capability **already exists but is disconnected**:

| Need | Exists in | Gap |
|------|-----------|-----|
| Fast landscape scan | `scout` | Only scans AI frontier, not product landscape |
| Deep research, prior art | `researcher` | Writes to vault only; not wired into product pipeline |
| Spike prototypes | `builder` | Promotes full prototype; no lightweight "spike to learn" mode |
| Approach comparison | architect's `design-council` | Tactical only — converges within one approach |

A new profile would duplicate all four. The missing piece is an **orchestration step that connects them into a phase** — a skill's job, not a profile's. The PO already owns the pre-architecture flow and already creates the architect card, so it's the natural orchestrator. A separate profile adds dispatch-path/identity/SOUL overhead for no gain.

## What R&D produces — the exploration dossier

Save to `~/projects/<slug>/.driver/exploration/dossier.md` (matches grill-decisions convention):

1. **Landscape map** — what exists: tools, libraries, competitors, prior art. With citations.
2. **Approach tree** (the core artifact) — 2-4 fundamentally different approaches. For each: how it works, what it optimizes for/against, evidence it works, key risks, rough build cost.
3. **Spike results** (if warranted) — what a builder spike validated, what surprised us. Throwaway, not production.
4. **Recommendation** — which approach, why, biggest remaining risk for the architect to design around. Not a lock — architect and human can override.
5. **Decision gate** (if approaches imply different *product directions*) — surface to human. That's a WHAT decision, above the architect and the PO.

The dossier is to the architect what grill decisions are to `project-kickoff-spec`: a gate input the next phase reads before proceeding.

## How it feeds the architect

The architect's design card (from `architect-gate` Step 1) gains two inputs:
- The exploration dossier
- The recommended approach + documented alternatives

The architect then designs the HOW for the recommended approach (existing job), with the approach-space pre-mapped so `design-council` converges faster. The architect can still flag "approach B is structurally better" — but now that's an informed trade-off against a documented alternative, not a blind optimization.

## Industry parallel

Both YC and venture builders (Idealab, Science, Betaworks) explicitly separate **"should we build this, and which direction?"** (exploration/validation) from **"how do we engineer it?"** (architecture) from **"build it."**

- YC: talk to users = grill. MVP = spike prototype. Pivot/iterate on *direction* before committing to *build*. Current pipeline commits to build after spec with no direction loop.
- Venture builders: explicit validation phase with its own deliverable (thesis dossier = exploration dossier). Ideation → validation → prototyping → commit → scale. Commit happens *after* validation, not before.

The current Hermes pipeline separates design from build (architect → tech-lead) but does NOT separate exploration from design. R&D fills that missing separation.

## Proposed: `exploration-gate` skill (not yet approved — recommendation only)

If approved, a new PO skill `software-development/exploration-gate/` would:
1. Read spec + grill decisions
2. Decide: needs exploration? If no → skip to `architect-gate`. If yes → continue.
3. Decompose into research questions + spike candidates
4. Fan out via `kanban_chains`: researcher (deep dives), scout (breadth), builder (spikes)
5. Park until fan-out completes
6. On promotion: synthesize the dossier
7. Surface decision gate to human if needed
8. Hand off to `architect-gate` (with dossier included)

Routing update in this file's parent SKILL.md:
```
Current:  grill → spec → architect → to-tickets
Proposed: grill → spec → [exploration-gate] → architect → to-tickets
```

No new profile, no new dispatch path, no workflow-engine changes. Conditional (skipped for low-stakes features). Matches the complexity posture.
