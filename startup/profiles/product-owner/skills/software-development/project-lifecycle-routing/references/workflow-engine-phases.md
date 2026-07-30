# Workflow Engine Phases

The workflow engine (`workflow-engine.py`) runs every minute on the PO profile's cron. It reads `active-projects.json` and runs 5 phases per project board.

## Phase 1: bead-sync

Syncs kanban card status → bd bead status. When a kanban card reaches `done`, the corresponding bead is closed via `bd update <id> -s closed`.

- Matches cards to beads via `idempotency_key = bead-<bead-id>`
- Status map: ready/running → in_progress, blocked → blocked, done → closed, archived → open
- Skips already-closed beads and merge slots (`gt:slot` label)

## Phase 2: dispatch

Checks `bd ready` for dispatchable beads. Routes by type:

- **Merge slots** (`gt:slot`): skipped
- **Epics**: skipped (containers, not work)
- **Wayfinder tickets**: routed by label to scout/ops/architect
- **Bugs** (`issue_type == 'bug'` OR `issue_type == 'task'` with `'bug'` in labels): routed directly to debugger via `dispatch_bug_to_debugger()`
- **Everything else**: collected into a PO dispatch card ("[dispatch] N ready bead(s)")

PO dispatch cards are deduped: if one is already active, no new one is created.

## Phase 2b: human-escalation

Scans for human-flagged beads (`bd tag <id> human`). Creates an operator HQ card on `hermes-hq` board. Idempotent per bead.

## Phase 3: scanner

Detects blocked tasks and escalates via ESCALATION_CHAIN:

```
developer → tech-lead
verifier → tech-lead
debugger → tech-lead
qa → tech-lead
tech-lead → product-owner
product-owner → HUMAN_REQUIRED
```

Checks if escalation was resolved (card with "RESOLVED:" summary), unblocks if so. Skips tasks with HUMAN_REQUIRED comments.

## Phase 4: qa-trigger

Scans for recently-completed verifier/debugger cards (last 1 hour) and creates QA re-test cards automatically.

### Filter chain (order matters):

1. **Idempotency**: `qa-after-<source-card-id>` key exists → skip
2. **Probe/sub-review**: title starts with `[probe]` or `verify t_` → skip
3. **Merge detection (regex)**: summary must contain one of:
   - `merged to master`
   - `merged to main`
   - `. merged ` (sentence-start "merged")
   - `^merged ` (summary-start "merged")
4. If all pass → create QA card with source card's context

### Design history (why regex on summaries):

| Approach | Why it failed |
|----------|--------------|
| Git `rev-list --merges` | False positives on PO spec/doc commits |
| Parent-child link check | Loop_engine creates complex hierarchies that don't follow simple parent-assignee patterns |
| `"merged"` keyword | False positives ("re-open against merged master") |
| **Regex patterns** | **Zero false positives, validated against 18 historical cards** |

The lesson: **detect outcomes in natural language summaries, not structural relationships.** The verifier writing "merged to master" is ground truth.

### Edge cases:

- **1-hour lookback window**: if engine is down >1h, QA trigger misses completed cards permanently. Trade-off: prevents historical flood on first run.
- **`completed_at` type**: assumes epoch integer. If kanban changes to datetime strings, the `>` comparison breaks silently.
- **Natural language fragility**: if verifier writes "merged into master" or "fast-forwarded to main", trigger misses. Acceptable — the verifier's SOUL.md stamps "merged to master" as its merge phrase.
