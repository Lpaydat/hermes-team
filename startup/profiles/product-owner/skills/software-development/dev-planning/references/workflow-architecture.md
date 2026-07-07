# Workflow Architecture — the Full Pipeline

## The Two-Layer Model

```
PLANNING (PO)                    EXECUTION (cron + agents)
─────────────                    ─────────────────────────
User/Agent chats with PO
  → discuss → PRD → beads + deps
  → close PRD bead
  → DONE
                                    Workflow engine cron (1m)
                                      → Phase 1: bead-sync (card status → bead status)
                                      → Phase 2: auto-dispatch
                                          → check bd ready
                                          → if new beads: create ONE PO dispatch card
                                          → if no new beads: skip
                                      → Phase 3: board-scanner (escalate blocked tasks)

PO receives dispatch card
  → dev-dispatch skill fires
  → creates tech-lead cards for ALL ready beads
  → completes own card

Tech-lead receives card
  → kanban_delegate tool (creates dev + verifier cards, blocks self)
  → developer builds code
  → verifier adversarial review
  → PASS → merge to main → bd close
  → FAIL → fix card → re-verify
  → tech-lead auto-promoted → kanban_complete
```

## Key Design Decisions

### PO is the dispatch bridge — not the cron
The workflow engine cron does NOT create tech-lead cards directly. It creates a PO dispatch card. PO works it via `dev-dispatch` and creates the tech-lead cards. This lets PO review, prioritize, or skip before dispatching.

### kanban_delegate — not manual card creation
Tech-lead uses the `kanban_delegate` plugin tool (not `kanban_create`) to create dev + verifier cards. The tool atomically: creates dev card, creates verifier card (parented on dev), links tech-lead as child of verifier, blocks tech-lead with kind=dependency. Tech-lead auto-promotes when verifier completes.

### Bead-sync timing
bead-sync closes beads when the tech-lead root card hits `done`. This is correct because `kanban_delegate` makes tech-lead block on the verifier — tech-lead only completes AFTER the verifier finishes. The `todo` status (dependency block) is not in STATUS_MAP, so the bead stays `in_progress` during the wait.

### Board scanner escalation chain
Any blocked task → escalate to one-level-up profile:
- developer/verifier blocked → tech-lead
- tech-lead blocked → product-owner
- product-owner blocked → human (HUMAN_REQUIRED comment)

Agent inspects, comments resolution, completes with "RESOLVED:". Scanner unblocks original task via CLI (bypasses tool API ownership check).

## Kanban Idempotency-Key Dedup

The `hermes kanban list --json` API does NOT expose the `idempotency_key` field. To check if a card already exists for a bead, query SQLite directly:

```sql
SELECT 1 FROM tasks WHERE idempotency_key = 'bead-<bead-id>' AND status != 'archived' LIMIT 1;
```

The `--idempotency-key` flag on `kanban create` deduplicates at the DB level — a second create with the same key returns the existing card. But archived cards are excluded from dedup, so the check must use `status != 'archived'`.

## Cron Hygiene

- All cron scripts that scan projects MUST read `active-projects.json` first. Empty list → skip (zero tokens).
- Use `deliver=local` for all dev-workflow crons. No Discord delivery.
- Combined 3 crons (auto-dispatch + bead-sync + board-scanner) into `workflow-engine.py` (1m) for execution ordering.
- Session archiver runs on ops (6h) — archives kanban worker sessions >3 days old via official `SessionDB.set_session_archived()` API.
