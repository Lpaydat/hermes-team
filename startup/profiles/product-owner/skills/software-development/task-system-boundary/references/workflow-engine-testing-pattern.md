# Workflow Engine Testing Pattern — FakeWorld

The technique for testing the workflow engine (or any board-dependent component)
without real dispatchers, real gateways, or real beads. Proven on the v1 engine:
30 integration tests (15 happy paths + 15 edge cases/unhappy paths), all passing.

## Why fake tests, not e2e livetests

The user's correction (exact quote): *"we need to better plan. let test with
smaller scale first"* and *"write tests that fake every parts of workflow to see
how this engine work. or you may fake even workflow."*

Livetests are for proving the FULL pipeline works end-to-end. They're slow
(hours), expensive (many agent dispatches), and non-deterministic (agent behavior
varies). For new engine components, start with fake integration tests that run
in milliseconds and are fully deterministic. Graduate to livetests only after
the fake tests prove the engine mechanics are correct.

## The FakeWorld fixture

A test context that provides everything the engine needs without touching real
infrastructure:

```python
class FakeWorld:
    """Test fixture: temp dir, fake board, engine, state DB."""

    def __init__(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="wf-test-"))

        # 1. Fake kanban board (real SQLite, minimal schema)
        self.board = make_fake_board(self.tmpdir, "test-board")
        self.board_db = self.tmpdir / "boards" / "test-board" / "kanban.db"

        # 2. Fake templates dir
        self.templates_dir = self.tmpdir / "templates"

        # 3. Monkey-patch KANBAN_HOME so kanban_adapter uses our fake board
        import workflow_engine.kanban_adapter as ka
        self._orig_home = ka.KANBAN_HOME
        ka.KANBAN_HOME = self.tmpdir / "boards"

        # 4. Engine with temp state DB
        self.engine = Engine(self.templates_dir)
        self.engine.state = StateDB(self.tmpdir / "state.db")

        # 5. Monkey-patch create_card to write directly to SQLite
        #    (bypasses `hermes kanban create` CLI subprocess)
        import workflow_engine.runtime as rt
        self._orig_create = rt.create_card
        rt.create_card = self._fake_create_card
```

## Key techniques

### 1. Fake kanban schema

Create a minimal SQLite DB with the tables the engine reads: `tasks`,
`task_runs`, `task_events`, `task_links`. Don't need the full Hermes schema —
just what the engine queries.

### 2. Monkey-patch KANBAN_HOME

The engine's `_boards_to_check()` reads from `kanban_adapter.KANBAN_HOME`.
Monkey-patch it at module level so the engine discovers your fake board. Note:
must read the module attribute at call time (not import time) for the patch to
take effect — see the `_boards_to_check` implementation.

### 3. Monkey-patch create_card

The engine calls `create_card()` which normally runs `hermes kanban create` as
a subprocess. Replace it with a direct SQLite INSERT. This avoids needing the
hermes CLI and makes card creation instant + deterministic.

### 4. Simulate card completions

To test the engine's completion detection, insert a completed `task_run` row
and set the card's status to `done`:

```python
def complete_fake_card(board_db, card_id, metadata=None, summary=""):
    conn = sqlite3.connect(str(board_db))
    conn.execute("UPDATE tasks SET status = 'done', completed_at = ? WHERE id = ?",
                 (int(time.time()), card_id))
    conn.execute("INSERT INTO task_runs (task_id, outcome, summary, metadata) "
                 "VALUES (?, 'completed', ?, ?)",
                 (card_id, summary, json.dumps(metadata) if metadata else None))
    conn.commit()
    conn.close()
```

### 5. Card ID collisions

When multiple cards are created in the same millisecond (common in tests), use
a counter suffix: `f"t_{int(time.time()*1000)}_{counter}"`. Without this, the
INSERT OR REPLACE silently overwrites the first card.

### 6. Instance ID collisions

When `start_manual()` is called twice in the same second, both instances get
the same `instance_id`. Fix: append a UUID suffix:
`f"wf_{int(time.time())}_{workflow_id}_{uuid.uuid4().hex[:8]}"`.

## Test categories (proven set — 30 tests)

### Happy paths (15)

| Category | What it tests | Example test |
|----------|--------------|--------------|
| Empty state | Engine doesn't crash with no work | `test_empty_tick` |
| Dispatch | Manual start → tick creates card | `test_manual_start_dispatches_node` |
| Advance | Card done → next node dispatches | `test_node_completion_advances` |
| Full lifecycle | A→B→C completes end-to-end | `test_full_lifecycle` |
| Variables | Output from A flows to B's template | `test_variable_resolution` |
| Idempotency | Tick twice = 1 card, not 2 | `test_idempotency` |
| Conditions | PASS path dispatches, FAIL doesn't | `test_conditional_node` |
| Triggers | Card completion auto-starts workflow | `test_trigger_detection` |
| Trigger guard | Non-matching card doesn't trigger | `test_trigger_no_match` |
| Keys | Card carries `wf:<instance>:<node>` key | `test_idempotency_key_on_card` |
| Parallel | Two nodes with same dep dispatch together | `test_parallel_dispatch` |
| Blocked | Blocked card reported, not advanced | `test_blocked_node_reported` |
| Restart | New engine resumes mid-workflow | `test_restart_recovery` |
| Multi-instance | Two instances on same board don't collide | `test_multiple_instances` |
| Diamond | A→(B,C)→D, D waits for both | `test_branching_workflow` |

### Edge cases & unhappy paths (15)

| Category | What it tests | Example test |
|----------|--------------|--------------|
| Circular deps | Two nodes depending on each other don't hang | `test_circular_dependency` |
| Missing template | Starting unknown workflow raises ValueError | `test_nonexistent_template` |
| Empty workflow | Zero nodes doesn't crash or falsely complete | `test_empty_workflow` |
| Trigger dedup | Same card doesn't trigger twice (watermark) | `test_trigger_dedup` |
| Multi-completion | Two parallel nodes done in one tick → fan-in dispatches | `test_multiple_completions_one_tick` |
| Malformed metadata | Invalid JSON in metadata doesn't crash engine | `test_malformed_metadata` |
| No metadata | Card completed with null metadata still advances | `test_no_metadata` |
| Schema validation | Invalid output doesn't block (soft validation) | `test_output_schema_validation` |
| Dead branch | Condition never passes → workflow stays active | `test_dead_branch` |
| Long chain | 5 sequential nodes complete end-to-end | `test_long_chain` |
| Unknown status | Card in weird status ignored, not done/blocked | `test_unknown_card_status` |
| Title prefix filter | Trigger respects `title_prefix` to skip probes | `test_trigger_with_title_prefix` |
| Missing upstream output | Template var resolves to empty, doesn't block | `test_missing_upstream_output` |
| Multiple triggers | Two different triggers fire on different cards | `test_multiple_triggers_same_board` |
| Board not found | Operations on nonexistent board return None/[] | `test_board_not_found` |

## The tick-ordering fix (critical bug)

The engine's `_check_instance()` MUST check completed nodes BEFORE checking
pending nodes in the same tick. Otherwise:

1. Tick detects card A is done, marks it DONE in state
2. But pending node B checks deps → A is still DISPATCHED (state not updated yet)
3. B doesn't dispatch this tick — waits for next tick
4. One tick of latency per hop in the pipeline

Fix: two-phase tick:
- **Phase 1**: Scan dispatched nodes for completion, update state + in-memory instance
- **Phase 2**: Scan pending nodes for dispatch (deps may have just completed in phase 1)

Also: update the in-memory `NodeState` object directly (not just the DB) so
phase 2 sees the updated status without reloading from DB.
