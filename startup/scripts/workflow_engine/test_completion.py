"""T7: Completion model — fence + skip propagation + reachability.

Verifies the completion decision per DESIGN §Completion Check + §Activation Rule:
  1. Conditional diamond: one branch skipped, workflow still completes.
  2. Skipped exit node does NOT block completion (terminal-for-exit = done/failed/skipped).
  3. Disconnected component (orphan subgraph) does NOT block completion.
  4. Foreach exit node: completion fence re-reads ALL card statuses from the board.
  5. Completion fence catches card regression (done→todo prevents false completion).

Run: python3 -m pytest test_completion.py -v
"""
import json
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

SCRIPTS = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPTS))

from workflow_engine.store import TemplateStore
from workflow_engine.kanban_adapter import board_db_path
from workflow_engine.runtime import Engine, StateDB


# ═══════════════════════════════════════════════════════════════════════════
# Helpers — mirror of test_engine.py's FakeWorld (self-contained fixture)
# ═══════════════════════════════════════════════════════════════════════════

def make_fake_board(tmpdir: Path, board_name: str = "test-board") -> str:
    db_path = tmpdir / "boards" / board_name / "kanban.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE tasks (
            id TEXT PRIMARY KEY, title TEXT, assignee TEXT,
            status TEXT DEFAULT 'todo', idempotency_key TEXT,
            completed_at INTEGER, priority INTEGER DEFAULT 0,
            body TEXT DEFAULT '', created_at INTEGER NOT NULL,
            parents TEXT DEFAULT '[]'
        );
        CREATE TABLE task_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
            outcome TEXT, summary TEXT, metadata TEXT,
            FOREIGN KEY (task_id) REFERENCES tasks(id)
        );
    """)
    conn.commit()
    conn.close()
    return board_name


def complete_fake_card(board_db: Path, card_id: str, metadata: dict | None = None,
                       summary: str = ""):
    conn = sqlite3.connect(str(board_db))
    conn.execute("UPDATE tasks SET status = 'done', completed_at = ? WHERE id = ?",
                 (int(time.time()), card_id))
    conn.execute("INSERT INTO task_runs (task_id, outcome, summary, metadata) VALUES (?, 'completed', ?, ?)",
                 (card_id, summary, json.dumps(metadata) if metadata else None))
    conn.commit()
    conn.close()


def set_card_status(board_db: Path, card_id: str, status: str):
    """Force a card to an arbitrary status (for regression tests)."""
    conn = sqlite3.connect(str(board_db))
    conn.execute("UPDATE tasks SET status = ?, completed_at = ? WHERE id = ?",
                 (status, None, card_id))
    conn.commit()
    conn.close()


class FakeWorld:
    def __init__(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="wf-comp-"))
        self.board = make_fake_board(self.tmpdir, "test-board")
        self.board_db = self.tmpdir / "boards" / "test-board" / "kanban.db"
        self.templates_dir = self.tmpdir / "templates"
        self.templates_dir.mkdir(parents=True)
        import workflow_engine.kanban_adapter as ka
        self._orig_home = ka.KANBAN_HOME
        ka.KANBAN_HOME = self.tmpdir / "boards"
        self.state_db_path = self.tmpdir / "state.db"
        self.engine = Engine(self.templates_dir)
        self.engine.state = StateDB(self.state_db_path)
        import workflow_engine.runtime as rt
        self._orig_create = rt.create_card
        rt.create_card = self._fake_create_card

    def _fake_create_card(self, board, title, assignee, body="", idempotency_key=None,
                          priority=None, workspace=None, parent=None):
        db = self.tmpdir / "boards" / board / "kanban.db"
        if not hasattr(self, '_card_counter'):
            self._card_counter = 0
        self._card_counter += 1
        card_id = f"t_{int(time.time()*1000)}_{self._card_counter}"
        conn = sqlite3.connect(str(db))
        conn.execute("INSERT INTO tasks (id, title, assignee, status, idempotency_key, created_at, body) VALUES (?, ?, ?, 'todo', ?, ?, ?)",
                     (card_id, title, assignee, idempotency_key, int(time.time()), body))
        conn.commit()
        conn.close()
        return True, json.dumps({"id": card_id})

    def add_template(self, template: dict):
        path = self.templates_dir / f"{template['id']}.json"
        path.write_text(json.dumps(template, indent=2))

    def tick(self):
        return self.engine.tick()

    def start(self, workflow_id, context=None):
        return self.engine.start_manual(
            workflow_id=workflow_id, board=self.board,
            project_dir=str(self.tmpdir), context=context or {},
        )

    def complete_card(self, card_id, metadata=None, summary=""):
        complete_fake_card(self.board_db, card_id, metadata, summary)

    def regress_card(self, card_id, status="todo"):
        set_card_status(self.board_db, card_id, status)

    def state_snapshot(self):
        instances = self.engine.state.load_active_instances()
        if not instances:
            return {}
        loaded = self.engine.state.load_state(instances[0].instance_id)
        return loaded.get("state", {})

    def card_id_for_node(self, node_id: str) -> str:
        conn = sqlite3.connect(str(self.board_db))
        row = conn.execute("SELECT id FROM tasks WHERE idempotency_key LIKE ?",
                           (f"%:{node_id}",)).fetchone()
        conn.close()
        return row[0] if row else None

    def cleanup(self):
        import workflow_engine.kanban_adapter as ka
        import workflow_engine.runtime as rt
        ka.KANBAN_HOME = self._orig_home
        rt.create_card = self._orig_create


def _instance_complete(world) -> bool:
    """Has the (single) active instance been marked completed?"""
    active = world.engine.state.load_active_instances()
    return len(active) == 0


# ═══════════════════════════════════════════════════════════════════════════
# TEST 1: Conditional diamond — one branch skipped, workflow completes
# ═══════════════════════════════════════════════════════════════════════════

def test_conditional_diamond_one_branch_skipped_completes():
    """Diamond: check → (ship on PASS, fix on FAIL). On PASS verdict:
    fix is a dead branch (condition false) → SKIPPED via skip propagation.
    ship completes normally. Workflow completes even though fix never ran.
    """
    world = FakeWorld()
    try:
        world.add_template({
            "id": "diamond",
            "name": "Conditional diamond",
            "nodes": [
                {"id": "check", "profile": "qa", "skill": "live-testing",
                 "body_template": "Run QA",
                 "output": {"schema": {"required": ["verdict"]}}},
                {"id": "ship", "profile": "product-owner", "skill": "dev-dispatch",
                 "body_template": "Ship it",
                 "depends_on": ["check"],
                 "condition": "${nodes.check.output.verdict} == 'PASS'"},
                {"id": "fix", "profile": "debugger", "skill": "debug-loop",
                 "body_template": "Fix it",
                 "depends_on": ["check"],
                 "condition": "${nodes.check.output.verdict} == 'FAIL'"},
            ],
        })
        world.start("diamond")
        world.tick()  # dispatch check
        check_card = world.card_id_for_node("check")
        assert check_card, "check should have dispatched a card"

        # PASS verdict → ship branch fires, fix branch is dead.
        world.complete_card(check_card, metadata={"verdict": "PASS"})
        actions = world.tick()
        assert any("DISPATCHED" in a and "node ship" in a for a in actions), \
            f"ship should dispatch on PASS, got: {actions}"
        assert any("SKIPPED" in a and "node fix" in a for a in actions), \
            f"fix should be SKIPPED (dead branch on PASS), got: {actions}"

        # Complete ship — now both exits are terminal (ship done, fix skipped).
        ship_card = world.card_id_for_node("ship")
        assert ship_card
        world.complete_card(ship_card, metadata={"shipped": True})

        actions = world.tick()
        assert any("WORKFLOW COMPLETE" in a for a in actions), \
            f"Workflow should complete with one branch done + one skipped, got: {actions}"
        assert _instance_complete(world), "Instance should be marked completed"
    finally:
        world.cleanup()


# ═══════════════════════════════════════════════════════════════════════════
# TEST 2: Skipped exit node does NOT block completion
# ═══════════════════════════════════════════════════════════════════════════

def test_skipped_exit_node_does_not_block_completion():
    """A graph where an exit node is itself skipped (dead branch) but a sibling
    exit node completes. The skipped exit must not block completion because
    terminal-for-exit = {done, failed, skipped}.
    """
    world = FakeWorld()
    try:
        world.add_template({
            "id": "skipped-exit",
            "name": "Skipped exit",
            "nodes": [
                {"id": "gate", "profile": "qa", "skill": "live-testing",
                 "body_template": "Gate",
                 "output": {"schema": {"required": ["ok"]}}},
                # normal path — always runs, becomes the completing exit.
                {"id": "normal", "profile": "developer", "skill": "developer-loop",
                 "body_template": "Normal path",
                 "depends_on": ["gate"],
                 "condition": "${nodes.gate.output.ok} == 'yes'"},
                # dead-path exit — skipped when ok=='yes'. It has no dependents
                # so it's an EXIT node that gets skipped.
                {"id": "dead_exit", "profile": "debugger", "skill": "debug-loop",
                 "body_template": "Only on failure",
                 "depends_on": ["gate"],
                 "condition": "${nodes.gate.output.ok} == 'no'"},
            ],
        })
        world.start("skipped-exit")
        world.tick()
        gate_card = world.card_id_for_node("gate")
        assert gate_card

        world.complete_card(gate_card, metadata={"ok": "yes"})
        world.tick()
        # dead_exit must be skipped (its only incoming source is terminal-but-not-firing)
        snap = world.state_snapshot()
        assert snap.get("dead_exit", {}).get("skipped"), \
            f"dead_exit should be marked skipped, state: {snap.get('dead_exit')}"

        normal_card = world.card_id_for_node("normal")
        assert normal_card, "normal should have dispatched"
        world.complete_card(normal_card, metadata={"done": True})

        actions = world.tick()
        assert any("WORKFLOW COMPLETE" in a for a in actions), \
            f"Skipped exit node must not block completion, got: {actions}"
        assert _instance_complete(world)
    finally:
        world.cleanup()


# ═══════════════════════════════════════════════════════════════════════════
# TEST 3: Disconnected component (orphan subgraph) does NOT block completion
# ═══════════════════════════════════════════════════════════════════════════

def test_disconnected_component_does_not_block_completion():
    """Main path: entry → follow (completes). Orphan: lone node with no edges to
    main path (depends only on itself). The orphan can never be reached from the
    BFS seed set, so reachability ignores it and the workflow completes.
    """
    world = FakeWorld()
    try:
        world.add_template({
            "id": "disconnected",
            "name": "Disconnected component",
            "nodes": [
                {"id": "entry", "profile": "qa", "skill": "live-testing",
                 "body_template": "Entry"},
                {"id": "follow", "profile": "developer", "skill": "developer-loop",
                 "body_template": "Follows entry", "depends_on": ["entry"]},
                # Orphan — a self-cycle with no path from entry/follow.
                {"id": "orphan", "profile": "qa", "skill": "live-testing",
                 "body_template": "Orphan", "depends_on": ["orphan"]},
            ],
        })
        world.start("disconnected")
        world.tick()
        entry_card = world.card_id_for_node("entry")
        assert entry_card

        world.complete_card(entry_card, metadata={"ok": True})
        world.tick()
        follow_card = world.card_id_for_node("follow")
        assert follow_card
        world.complete_card(follow_card, metadata={"ok": True})

        actions = world.tick()
        assert any("WORKFLOW COMPLETE" in a for a in actions), \
            f"Disconnected orphan must not block completion, got: {actions}"
        assert _instance_complete(world)
    finally:
        world.cleanup()


# ═══════════════════════════════════════════════════════════════════════════
# TEST 4: Foreach exit node — fence re-reads ALL card statuses
# ═══════════════════════════════════════════════════════════════════════════

def _foreach_template(tid: str, items: list) -> dict:
    """A 2-node template: src produces a list, fan fans it out into N cards.
    `fan` is the exit node (no dependents)."""
    return {
        "id": tid,
        "name": tid,
        "nodes": [
            {"id": "src", "profile": "qa", "skill": "live-testing",
             "body_template": "Produce list",
             "output": {"schema": {"required": ["items"]}}},
            {"id": "fan", "profile": "developer", "skill": "developer-loop",
             "body_template": "Review ${item}",
             "foreach": "${nodes.src.output.items}",
             "depends_on": ["src"]},
        ],
        "edges": [{"from": "src", "to": "fan"}],
    }


def test_foreach_exit_fence_rereads_all_cards():
    """A foreach node as an exit node. The completion fence must re-read EVERY
    card status from the board (not cached state). Completing all cards lets the
    workflow complete; regressing any one prevents false completion.
    """
    world = FakeWorld()
    try:
        world.add_template(_foreach_template("foreach-exit", ["a", "b", "c"]))
        world.start("foreach-exit")
        world.tick()  # dispatch src
        src_card = world.card_id_for_node("src")
        assert src_card
        world.complete_card(src_card, metadata={"items": ["a", "b", "c"]})
        world.tick()  # fan fans out → 3 cards

        snap = world.state_snapshot()
        cards = snap.get("fan", {}).get("cards", [])
        assert len(cards) == 3, f"Expected 3 foreach cards, got {len(cards)}: {snap.get('fan')}"

        # Not yet complete — only some done.
        world.complete_card(cards[0], metadata={"v": "a"})
        world.complete_card(cards[1], metadata={"v": "b"})
        world.tick()
        assert not _instance_complete(world), \
            "Workflow must NOT complete until ALL foreach cards are done"

        # Complete the last one → fence sees all done → completes.
        world.complete_card(cards[2], metadata={"v": "c"})
        actions = world.tick()
        assert any("WORKFLOW COMPLETE" in a for a in actions), \
            f"All foreach cards done should complete, got: {actions}"
        assert _instance_complete(world)
    finally:
        world.cleanup()


def test_foreach_exit_fence_catches_regression():
    """Foreach exit: complete all cards, then regress one to 'todo'. The fence
    re-reads board truth and must NOT falsely complete."""
    world = FakeWorld()
    try:
        world.add_template(_foreach_template("foreach-regress", ["a", "b"]))
        world.start("foreach-regress")
        world.tick()
        src_card = world.card_id_for_node("src")
        assert src_card
        world.complete_card(src_card, metadata={"items": ["a", "b"]})
        world.tick()

        snap = world.state_snapshot()
        cards = snap.get("fan", {}).get("cards", [])
        assert len(cards) == 2

        # Complete both, then regress the first BEFORE ticking.
        world.complete_card(cards[0], metadata={"v": "a"})
        world.complete_card(cards[1], metadata={"v": "b"})
        world.regress_card(cards[0], status="todo")

        actions = world.tick()
        assert not _instance_complete(world), \
            f"Foreach fence must catch card regression, got: {actions}"
        assert not any("WORKFLOW COMPLETE" in a for a in actions), \
            f"Must not falsely complete with a regressed foreach card, got: {actions}"
    finally:
        world.cleanup()


# ═══════════════════════════════════════════════════════════════════════════
# TEST 5: Completion fence catches single-card regression (done→todo)
# ═══════════════════════════════════════════════════════════════════════════

def test_completion_fence_catches_card_regression():
    """Single-card exit node. Complete the card → workflow would complete. But
    if the card regresses to 'todo' (board truth), the completion fence re-reads
    it and refuses to complete — no false-positive completion.
    """
    world = FakeWorld()
    try:
        world.add_template({
            "id": "single-exit",
            "name": "Single exit",
            "nodes": [
                {"id": "only", "profile": "qa", "skill": "live-testing",
                 "body_template": "The only node"},
            ],
        })
        world.start("single-exit")
        world.tick()
        only_card = world.card_id_for_node("only")
        assert only_card

        # Complete then regress before the tick that would finish the workflow.
        world.complete_card(only_card, metadata={"ok": True})
        world.regress_card(only_card, status="todo")

        actions = world.tick()
        assert not _instance_complete(world), \
            f"Regressed card must prevent completion, got: {actions}"
        assert not any("WORKFLOW COMPLETE" in a for a in actions), \
            f"Must not falsely complete with regressed card, got: {actions}"

        # Now complete for real → completes.
        world.complete_card(only_card, metadata={"ok": True})
        actions = world.tick()
        assert any("WORKFLOW COMPLETE" in a for a in actions), \
            f"Genuinely-done card should complete, got: {actions}"
        assert _instance_complete(world)
    finally:
        world.cleanup()


if __name__ == "__main__":
    test_conditional_diamond_one_branch_skipped_completes()
    print("OK: conditional diamond one branch skipped completes")
    test_skipped_exit_node_does_not_block_completion()
    print("OK: skipped exit node does not block completion")
    test_disconnected_component_does_not_block_completion()
    print("OK: disconnected component does not block completion")
    test_foreach_exit_fence_rereads_all_cards()
    print("OK: foreach exit fence re-reads all cards")
    test_foreach_exit_fence_catches_regression()
    print("OK: foreach exit fence catches regression")
    test_completion_fence_catches_card_regression()
    print("OK: completion fence catches card regression")
    print("\nAll T7 completion-model tests passed.")
