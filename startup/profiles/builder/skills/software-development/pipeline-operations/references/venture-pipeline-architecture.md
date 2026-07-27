# Venture Pipeline Architecture

The venture pipeline has 4 independent stages. Stages 1 and 2 are automated (cron + script). Stages 3 and 4 are builder sessions dispatched as kanban cards.

## Stage 1 — Discovery (cron, no human)

Daily scan across 4 doors:
- **Door A — Problem:** Pain-driven. Communities complaining, frustration, unmet needs.
- **Door B — Opportunity:** Shift-driven. New API, tech crossing a threshold, regulatory shift.
- **Door C — Copycat:** Success-driven. Product making money but broken/sloppy/missing something.
- **Door D — User:** Founder submits to `~/vault/ventures/user-ideas.md`. PRIORITY — always included, go first, regardless of score.

Output: raw signals → score /25 → full dossier → fact-verify. Verified dossiers land in `~/vault/ventures/idea-bank.md`.

The pipeline does NOT grill or build — those are separate builder sessions (Stage 3).

## Stage 2 — Queue (cron script, no AI)

`queue-builds.sh` reads idea-bank.md, sorts by score, picks top 10, creates **2 kanban cards per idea** (Grill + Build) on `hermes-hq` board.

```
idea1-Grill → idea1-Build   ↘
idea2-Grill → idea2-Build   → all run concurrently (capped by max_in_progress_per_profile=3)
idea3-Grill → idea3-Build   ↗
```

Each idea is an INDEPENDENT grill→build pair. No cross-idea chaining.

## Stage 3 — Builder sessions (kanban cards, separate context per card)

### Card A: "Grill: <idea>" (no parent, dispatched first)

- Reads dossier → runs `self-grill` (launches real PO via RPC, answers as founder) → validates → completes
- Loads: `self-grill` + `grill-rpc-ops`
- Output: `~/projects/<slug>/context/*.md` (per-branch grill decisions)
- Does NOT build the prototype — that is the next card

### Card B: "Build: <idea>" (child of Card A via `--parent`)

- Auto-promotes to ready only when Card A completes (kanban-enforced gate)
- Reads context → builds with `venture-prototype` + loop_engine → README → review handoff
- Loads: `venture-prototype`
- Output: `~/projects/<slug>/prototype/` + `~/projects/<slug>/README.md` + portfolio entry
- Does NOT re-grill

### Why 2 cards instead of 1

The 1-card design buried loop_engine as step 2 of 4 in a multi-hour session. The builder self-assessed builds as "simple enough" to skip loop_engine on 15/15 prototypes across 2 batches. The 2-card split gives the builder a fresh context where loop_engine is the ONLY job.

## Stage 4 — Interactive review (user-driven)

User reviews prototypes → opens chat with builder → gives feedback. Three outcomes:
- "Fix X" → builder iterates
- "Promote this" → builder runs `project-promotion` skill → dispatches to PO
- "Shelve" → done

## Project structure (on promotion)

```
~/projects/<slug>/
├── .context/              ← dossier, grill decisions, verification
├── prototype/             ← builder's working demo
├── src/                   ← production code (PO controls, tech-lead/developer writes)
├── tests/
├── STATUS.md              ← project dashboard — PO owns
└── README.md
```

Self-contained. Only `.context/`, `STATUS.md`, and `README.md` are fixed; the rest adapts to the stack.
