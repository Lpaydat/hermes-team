# Workflow Engine — Read/Write Contract with Beads and Kanban

The core principle is **beads is the spec, kanban is the engine**, and the
workflow engine is an **asymmetric bridge** between them. The full boundary spec
lives in the project repo (`docs/adr/workflow-engine-beads-kanban-boundary.md`);
this file is the condensed reference an agent consults when designing or
debugging the engine.

## The asymmetric access model

| Store | Engine privilege | Allowed commands | Forbidden commands |
|---|---|---|---|
| **Beads** (`bd`/Dolt) | **read for triggers, write status only** | `bd list`, `bd ready`, `bd show`, `bd update <id> -s <status>` | `bd create`, `bd close` (of definition), `bd dep add`, `bd tag`, `bd update --title/--type/--description` |
| **Kanban** (SQLite) | **full read/write** | create, read, mutate, escalate cards freely | (none — this is the engine's home turf) |

**Why asymmetric:** beads survives disk loss (git-remote + Dolt sync) and is the
recoverable canonical truth. The board must always be reconstructable from beads,
so the durable facts live there and the engine only mirrors execution status
back. The engine never authors scope — authorship is a profile/human privilege. A
crash mid-`bd create` could duplicate or drop master-plan items; a crash mid-`-s`
is a recoverable no-op.

**Proven test for "should the engine write this to beads?":** *Would a human want
this in the backlog a month from now?* Yes → it's a bead, but **the engine doesn't
author it** — a profile or human does; the engine only mutates its status. No →
it's a card; the engine owns it entirely.

## Engine reads beads for triggers (3 trigger families)

1. **Ready-trigger (`bd ready`) → dispatch.** `bd ready` returns beads whose
   `bd dep` dependencies are resolved — so the engine dispatches **in dependency
   order automatically**, with no cross-store dependency tracking. Routing keys
   off type + labels:
   - `issue_type == "bug"` OR `task` + a `bug` label → **debug-loop workflow**
     (card to `debugger`, skips PO→tech-lead).
   - label `wayfinder:research` → scout · `wayfinder:task` → ops ·
     `wayfinder:architecture` → architect.
   - everything else → **dev workflow** (PO dispatch card → tech-lead).
   - **Skipped labels (never headless-dispatched):** `wayfinder:grilling`,
     `wayfinder:prototype`, `wayfinder:map`, `venture:brief` (HITL-substitute
     work owned by PO↔builder), and `gt:slot` (merge slots are containers).
2. **Human-flag-trigger (`bd list --label human`) → escalation.** A bead tagged
   `human` becomes a HQ ping card on `hermes-hq`. Idempotent per bead.
3. **Implicit structure-trigger (bead parent/epic).** `bd show <id>` resolves
   `parent` to populate card bodies (e.g. wayfinder map ID). The engine doesn't
   traverse dependencies — it relies on `bd ready` for ordering.

## Engine writes to beads — status only

The engine performs exactly **one class of bead write: status mutation**
(`bd update <id> -s <status>`). It does NOT let profiles handle bead closure —
profiles complete the card, and bead-sync closes the bead. This centralizes
closure in one idempotent place and avoids the double-close race and the fragile
agent-creates-card anti-pattern (proven across 16 livetest gaps).

## Status sync contract — unidirectional: kanban → beads

| Kanban card status | Bead status |
|---|---|
| `ready` | `in_progress` |
| `running` | `in_progress` |
| `blocked` | `blocked` |
| `done` | `closed` |
| `archived` | `open` (reopened — card discarded, work not done) |

- **Direction is one way.** Reverse sync (bead → kanban) does NOT happen via
  sync — it happens via the dispatch trigger (a bead becoming ready creates a new
  card). Bidirectional sync would let manual backlog edits spawn agents.
- **The join is `idempotency_key = "bead-<bead-id>"`.** This is the sole durable
  cross-store link — it's what makes the board reconstructable from beads.
- **Closed beads are terminal** (re-syncing is a no-op). **`gt:slot` skipped**
  (containers, not dispatchable).

## How workflow JSON templates reference beads (3 ways)

1. **By ID — the execution join.** Every card the engine creates for a bead
   carries `idempotency_key: "bead-{bead.id}"`. Lose it and the card is orphaned.
2. **By type/label — the routing branch.** The type+label fallback is
   **mandatory** — `issue_type` alone is unreliable (`bd create --type=bug` may
   store `issue_type=task`). Branch must check both.
3. **By dependency — implicit via `bd ready`.** Templates do NOT encode cross-bead
   dependencies; `bd dep` enforces ordering. The engine must never replicate bead
   dependencies in kanban `task_links` — double-tracks ordering and drifts.

## Boundary violations (anti-patterns)

- Engine calling `bd create` / `bd dep add` / `bd tag` — authorship is a
  profile/human act.
- Engine calling `bd close <id>` (definition close) — use `bd update -s closed`.
- Replicating bead deps in kanban links for bead-level ordering — use `bd ready`.
- Bidirectional status sync — lets manual edits spawn agents.
- Promoting dev/verifier cards to beads — backlog explosion + sync noise.
- Bugs filed as cards — defects outlive the card that surfaced them.
- Relying on agents to `bd close` after card completion — closure is
  infrastructure's job (bead-sync), not the agent's.

## Future unification

The engine exists only because beads and kanban lack event hooks into each other.
The contract above survives the rebuild; only the polling cron dies. When the
team's harness provides native lifecycle hooks (`bd post-ready`, `kanban
on-complete`, card-completion events), the 5-phase bridge disappears into native
hooks. The `ngin` dispatcher platform is ~90% of this (see
`ngin-dispatcher-platform.md`).
