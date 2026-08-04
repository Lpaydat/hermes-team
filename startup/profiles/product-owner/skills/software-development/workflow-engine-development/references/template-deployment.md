# Template Deployment + Kanban Board Schema (2026-08-02)

Lessons from deploying the dev-dispatch template to a live production board.

## Production template deployment

The engine cron (`wf-engine-tick.py`) reads templates from
`startup/scripts/workflow_engine/templates/`. This is the MAIN repo copy.
Deploying a template that exists only in a worktree is invisible to the
running cron. Deployment options:

1. **Copy the template file** to the production templates dir (fast, no merge
   needed). Safe for additive templates (new triggers/nodes). BUT requires
   the engine code on main to support any new features the template uses
   (e.g. if the template uses back-edges but main's engine doesn't have the
   loop rewrite, the template fails to load).
2. **Merge the branch** (requires user approval — NEVER do this without
   explicit sign-off).

## Kanban metadata lives in task_runs, NOT tasks

The `tasks` table has NO `metadata` column. Card metadata is stored in
`task_runs.metadata` (JSON). This is critical for:

- **Creating test cards with metadata via SQL:** INSERT into BOTH `tasks`
  AND `task_runs` — a card with no task_run has no metadata.
- **Trigger conditions on metadata.*:** The engine's
  `find_recent_completions` joins `tasks` (status='done', completed_at > X)
  with `task_runs.metadata`. A card completed without a task_run row has
  no metadata → `metadata.type` evaluates to None → routing defaults.

```sql
-- Correct: create card + task_run with metadata
INSERT INTO tasks (id, title, assignee, status, created_at, completed_at, body)
VALUES ('spec1', '[spec] Test', 'product-owner', 'done', ?, ?, 'body');

INSERT INTO task_runs (task_id, profile, status, started_at, ended_at, outcome, metadata)
VALUES ('spec1', 'product-owner', 'done', ?, ?, 'completed', '{"type": "bug"}');
```

## Live board test procedure

1. Create a board: `hermes kanban boards create <slug>`
2. Copy template to production templates dir
3. Create spec cards with metadata via SQL (see above)
4. Run engine tick: `python3 startup/scripts/workflow_engine/main.py tick`
5. Verify routing: check board for engine-created cards
6. Verify template resolution: check card bodies for `${trigger.*}` values
7. Clean up: `hermes kanban boards delete <slug>`

## Trigger context fields

When a `card_completed` trigger fires, `_start_from_trigger` builds the
context:

```python
trigger_context = {
    "card_id": trigger_card.id,
    "board": board,
    "assignee": trigger_card.assignee,
    "title": trigger_card.title or "",  # added 2026-08-02
    **metadata,  # spread: metadata.type → trigger.type
}
```

So `${trigger.title}` and `${trigger.type}` resolve in body templates.
Without `title` in context, `${trigger.title}` resolves to empty.

## Old cron vs new engine cron

Two crons coexist:
- `5838e048ae7f` — old `workflow-engine.py` (bead-sync + dispatch + scanner).
  PAUSED when migrating to the new engine. Can be re-enabled if needed.
- `94e735a11be6` — new `wf-engine-tick.py` (calls the stateless engine tick).
  ENABLED. This is the production engine.

The old cron's pause does NOT survive a `git reset --hard` if the cron DB
was modified by the cron system after the pause. Always verify the pause
state after any git operations on main.
