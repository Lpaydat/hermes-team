# FakeWorld Testing Pattern for Workflow Engines

The FakeWorld pattern lets you test a workflow engine end-to-end without
touching real beads, real dispatchers, or real gateway processes. Every part
of the system is faked — the kanban board, the card creation, the card
completions — so tests run in milliseconds and are fully deterministic.

## The core idea

Instead of mocking individual functions, create a complete fake environment:

1. A temp directory with a fake kanban SQLite DB (real schema, empty data)
2. Monkey-patch `KANBAN_HOME` so all board operations go to the temp dir
3. Monkey-patch `create_card` so it writes directly to SQLite (no hermes CLI)
4. Simulate card completions by inserting rows with `status='done'`
5. Call `engine.tick()` to run the tick loop, assert on returned actions

This gives you real integration testing: the engine reads/writes real SQLite,
processes real JSON templates, and exercises the full tick cycle — but without
any external dependencies or async waiting.

## The FakeWorld fixture (skeleton)

```python
class FakeWorld:
    def __init__(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="wf-test-"))
        self.board = make_fake_board(self.tmpdir, "test-board")
        self.board_db = self.tmpdir / "boards" / "test-board" / "kanban.db"
        self.templates_dir = self.tmpdir / "templates"
        self.templates_dir.mkdir(parents=True)

        # Monkey-patch KANBAN_HOME
        import workflow_engine.kanban_adapter as ka
        self._orig_home = ka.KANBAN_HOME
        ka.KANBAN_HOME = self.tmpdir / "boards"

        # Create engine with temp state DB
        self.state_db_path = self.tmpdir / "state.db"
        self.engine = Engine(self.templates_dir)
        self.engine.state = StateDB(self.state_db_path)

        # Monkey-patch create_card
        import workflow_engine.runtime as rt
        self._orig_create = rt.create_card
        rt.create_card = self._fake_create_card
```

## Three critical monkey-patches

### 1. KANBAN_HOME (board path resolution)

The engine's kanban adapter resolves board paths via `KANBAN_HOME`. If you
don't patch this, the engine writes to the real `~/.hermes-teams/startup/kanban/boards/`.

```python
import workflow_engine.kanban_adapter as ka
ka.KANBAN_HOME = self.tmpdir / "boards"
```

**Gotcha:** some methods read `KANBAN_HOME` at import time as a module-level
constant. Patch the module attribute, and make sure runtime methods import it
dynamically (`from .kanban_adapter import KANBAN_HOME`) rather than caching it.

### 2. create_card (CLI bypass)

The engine calls `create_card()` which shells out to `hermes kanban create`.
In tests, write directly to the fake board DB:

```python
def _fake_create_card(self, board, title, assignee, body="",
                      idempotency_key=None, priority=None, workspace=None):
    db = self.tmpdir / "boards" / board / "kanban.db"

    # CRITICAL: use a counter to avoid timestamp collisions
    if not hasattr(self, '_card_counter'):
        self._card_counter = 0
    self._card_counter += 1
    card_id = f"t_{int(time.time()*1000)}_{self._card_counter}"

    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO tasks (id, title, assignee, status, idempotency_key, created_at) "
        "VALUES (?, ?, ?, 'todo', ?, ?)",
        (card_id, title, assignee, idempotency_key, int(time.time())),
    )
    conn.commit()
    conn.close()
    return True, json.dumps({"id": card_id})
```

### 3. Simulating card completions

```python
def complete_fake_card(board_db, card_id, metadata=None, summary=""):
    conn = sqlite3.connect(str(board_db))
    conn.execute(
        "UPDATE tasks SET status='done', completed_at=? WHERE id=?",
        (int(time.time()), card_id),
    )
    conn.execute(
        "INSERT INTO task_runs (task_id, outcome, summary, metadata) "
        "VALUES (?, 'completed', ?, ?)",
        (card_id, summary, json.dumps(metadata) if metadata else None),
    )
    conn.commit()
    conn.close()
```

## The fourth critical monkey-patch: LOCK_FILE

**If you skip this, every tick silently SKIPs and tests pass for the wrong reason.**

The engine's `tick()` acquires an `fcntl.flock(LOCK_EX | LOCK_NB)` on a global
`LOCK_FILE` (`~/.hermes-teams/startup/kanban/workflow-engine.lock`). If a
production engine process is running, OR the lock file still points at the real
path, the flock call fails and `tick()` returns immediately with
`["SKIP tick: another engine process holds the lock"]`.

The symptom: tests that assert on dispatched actions get an empty list, but
the assertion still passes because "no actions" can look like correct behavior
(e.g., "second tick should not re-dispatch"). The test is green but proves
nothing.

In your test fixture, patch `LOCK_FILE` to a temp path:

```python
import workflow_engine.runtime as rt
world._orig_lock_file = rt.LOCK_FILE
rt.LOCK_FILE = world.tmpdir / "test-engine.lock"
# ... in cleanup:
rt.LOCK_FILE = world._orig_lock_file
```

This is separate from the `threading.Lock` inside Engine — that's an in-process
reentrancy guard, not a cross-process lock. You need the `fcntl` lock patched
for test isolation.

## Test lifecycle

```python
def test_example():
    world = FakeWorld()
    world.add_template({...})
    world.start("example", context={"key": "value"})
    world.tick()  # dispatch entry nodes

    # Find and complete the card
    conn = sqlite3.connect(str(world.board_db))
    card = conn.execute("SELECT id FROM tasks WHERE assignee='qa'").fetchone()[0]
    conn.close()
    world.complete_card(card, metadata={"verdict": "PASS"})

    world.tick()  # detect completion, dispatch next node

    # Assert on actions
    # Assert on board state
    # Assert on state DB

    world.cleanup()  # restore monkey-patches
```

## Cleanup

```python
def cleanup(self):
    import workflow_engine.kanban_adapter as ka
    import workflow_engine.runtime as rt
    ka.KANBAN_HOME = self._orig_home
    rt.create_card = self._orig_create
```

Failure to cleanup causes subsequent tests to write to temp dirs that no
longer exist.

## Fake board schema

The fake board needs at minimum: `tasks` (id, title, assignee, status,
idempotency_key, completed_at, created_at) and `task_runs` (id, task_id,
outcome, summary, metadata). Match the real Hermes kanban schema.

## Why this works

The engine doesn't know it's in a fake world. It:
- Reads templates from the temp templates dir (real JSON files)
- Writes cards to the fake board DB (real SQLite, real schema)
- Reads card status from the fake board (real SQL queries)
- Persists state to the temp state DB (real SQLite)
- Processes triggers from the fake board (real completion data)

The ONLY thing faked is the boundary: no `hermes kanban` CLI calls, no
gateway dispatch, no async waiting. Everything inside the engine is real.
