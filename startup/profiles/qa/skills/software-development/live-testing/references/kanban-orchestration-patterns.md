# Hermes Kanban Orchestration Patterns

Platform-native patterns for multi-card QA workflows. Verified against platform source (`kanban_swarm.py`, `kanban.py`, `kanban_db.py`) on 2026-07-09.

## The `hermes kanban swarm` command

Creates a full parallel-worker → verifier → synthesizer topology in one atomic call:

```bash
hermes kanban swarm \
  "Goal: <final outcome>" \
  --worker PROFILE:TITLE[:SKILL,SKILL] \
  --worker PROFILE:TITLE[:SKILL,SKILL] \
  --verifier PROFILE \
  --synthesizer PROFILE \
  --created-by PROFILE \
  --json
```

### What it creates

```
Root card (completed immediately, acts as shared blackboard)
  ├── Worker 1 (ready, parallel, skills loaded)
  ├── Worker 2 (ready, parallel, skills loaded)
  ├── Worker N (ready, parallel, skills loaded)
  ├── Verifier (todo — parents=all workers, gates the synthesizer)
  └── Synthesizer (todo — parent=verifier, produces final output)
```

- The root card is completed immediately so workers can start
- Workers are `ready` immediately (parent is done)
- Verifier waits for ALL workers (parents=worker_ids)
- Synthesizer waits for verifier (parent=verifier_id)
- Each worker can have specific skills loaded via `[:skill,skill]`
- Idempotency: if the root card already exists (same idempotency key), the swarm is not duplicated

### The blackboard pattern

Workers and the synthesizer communicate via structured JSON comments on the root card:

```python
# Post a structured update (from execute_code or terminal):
# The comment body is: "[swarm:blackboard] " + JSON
# post_blackboard_update(conn, root_id, author="qa-functional", key="verdicts", value={
#     "claim_1": "proven",
#     "claim_2": "disproven",
#     "evidence_claim_2": "curl -v output..."
# })

# Read all structured updates:
# latest_blackboard(conn, root_id) → merged dict (later values replace earlier for same key)
```

The blackboard IS the shared state mechanism. Workers don't need to see each other's full context — just the structured facts on the root card. The synthesizer reads all blackboard updates to produce the final output.

## The `kanban_delegate` myth

The tech-lead's `loops-engineering` skill references `kanban_delegate` as if it's a real tool. **It is not.** It does not exist in:
- The CLI (`hermes kanban --help` — no `delegate` subcommand)
- The source code (`grep -rn 'kanban_delegate' hermes_cli/` — zero results)
- The kanban module (`kanban.py` — no delegate function)

It is a **convention name** in the skill for the three-step pattern:
1. `kanban_create(assignee=..., parents=[self], body=..., skills=[...])` — create child card
2. `kanban_link(parent_id=self, child_id=child)` — if not using `parents=` on create
3. `kanban_block(reason="dependency: ...")` — block yourself; dispatcher auto-promotes children

Do not write `kanban_delegate(...)` in a skill and expect it to work. Use the real `kanban_*` tools.

## The `max_in_progress_per_profile` constraint

The global dispatcher setting `max_in_progress_per_profile` (in the ROOT `~/.hermes/config.yaml`, NOT per-profile config) caps each profile to N concurrent tasks. Default: 1.

**Impact on fan-out:** If you create 4 child cards all `assignee=qa`, and `max_in_progress_per_profile: 1`, the dispatcher picks up ONE at a time. The other 3 sit in `ready` until the first completes. This is serial execution, not parallel.

**To get true parallelism:**
1. Raise `max_in_progress_per_profile` in ROOT `~/.hermes/config.yaml` (e.g., to 4)
2. Restart the gateway (caps load at boot)
3. Verify: `hermes kanban list --status running` should show multiple `qa` tasks

**Or accept serial execution** — it's still durable, crash-safe, and each worker gets a clean context window. Just slower.

