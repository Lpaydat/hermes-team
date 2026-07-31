# Hybrid Integration Testing — Real Boards, Simulated Completions

A third testing tier between FakeWorld (fully mocked) and the real-integration
echo-test (fully real, 60s+ per node). The hybrid pattern creates **real kanban
boards** and dispatches **real cards** through the engine's `create_card` →
`hermes kanban create` path, but **simulates card completions via direct SQLite
writes** instead of waiting for real agents.

Result: tests run in seconds, not minutes, while still proving the real plumbing
(CLI calls, real SQLite schema, idempotency keys, metadata reads, trigger
detection). Only 1-2 tests use real agent dispatch (gated behind a `--real` flag).

## When to use each tier

| Tier | Speed | Proves | Use for |
|------|-------|-------|---------|
| FakeWorld | ms | Engine logic (tick ordering, variable resolution, state) | Logic regression suite, adversarial tests |
| **Hybrid (this pattern)** | **1-3s** | **Real board schema, real CLI card creation, real metadata/trigger reads** | **CI, fast integration feedback, adapter correctness** |
| Real echo-test | 60-90s/node | Dispatcher handoff, real agent execution, end-to-end | Periodic smoke test, release validation |

## The simulated-completion recipe

When a real agent completes a card, `kanban_complete` does two SQL operations.
The hybrid test replicates these directly against the real board DB:

```python
import sqlite3, json, time

def _simulate_completion(board: str, card_id: str,
                         metadata: dict | None = None,
                         summary: str = "",
                         outcome: str = "completed"):
    """Mark a card done with a completed run — mimics kanban_complete."""
    db = KANBAN_HOME / board / "kanban.db"
    conn = sqlite3.connect(str(db))
    now = int(time.time())
    try:
        # 1. Mark the task done
        conn.execute(
            "UPDATE tasks SET status='done', completed_at=?, "
            "started_at=COALESCE(started_at, ?) WHERE id=?",
            (now, now, card_id),
        )
        # 2. Insert a task_run row (this is what get_card_metadata reads)
        conn.execute(
            "INSERT INTO task_runs (task_id, profile, status, outcome, "
            "summary, metadata, started_at, ended_at) "
            "VALUES (?, NULL, 'done', ?, ?, ?, ?, ?)",
            (card_id, outcome, summary,
             json.dumps(metadata) if metadata else None, now, now),
        )
        conn.commit()
    finally:
        conn.close()
```

**Critical columns in `task_runs`:** `outcome='completed'` (the adapter filters
on this), `metadata` (JSON string or NULL), `started_at` + `ended_at` (NOT NULL).
Missing `started_at`/`ended_at` causes an insert failure.

## Board lifecycle for test isolation

```python
def _unique_board_name(prefix="wf-int-test"):
    return f"{prefix}-{int(time.time())}-{uuid.uuid4().hex[:6]}"

# Setup
subprocess.run(["hermes", "kanban", "boards", "create", slug, "--name", "Test"])
assert (KANBAN_HOME / slug / "kanban.db").exists()

# ... test runs ...

# Teardown — --delete removes the directory entirely
subprocess.run(["hermes", "kanban", "boards", "rm", slug, "--delete"])
```

Use unique slugs (timestamp + uuid) so concurrent test runs don't collide.
Always clean up in a `finally:` block.

## State DB isolation

Each test gets its own temp state DB to prevent cross-test trigger contamination:

```python
tmpdir = Path(tempfile.mkdtemp(prefix="wf-int-"))
engine = Engine(templates_dir)
engine.state = StateDB(tmpdir / "state.db")  # isolated, not the real STATE_DB
```

## Fixture pattern: RealBoardFixture

```python
class RealBoardFixture:
    def __init__(self, template_data=None):
        self.board = _unique_board_name()
        self.tmpdir = Path(tempfile.mkdtemp(prefix="wf-int-"))
        self.templates_dir = self.tmpdir / "templates"
        self.templates_dir.mkdir(parents=True)
        assert _create_board(self.board)
        self.state_db_path = self.tmpdir / "state.db"
        self.engine = Engine(self.templates_dir)
        self.engine.state = StateDB(self.state_db_path)
        if template_data:
            self.add_template(template_data)

    def tick(self):
        return self.engine.tick()

    def start(self, workflow_id, context=None):
        return self.engine.start_manual(
            workflow_id=workflow_id, board=self.board,
            project_dir="", context=context or {})

    def complete_card(self, card_id, metadata=None, summary=""):
        _simulate_completion(self.board, card_id, metadata, summary)

    def cleanup(self):
        _delete_board(self.board)
```

**Key:** the engine uses the REAL `create_card` (no monkey-patching). Cards are
created through the production CLI path. Only the *completion* is simulated.

## Test categories that work well in hybrid mode

These exercise real board schema and adapter code without needing real agents:

1. **Real card creation** — verify `create_card` → CLI → real DB, check all fields
2. **Idempotency lookup** — `find_cards_by_idempotency_key` against real schema
3. **Metadata reading** — `get_card_metadata` against real `task_runs` table
4. **Trigger detection** — `find_recent_completions` with real JOIN queries
5. **Full lifecycle** — 3-node pipeline, simulated completions at each stage
6. **Trigger firing** — card_completed trigger → workflow instance starts
7. **Variable resolution** — verify `${nodes.x.output.y}` resolves in real card bodies
8. **Deleted board detection** — delete board mid-instance, verify zombie guard fires
9. **Status transitions** — ready → running → done on real schema
10. **Edge cases** — empty metadata, large metadata (10k+ chars)

## Gating real-agent tests behind --real

```python
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--real", action="store_true",
                        help="Include real agent dispatch tests (slow, 60s+)")
    parser.add_argument("--only", type=str, default="",
                        help="Run only tests matching this substring")
    args = parser.parse_args()

    all_tests = [/* fast hybrid tests */]
    if args.real:
        all_tests.append(("test_real_agent_echo", test_real_agent_echo))
```

The default run is fast (all simulated). `--real` adds the slow agent-dispatch
test for end-to-end validation when you have time.

## Key findings

1. **Real boards default created cards to `ready` status**, not `todo`. The engine's
   `create_card` calls `hermes kanban create`, which sets status='ready' for
   assignable cards. Tests should assert `status in ("todo", "ready")`.

2. **`_simulate_completion` must set `started_at`** if it was NULL — the real
   `task_runs` table requires `started_at NOT NULL`. Use
   `started_at=COALESCE(started_at, ?)` in the UPDATE.

3. **`task_runs.outcome='completed'` is the filter** that `get_card_metadata` and
   `find_recent_completions` query on. Setting `outcome` to anything else makes
   the card invisible to the adapter — a common simulation bug.

4. **Board deletion is fast and clean.** `hermes kanban boards rm <slug> --delete`
   removes the entire directory (DB + workspaces). Verified: no leftovers in
   `_archived/` or active boards after a full test run.

5. **`--only` substring filtering** lets you iterate on a single test class
   during development without waiting for the full suite.
