# Workflow Architecture

## The Pipeline

```
User/Agent chats with PO
  → dev-planning skill
  → discuss → PRD → review → beads → review → close PRD bead
  → DONE (PO walks away)

Workflow Engine cron (1min, zero-token)
  → Phase 1: bead-sync — sync card status → bead status
  → Phase 2: auto-dispatch — bd ready → create ONE PO dispatch card
  → Phase 3: board-scanner — blocked tasks → escalate to proper profile

PO receives dispatch card
  → dev-dispatch skill
  → checks bd ready → creates tech-lead cards for ALL ready beads
  → completes own card

Tech-lead receives card
  → kanban_delegate plugin → developer + verifier cards atomically
  → tech-lead blocks (dependency_wait)
  → developer builds via pi harness
  → verifier reviews (two-phase adversarial)
  → PASS → merge to main → bead closed
  → FAIL → fix card to developer → re-verify loop
  → tech-lead auto-promotes when all verifiers done
  → completes
```

## Board Model

One board per project. Board slug = project name. All profiles (PO, tech-lead, developer, verifier) work on ALL boards — n-to-n relationship. There is no "PO board" — every board is a project board.

- Each project gets its own kanban board: `hermes kanban boards create <slug>`
- The `team` board handles cross-project ops (infrastructure, audits, ops tasks)
- The `startup` board was killed — replaced by `team`
- The dispatcher injects `HERMES_KANBAN_BOARD` per task — workers auto-scoped
- The gateway dispatcher iterates ALL boards on disk every tick (60s default)
- Escalation cards stay on the same project board — no cross-board routing
- Board slug is immutable once created — choose it carefully at creation time

## active-projects.json

Maps projects to boards. Empty list = no scanning, zero tokens.

```json
{
  "active_projects": [
    {
      "name": "Project Name",
      "path": "/absolute/path/to/project",
      "board": "project-slug"
    }
  ]
}
```

The workflow engine reads this to know which projects to scan. ALL crons that iterate projects must respect this list.

## Key Design Decisions

### PO is the dispatch bridge — not the cron
The workflow engine cron does NOT create tech-lead cards directly. It creates a PO dispatch card. PO works it via `dev-dispatch` and creates the tech-lead cards. This lets PO review, prioritize, or skip before dispatching.

### kanban_delegate — not manual card creation
Tech-lead uses the `kanban_delegate` plugin tool (not `kanban_create`) to create dev + verifier cards. The tool atomically: creates dev card, creates verifier card (parented on dev), links tech-lead as child of verifier, blocks tech-lead with kind=dependency. Tech-lead auto-promotes when verifier completes.

### Board scanner escalation chain
Any blocked task → escalate to one-level-up profile on the SAME board:
- developer/verifier blocked → tech-lead
- tech-lead blocked → product-owner
- product-owner blocked → human (HUMAN_REQUIRED comment)

Agent inspects, comments resolution, completes with "RESOLVED:". Scanner unblocks original task via CLI (bypasses tool API ownership check).

## Kanban Ownership (source-code verified)

| Action | Tool API (agents) | CLI (cron/scripts) |
|--------|-------------------|---------------------|
| `kanban_complete` | Own task only (ownership enforced) | Any task |
| `kanban_block` | Own task only | Any task |
| `kanban_unblock` | Own task only | Any task |
| `kanban_comment` | Any task (explicitly allowed) | Any task |
| `kanban_create` | Any task | Any task |
| `kanban_link` | Any task | Any task |

The ownership check is `_enforce_worker_task_ownership` in `tools/kanban_tools.py:135`. It checks `HERMES_KANBAN_TASK` env var — if set (worker context), foreign task mutations are rejected. If not set (orchestrator/CLI context), all mutations are allowed.

## Kanban Idempotency-Key Dedup

The `hermes kanban list --json` API does NOT expose the `idempotency_key` field. To check if a card already exists for a bead, query SQLite directly:

```sql
SELECT 1 FROM tasks WHERE idempotency_key = 'bead-<bead-id>' AND status != 'archived' LIMIT 1;
```

The `--idempotency-key` flag on `kanban create` deduplicates at the DB level — a second create with the same key returns the existing card. But archived cards are excluded from dedup, so the check must use `status != 'archived'`.

## Session Archiving (official API)

Kanban worker sessions (first message: "work kanban task t_xxx") pollute the session list. Archive them using the official `SessionDB.set_session_archived()` API — NOT raw SQL.

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes-teams" / "startup" / "hermes-agent"))
from hermes_state import SessionDB

store = SessionDB(db_path)  # Pass Path object, not string
store.set_session_archived(session_id, True)  # Soft hide — still searchable
store.close()
```

## Cron Hygiene

- All cron scripts that scan projects MUST read `active-projects.json` first. Empty list → skip (zero tokens). Non-negotiable. The user has corrected this pattern 10+ times.
- Use `deliver=local` for all dev-workflow crons. No Discord delivery (was broken — 401).
- Combined 3 crons into `workflow-engine.py` (1m) for execution ordering.
- Session archiver runs on ops (6h) — archives kanban worker sessions >3 days old.
- Cron script paths: bare filename only (`script='workflow-engine.py'`), NOT `scripts/workflow-engine.py`.
- `fallback_model: []` on ALL profiles — no deepseek (no API key, silently fails).
- When the user says "do X" and you've been corrected on X before, just DO it — don't ask "should I do X?" That's corner-cutting.

## Component Map

| Component | Location | Purpose |
|-----------|----------|---------|
| `workflow-engine.py` | `product-owner/scripts/` | Combined cron: bead-sync + dispatch + scanner |
| `kanban_delegate` plugin | `tech-lead/plugins/dev_workflow/` | Creates dev+verifier cards, blocks tech-lead atomically |
| `session-archiver.py` | `ops/scripts/` | Archives kanban worker sessions >3 days |
| `hygiene-guard.sh` | `product-owner/scripts/` | Scans active projects for stale/orphan beads |

## Proven Components

- Core loop (TL→DEV→VER→merge): ✅ 22+ battle tests
- Parallel execution (3 concurrent): ✅ 5-case validation
- Merge conflict resolution: ✅ C6 3/3
- Tech-lead re-block on FAIL: ✅ C9 3/3 (via C6)
- `kanban_delegate` reliability: ✅ 5/5
- Board scanner v2: ✅ 7/7 test suite + production
- Multi-board parallel (2 boards simultaneously): ✅ startup-internal + multi-board-test, no cross-board leakage, Jul 2026