## Kanban DB schema (relevant tables)

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `tasks` | The cards | id, title, body, assignee, status, workspace_kind, workspace_path, skills (JSON), model_override, block_kind |
| `task_links` | Parent→child dependencies | parent_id, child_id |
| `task_comments` | The Q&A/handoff thread | task_id, author, body, created_at |
| `task_attachments` | File storage (screenshots, reports) | task_id, filename, stored_path, content_type, size |
| `task_runs` | Per-execution records | task_id, status, outcome, summary, metadata (JSON) |

### Key columns for QA

- `tasks.skills` — JSON array of skill names force-loaded for the worker (e.g., `["qa-functional"]`)
- `tasks.model_override` — per-card model override (e.g., a different model for security testing)
- `task_runs.metadata` — JSON blob set by `kanban_complete(metadata={...})`, auto-injects into child card context
- `task_runs.summary` — human-readable completion summary, readable via `kanban_show`
- `task_attachments` — store screenshots and long evidence files here, not in ~/vault/

## Evidence flow through kanban (not ~/vault/)

| Evidence type | Mechanism | How to read it |
|---|---|---|
| Short (curl output, exit codes) | Inline in `kanban_complete(summary=...)` or finding card body | `kanban_show(card_id)` |
| Structured (per-claim verdicts) | `kanban_complete(metadata={...})` as JSON | `kanban_show(card_id)` — auto-injects into parent context |
| Cross-worker shared facts | Blackboard comments on root card (`post_blackboard_update`) | `latest_blackboard(conn, root_id)` |
| Visual (screenshots) | `task_attachments` on the finding card | Stored in kanban DB, visible via `kanban show` |
| Long (full logs, reports) | `/tmp/qa-evidence/<card-id>/` (ephemeral) | File system (lost on crash — keep structured summary in kanban) |

**Never write QA evidence to `~/vault/`** — that's the knowledge base (journal, wiki, ventures, traces). QA evidence is runtime data, not knowledge. The kanban DB is durable, card-scoped, and readable by any agent via `kanban_show`.

## How the tech-lead blocks and auto-resumes

The proven pattern (from `loops-engineering` SKILL.md):

1. Tech-lead creates child cards: `kanban_create(assignee="developer", parents=[tech_lead_card], ...)`
2. Tech-lead blocks itself: `kanban_block(reason="dependency: dev+verifier cards dispatched")`
3. Tech-lead's session **ends** (it does NOT poll or sleep)
4. Dispatcher picks up child cards (they're `ready` because parent blocked = "done" from child's perspective)
5. Children work and complete
6. When ALL children complete → parent auto-promotes from `blocked` to `ready`
7. Dispatcher re-dispatches the tech-lead with a fresh session
8. Tech-lead reads child completions via `kanban_show` and proceeds

**Key rules:**
- Do NOT poll. Do NOT sleep-loop calling `kanban_show`. The dispatcher handles promotion.
- The session ends on block. State is reconstructed from the board on re-dispatch.
- `kanban_show` returns child card completion metadata — that's the handoff mechanism.

## How the verifier creates fix cards (the re-test loop pattern)

On FAIL, the verifier:
1. Comments findings on the developer card with header `REVIEW-ITERATION: <N>` (the comment IS the iteration counter — cards have no mutable metadata field)
2. Creates a fix card: `kanban_create(assignee="developer", parents=[review_card], workspace_kind="dir", workspace_path=<original worktree>, body="Review-Iteration: <N+1>, Chain-Root: <id>, ...")`
3. Creates a fresh review card as the fix card's child
4. Completes its own review card with verdict=fail

The iteration count lives in comments + the chain of review cards. Escalation at iteration ≥ 3: verifier blocks its own card `needs_input` and creates a tech-lead escalation card.

QA should use the same pattern for findings: file as kanban card to `developer` with severity + evidence in body, block QA card on Critical findings, escalate after 3 failed fix attempts.
