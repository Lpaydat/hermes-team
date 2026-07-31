# Workflow Engine Phases

The workflow engine (`workflow-engine.py`) runs every minute on the PO profile's cron. It reads `active-projects.json` and runs phases per project board.

> **Phase count caveat:** the code defines 5 phases, but Phase 4 (qa-trigger) is currently commented out in `main()` (see SKILL.md current-state warning). The replacement cron job is erroring. So in practice only Phases 1, 2, 2b, and 3 execute.

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

Scans for human-flagged beads (`bd label add <id> human`). Creates an operator HQ card on `hermes-hq` board. Idempotent per bead.

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

## Phase 4: qa-trigger — ⚠ CURRENTLY DISABLED

> **Status (2026-07-31): commented out in `main()`.** The call block is wrapped in a comment: `# QA trigger disabled — now handled by new workflow engine`. The replacement cron job (`94e735a11be6`, "New Workflow Engine") is **erroring every tick** ("Script not found"). QA re-test cards are NOT being created automatically. See SKILL.md for the full current-state warning.

### How it works when enabled (the hybrid git-diff approach)

Two-signal AND gate — both must be true to trigger:

1. **Git signal:** `git rev-parse HEAD` changed since the last run for this board (state in `qa-trigger-state.json`), AND `git diff --name-only <last>..<current>` shows at least one code file (extensions: `.py .js .ts .rs .go .java .rb .sh .sql .yaml .yml .toml`). Doc-only commits are filtered out.
2. **Card signal:** a verifier or debugger card completed in the last 1 hour (excluding `[probe]` and `verify t_` cards).

- Dedup via idempotency key `qa-merge-<sha>`.
- Creates `[qa] Re-test after merge: <sha>` card assigned to `qa`.

### Design history — why the abandoned regex approach was abandoned

The trigger went through 7 iterations. The **first six approaches all failed**:

| Approach | Why it failed |
|----------|---------------|
| Git `rev-list --merges` | False positives on PO spec/doc commits |
| Parent-child link check | Loop_engine creates complex hierarchies that don't follow simple parent-assignee patterns |
| `"merged"` keyword | False positives ("re-open against merged master") |
| Regex on summaries (`merged to master` / `^merged ` / etc.) | **Fragile — agents don't write predictable text.** Verifiers write "PASS" not "merged to master". Zero reliability. |
| **Final working approach** | **Structural signals:** git diff (language-independent code-file detection) + verifier/debugger card completion confirms it was a code merge, not a manual push. |

**The lesson (durable):** Never depend on what an agent wrote in its summary for pipeline triggers. Use structural signals (git diff, card assignee + completion status) instead of natural-language text matching. Agents are unreliable writers of trigger phrases.

### Edge cases (when enabled)

- **1-hour lookback window**: if engine is down >1h, QA trigger misses completed cards permanently. Trade-off: prevents historical flood on first run.
- **First run per board**: seeds `qa-trigger-state.json` with current SHA without creating a card (avoids firing on stale history).
- **`completed_at` type**: the SQL comparison assumes epoch integer. If kanban changes to datetime strings, the `>` comparison breaks silently.
