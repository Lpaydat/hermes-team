"""
Variable resolution and data flow edge case tests.

This suite probes the trickiest part of the workflow engine: how data flows
between nodes — template resolution, condition evaluation, and metadata
propagation across the tick loop. It covers type coercion (dict/list/None/bool
variable values), circular references, dotted keys, non-existent references,
recursive expansion, empty/escaped variables, unicode, deeply nested metadata,
and output mutation between ticks.

Two layers of tests:
  1. Unit tests — call resolve_template / evaluate_condition directly with
     hand-built contexts. These pin the exact string the engine produces for
     each value type, so regressions are caught immediately.
  2. Integration tests — use the FakeWorld harness from test_engine.py to
     exercise the full tick loop (dispatch → complete → resolve → advance),
     verifying end-to-end data flow on a real (fake) board.

Run: python3 -m pytest test_dataflow.py -v
Or:  python3 test_dataflow.py
"""
import json
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

# Add scripts dir to path
SCRIPTS = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPTS))

from workflow_engine.model import resolve_template, evaluate_condition
from workflow_engine.runtime import Engine, StateDB, NodeStatus
from workflow_engine.kanban_adapter import KANBAN_HOME


# ═══════════════════════════════════════════════════════════════════════════
# FakeWorld harness — copied from test_engine.py (DO NOT modify test_engine.py)
# ═══════════════════════════════════════════════════════════════════════════

def _make_fake_board(tmpdir: Path, board_name: str = "test-board") -> str:
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
        CREATE TABLE task_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
            kind TEXT NOT NULL, payload TEXT, ts INTEGER NOT NULL
        );
        CREATE TABLE task_links (
            child_id TEXT NOT NULL, parent_id TEXT NOT NULL,
            PRIMARY KEY (child_id, parent_id)
        );
    """)
    conn.commit()
    conn.close()
    return board_name


def _complete_fake_card(board_db: Path, card_id: str, metadata: dict | None = None,
                        summary: str = ""):
    conn = sqlite3.connect(str(board_db))
    conn.execute(
        "UPDATE tasks SET status = 'done', completed_at = ? WHERE id = ?",
        (int(time.time()), card_id),
    )
    conn.execute(
        """INSERT INTO task_runs (task_id, outcome, summary, metadata)
           VALUES (?, 'completed', ?, ?)""",
        (card_id, summary, json.dumps(metadata) if metadata else None),
    )
    conn.commit()
    conn.close()


class FakeWorld:
    """Test fixture: temp dir, fake board, engine, state DB.

    Stores resolved body in the tasks.body column so tests can read it back
    to verify variable resolution end-to-end.
    """

    def __init__(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="wf-dataflow-"))
        self.board = _make_fake_board(self.tmpdir, "test-board")
        self.board_db = self.tmpdir / "boards" / "test-board" / "kanban.db"
        self.templates_dir = self.tmpdir / "templates"
        self.templates_dir.mkdir(parents=True)

        import workflow_engine.kanban_adapter as ka
        self._orig_home = ka.KANBAN_HOME
        ka.KANBAN_HOME = self.tmpdir / "boards"

        # Isolate the engine's global file lock so concurrent test processes
        # (or a production engine) can't starve our ticks. Without this,
        # Engine.tick() returns "SKIP tick: another engine process holds the
        # lock" and downstream assertions see None card_ids.
        import workflow_engine.runtime as rt_mod
        self._orig_lock_file = rt_mod.LOCK_FILE
        rt_mod.LOCK_FILE = self.tmpdir / "wf-engine-test.lock"

        self.state_db_path = self.tmpdir / "state.db"
        self.engine = Engine(self.templates_dir)
        self.engine.state = StateDB(self.state_db_path)

        import workflow_engine.runtime as rt
        self._orig_create = rt.create_card
        rt.create_card = self._fake_create_card

    def _fake_create_card(self, board, title, assignee, body="", idempotency_key=None,
                          priority=None, workspace=None):
        """Write to the fake board, persisting body so tests can inspect it."""
        db = self.tmpdir / "boards" / board / "kanban.db"
        if not hasattr(self, '_card_counter'):
            self._card_counter = 0
        self._card_counter += 1
        card_id = f"t_{int(time.time()*1000)}_{self._card_counter}"
        conn = sqlite3.connect(str(db))
        conn.execute(
            """INSERT INTO tasks (id, title, assignee, status, idempotency_key, body, created_at)
               VALUES (?, ?, ?, 'todo', ?, ?, ?)""",
            (card_id, title, assignee, idempotency_key, body, int(time.time())),
        )
        conn.commit()
        conn.close()
        return True, json.dumps({"id": card_id})

    def add_template(self, template: dict):
        path = self.templates_dir / f"{template['id']}.json"
        path.write_text(json.dumps(template, indent=2))

    def tick(self):
        return self.engine.tick()

    def start(self, workflow_id: str, context: dict | None = None) -> str:
        return self.engine.start_manual(
            workflow_id=workflow_id,
            board=self.board,
            project_dir=str(self.tmpdir),
            context=context or {},
        )

    def complete_card(self, card_id: str, metadata: dict | None = None, summary: str = ""):
        _complete_fake_card(self.board_db, card_id, metadata, summary)

    def get_card_body(self, card_id: str) -> str:
        conn = sqlite3.connect(str(self.board_db))
        row = conn.execute("SELECT body FROM tasks WHERE id = ?", (card_id,)).fetchone()
        conn.close()
        return row[0] if row else ""

    def get_card_id_by_assignee(self, assignee: str) -> str | None:
        conn = sqlite3.connect(str(self.board_db))
        row = conn.execute(
            "SELECT id FROM tasks WHERE assignee = ?", (assignee,)
        ).fetchone()
        conn.close()
        return row[0] if row else None

    def get_card_id_by_node(self, node_id: str) -> str | None:
        """Find a card by its idempotency key wf:<instance>:<node>."""
        conn = sqlite3.connect(str(self.board_db))
        rows = conn.execute(
            "SELECT id, idempotency_key FROM tasks WHERE idempotency_key LIKE ?",
            (f"wf:%{node_id}",),
        ).fetchall()
        conn.close()
        return rows[0][0] if rows else None

    def count_cards(self) -> int:
        conn = sqlite3.connect(str(self.board_db))
        count = conn.execute("SELECT count(*) FROM tasks").fetchone()[0]
        conn.close()
        return count

    def cleanup(self):
        import workflow_engine.kanban_adapter as ka
        import workflow_engine.runtime as rt
        ka.KANBAN_HOME = self._orig_home
        rt.LOCK_FILE = self._orig_lock_file
        rt.create_card = self._orig_create


# ═══════════════════════════════════════════════════════════════════════════
# UNIT TESTS — resolve_template with typed values
# ═══════════════════════════════════════════════════════════════════════════

# ─── 1-4. Variable resolves to dict / list / None / bool ──────────────────

def test_df_resolve_dict_value():
    """A variable resolving to a dict becomes a Python repr string.

    The engine uses str(value), which on a dict yields single-quoted Python
    repr — not JSON. This documents the current behavior so a switch to JSON
    (or json.dumps) is caught.
    """
    result = resolve_template(
        "Config: ${trigger.config}",
        {"trigger.config": {"nested": "value", "num": 42}},
    )
    assert result == "Config: {'nested': 'value', 'num': 42}", \
        f"Dict should become Python repr (single quotes), got: {result}"


def test_df_resolve_list_value():
    """A variable resolving to a list becomes a Python repr string."""
    result = resolve_template(
        "Items: ${trigger.items}",
        {"trigger.items": ["a", "b", "c"]},
    )
    assert result == "Items: ['a', 'b', 'c']", \
        f"List should become Python repr, got: {result}"


def test_df_resolve_list_of_dicts():
    """A list of dicts stringifies with Python repr of each dict."""
    result = resolve_template(
        "Beasts: ${trigger.beasts}",
        {"trigger.beasts": [{"id": 1}, {"id": 2}]},
    )
    assert "'id': 1" in result, f"List-of-dict repr missing element, got: {result}"
    assert "'id': 2" in result


def test_df_resolve_none_value():
    """A variable resolving to None becomes the literal string 'None'.

    WEAKNESS: None becomes 'None' (4 chars), not '' (empty string). Downstream
    templates and conditions receive a truthy-looking string. This documents it.
    """
    result = resolve_template("val: ${trigger.missing}", {"trigger.missing": None})
    assert result == "val: None", \
        f"None should stringify to 'None' (str(None)), got: {result}"


def test_df_resolve_none_absent_key():
    """A variable whose key is entirely absent from context is removed (empty).

    context.get(missing_key) returns None implicitly, but resolve_template
    iterates context.items(), so it never sees the key at all. The leftover
    ${...} is stripped by the regex cleanup pass.
    """
    result = resolve_template("val: ${trigger.ghost}", {})
    assert result == "val: ", \
        f"Absent key should be removed (empty), got: {result}"


def test_df_resolve_bool_true():
    """A variable resolving to True becomes 'True' (Python str), not 'true'."""
    result = resolve_template("flag: ${trigger.flag}", {"trigger.flag": True})
    assert result == "flag: True", \
        f"True should stringify to 'True' (capital T), got: {result}"


def test_df_resolve_bool_false():
    """A variable resolving to False becomes 'False' (Python str), not 'false'."""
    result = resolve_template("flag: ${trigger.flag}", {"trigger.flag": False})
    assert result == "flag: False", \
        f"False should stringify to 'False' (capital F), got: {result}"


def test_df_resolve_int_value():
    """An integer variable becomes its decimal string."""
    result = resolve_template("count: ${n}", {"n": 42})
    assert result == "count: 42", f"Int should stringify, got: {result}"


def test_df_resolve_float_value():
    """A float variable becomes its repr (str(float))."""
    result = resolve_template("rate: ${r}", {"r": 3.14})
    assert result == "rate: 3.14", f"Float should stringify, got: {result}"


def test_df_resolve_zero_and_empty_string():
    """0 and '' are distinct falsy values that str() differently."""
    assert resolve_template("z=${x}", {"x": 0}) == "z=0"
    assert resolve_template("e=${x}", {"x": ""}) == "e="


# ─── 5. Circular variable references ───────────────────────────────────────

def test_df_resolve_circular_references_unit():
    """At the resolve_template level, circular refs don't loop because
    resolution is a single replace pass over context.items(), not recursive.

    Context: node A's output key name is node B's output, and vice versa.
    The body references one; after one pass it's resolved. No infinite loop.
    """
    # Simulate: A.output.value references B, B.output.value references A
    # But in practice each is just a value in context.
    ctx = {
        "nodes.a.output.value": "from_b",
        "nodes.b.output.value": "from_a",
    }
    result = resolve_template("A says ${nodes.a.output.value}", ctx)
    assert result == "A says from_b", f"Circular context should resolve fine, got: {result}"


# ─── 6. Dotted keys ────────────────────────────────────────────────────────

def test_df_resolve_dotted_key_in_name():
    """A variable whose key contains dots resolves correctly.

    The engine treats the full ${...} content as a flat lookup key, so
    ${nodes.a.output.my.complex.key} works if context has that exact key.
    """
    ctx = {"nodes.a.output.my.complex.key": "deep_value"}
    result = resolve_template("val: ${nodes.a.output.my.complex.key}", ctx)
    assert result == "val: deep_value", f"Dotted key should resolve, got: {result}"


def test_df_resolve_dotted_key_with_dashes():
    """Keys with dashes (not just dots) resolve correctly."""
    ctx = {"nodes.a.output.branch-name": "feat/x"}
    result = resolve_template("b: ${nodes.a.output.branch-name}", ctx)
    assert result == "b: feat/x", f"Dashed key should resolve, got: {result}"


# ─── 7-8. Non-existent references ──────────────────────────────────────────

def test_df_resolve_nonexistent_node():
    """A variable referencing a non-existent node is stripped to empty."""
    result = resolve_template("val: ${nodes.ghost.output.value}", {})
    assert result == "val: ", \
        f"Non-existent node ref should be removed, got: {result}"


def test_df_resolve_nonexistent_output_key():
    """A variable referencing a non-existent output key on an existing node."""
    ctx = {"nodes.a.output.real_key": "yes"}
    result = resolve_template(
        "val: ${nodes.a.output.ghost_key}", ctx
    )
    assert result == "val: ", \
        f"Non-existent output key should be removed, got: {result}"


# ─── 9. Multiple variables in one body ─────────────────────────────────────

def test_df_resolve_multiple_variables():
    """Multiple distinct variables in one body all resolve."""
    ctx = {"a": "1", "b": "2", "c": "3"}
    result = resolve_template("${a} and ${b} and ${c}", ctx)
    assert result == "1 and 2 and 3", f"Multiple vars should resolve, got: {result}"


def test_df_resolve_repeated_variable():
    """The same variable referenced multiple times resolves everywhere."""
    ctx = {"x": "X"}
    result = resolve_template("${x} ${x} ${x}", ctx)
    assert result == "X X X", f"Repeated var should resolve everywhere, got: {result}"


def test_df_resolve_partial_mixed():
    """Some variables present, some absent — present ones resolve, absent removed."""
    ctx = {"present": "HERE"}
    result = resolve_template("[${present}][${absent}]", ctx)
    assert result == "[HERE][]", f"Mixed present/absent, got: {result}"


# ─── 10. Recursive expansion ───────────────────────────────────────────────

def test_df_resolve_recursive_expansion():
    """Variable inside a variable: ${${...}}.

    WEAKNESS: resolve_template does a single pass over context.items() in dict
    order. Nested ${${inner}} resolves only if the outer key appears AFTER the
    inner key in iteration order (so by the time we reach the outer, ${inner}
    was already substituted). This is ORDER-DEPENDENT and fragile.
    """
    ctx = {
        "nodes.meta.output.key": "nodes.target.output.value",
        "nodes.target.output.value": "hello",
    }
    result = resolve_template("${${nodes.meta.output.key}}", ctx)
    # meta.key first → ${nodes.target.output.value} → then target.value → hello
    assert result == "hello", \
        f"Recursive expansion in correct order should work, got: {result}"


def test_df_resolve_recursive_expansion_reverse_order():
    """Recursive expansion where outer key comes before inner in dict order.

    WEAKNESS: Because iteration is insertion-order, if the outer (composite)
    key is processed first, ${inner} is not yet resolved so the lookup misses,
    and the whole ${${...}} is stripped by the regex cleanup. The result is
    empty — silently losing data depending on dict key order.
    """
    ctx = {
        "nodes.target.output.value": "hello",          # inner first
        "nodes.meta.output.key": "nodes.target.output.value",  # outer second
    }
    result = resolve_template("${${nodes.meta.output.key}}", ctx)
    # Outer processed first: "${nodes.target.output.value}" not in context yet
    # (the context key is the literal "nodes.target.output.value", not the
    # template "${nodes.target.output.value}"), so no match; regex strips it.
    assert result == "", \
        f"Reverse-order recursive expansion yields empty (order-dependent), got: {result}"


def test_df_resolve_recursive_no_target():
    """Recursive expansion where inner resolves to a key not in context → empty."""
    ctx = {"nodes.meta.output.key": "nodes.target.output.value"}  # target absent
    result = resolve_template("${${nodes.meta.output.key}}", ctx)
    assert result == "", f"Recursive with no target should be empty, got: {result}"


# ─── 11. Empty variable ${} ────────────────────────────────────────────────

def test_df_resolve_empty_variable_no_context():
    """An empty ${} with no matching context key is left... NOT stripped.

    WEAKNESS: The cleanup regex requires at least one char between braces.
    ${} has zero chars so it is NOT matched by the regex and
    survives resolution as a literal "${}" in the output. This is an asymmetry:
    ${x} (missing) → empty, but ${} (empty) → literal "${}".
    """
    result = resolve_template("before ${} after", {})
    assert result == "before ${} after", \
        f"Empty ${{}} with no context key survives as literal (regex gap), got: {result}"


def test_df_resolve_empty_variable_empty_context_key():
    """An empty ${} with context key '' does substitute (edge of context.items)."""
    result = resolve_template("before ${} after", {"": "VAL"})
    assert result == "before VAL after", \
        f"Empty ${{}} with empty-string key should substitute, got: {result}"


# ─── 12. Variable with spaces ──────────────────────────────────────────────

def test_df_resolve_variable_with_spaces():
    """A variable with internal spaces ${ my var } won't match a key 'my var'.

    The engine builds the lookup key as "${" + key + "}", so only an exact
    context key of " my var " (with spaces) would match. With a clean context
    key 'my var', the spaced template form is stripped by regex.
    """
    # Exact key 'my var' (no surrounding spaces) does NOT match '${ my var }'
    result = resolve_template("before ${ my var } after", {"my var": "VAL"})
    assert result == "before  after", \
        f"Spaced variable should be stripped (no exact key match), got: {result}"


def test_df_resolve_variable_with_spaces_exact_key():
    """If the context key itself includes the spaces, it matches."""
    result = resolve_template("before ${ my var } after", {" my var ": "VAL"})
    assert result == "before VAL after", \
        f"Spaced variable with exact spaced key matches, got: {result}"


# ─── 13-14. Condition evaluation edge cases ───────────────────────────────

def test_df_condition_trigger_context_exists():
    """'${trigger.spec_path} exists' checks truthiness of the context value."""
    ctx_true = {"trigger.spec_path": "/real/path.md"}
    assert evaluate_condition("${trigger.spec_path} exists", ctx_true) is True

    ctx_false = {"trigger.spec_path": ""}
    assert evaluate_condition("${trigger.spec_path} exists", ctx_false) is False

    ctx_missing = {}
    assert evaluate_condition("${trigger.spec_path} exists", ctx_missing) is False


def test_df_condition_with_regex_chars():
    """A condition value containing regex special chars compares literally.

    evaluate_condition uses plain string == (after str()), not regex, so
    '/tmp/[test]/' matches literally without bracket interpretation.
    """
    ctx = {"nodes.a.output.path": "/tmp/[test]/"}
    assert evaluate_condition(
        "${nodes.a.output.path} == '/tmp/[test]/'", ctx
    ) is True

    ctx2 = {"nodes.a.output.path": "/tmp/test/"}
    assert evaluate_condition(
        "${nodes.a.output.path} == '/tmp/[test]/'", ctx2
    ) is False


def test_df_condition_inequality():
    """'!=' operator works and respects exact string comparison."""
    ctx = {"v": "PASS"}
    assert evaluate_condition("${v} != 'FAIL'", ctx) is True
    assert evaluate_condition("${v} != 'PASS'", ctx) is False


def test_df_condition_is_empty():
    """'is empty' checks falsiness."""
    assert evaluate_condition("${v} is empty", {"v": ""}) is True
    assert evaluate_condition("${v} is empty", {"v": 0}) is True  # 0 is falsy
    assert evaluate_condition("${v} is empty", {"v": "x"}) is False
    assert evaluate_condition("${v} is empty", {}) is True  # missing → falsy


def test_df_condition_bool_value():
    """A boolean in context: str(True) == 'True' != 'true'."""
    ctx = {"v": True}
    # str(True) is 'True', so == 'True' matches
    assert evaluate_condition("${v} == 'True'", ctx) is True
    # but == 'true' does NOT match (case sensitivity)
    assert evaluate_condition("${v} == 'true'", ctx) is False


def test_df_condition_none_value():
    """None in a condition: str(None) == 'None'."""
    ctx = {"v": None}
    assert evaluate_condition("${v} == 'None'", ctx) is True
    assert evaluate_condition("${v} exists", ctx) is False  # None is falsy


def test_df_condition_malformed():
    """A condition that matches no pattern returns False (safe default)."""
    assert evaluate_condition("this is not valid", {}) is False
    assert evaluate_condition("", {}) is False


# ─── 15. Escaped/literal ${} ───────────────────────────────────────────────

def test_df_resolve_literal_dollar_brace_not_variable():
    """A bare '$' not followed by '{' is left alone."""
    result = resolve_template("Price: $5 and $10", {})
    assert result == "Price: $5 and $10", f"Bare $ should survive, got: {result}"


def test_df_resolve_unmatched_brace():
    """A '${' with no closing '}' is left as-is (regex needs closing brace)."""
    result = resolve_template("oops ${nope", {})
    assert result == "oops ${nope", f"Unterminated ${{ should survive, got: {result}"


# ─── 16. Long string value ─────────────────────────────────────────────────

def test_df_resolve_very_long_string():
    """A 10000-char variable value resolves fully (no truncation in resolver)."""
    long_val = "A" * 10000
    result = resolve_template("pre:${x}:post", {"x": long_val})
    expected = f"pre:{long_val}:post"
    assert result == expected, \
        f"Long string should resolve fully ({len(result)} vs {len(expected)})"


# ─── 17. Unicode values ────────────────────────────────────────────────────

def test_df_resolve_unicode_value():
    """Unicode (emoji, CJK, accents) resolves correctly."""
    result = resolve_template(
        "name: ${n}", {"n": "café ☕ 日本語"}
    )
    assert result == "name: café ☕ 日本語", \
        f"Unicode should resolve intact, got: {result}"


def test_df_resolve_unicode_key():
    """A variable key with unicode resolves if context has the exact key."""
    ctx = {"nodes.a.output.名前": "タロウ"}
    result = resolve_template("名前: ${nodes.a.output.名前}", ctx)
    assert result == "名前: タロウ", f"Unicode key should resolve, got: {result}"


# ─── 18. Variable in title (unit) ──────────────────────────────────────────
# (Note: resolve_template is only called on body_template in the engine;
#  title is hardcoded as f"[{node.id}] {skill}". The integration test below
#  documents that titles do NOT get variable resolution.)

# ─── 19. Deeply nested metadata ────────────────────────────────────────────

def test_df_resolve_deeply_nested_dict_metadata():
    """A 5-level nested dict value stringifies to Python repr."""
    nested = {"l1": {"l2": {"l3": {"l4": {"l5": "deep"}}}}}
    result = resolve_template("v: ${x}", {"x": nested})
    assert "l5" in result and "'deep'" in result, \
        f"Nested dict repr should contain all levels, got: {result}"
    assert result == "v: {'l1': {'l2': {'l3': {'l4': {'l5': 'deep'}}}}}", \
        f"Deeply nested dict should be full Python repr, got: {result}"


def test_df_resolve_deeply_nested_list_metadata():
    """Deeply nested list/dict combos stringify correctly."""
    nested = [[[["deep"]]]]
    result = resolve_template("v: ${x}", {"x": nested})
    assert result == "v: [[[['deep']]]]", f"Nested list repr, got: {result}"


# ═══════════════════════════════════════════════════════════════════════════
# INTEGRATION TESTS — full tick loop with FakeWorld
# ═══════════════════════════════════════════════════════════════════════════

def test_df_integration_dict_output_flows_to_body():
    """End-to-end: node A output is a dict; node B body references it.

    The dict becomes Python repr in B's card body.
    """
    world = FakeWorld()
    try:
        world.add_template({
            "id": "dict-flow",
            "name": "Dict flow",
            "nodes": [
                {"id": "src", "profile": "qa", "skill": "live-testing",
                 "body_template": "produce config"},
                {"id": "sink", "profile": "developer", "skill": "developer-loop",
                 "body_template": "Config is ${nodes.src.output.config}",
                 "depends_on": ["src"]},
            ],
        })
        world.start("dict-flow")
        world.tick()  # dispatch src

        src_card = world.get_card_id_by_assignee("qa")
        world.complete_card(src_card, metadata={"config": {"key": "val", "n": 1}})

        world.tick()  # src done, dispatch sink

        sink_card = world.get_card_id_by_assignee("developer")
        assert sink_card, "sink card should be created"
        body = world.get_card_body(sink_card)
        assert "'key': 'val'" in body, f"Dict repr should be in body, got: {body}"
        assert body == "Config is {'key': 'val', 'n': 1}", \
            f"Full dict repr in body, got: {body}"
    finally:
        world.cleanup()
    print("OK: test_df_integration_dict_output_flows_to_body")


def test_df_integration_list_output_flows_to_body():
    """End-to-end: node A output is a list; node B body references it."""
    world = FakeWorld()
    try:
        world.add_template({
            "id": "list-flow",
            "name": "List flow",
            "nodes": [
                {"id": "src", "profile": "qa", "skill": "live-testing",
                 "body_template": "produce items"},
                {"id": "sink", "profile": "developer", "skill": "developer-loop",
                 "body_template": "Items: ${nodes.src.output.items}",
                 "depends_on": ["src"]},
            ],
        })
        world.start("list-flow")
        world.tick()
        src_card = world.get_card_id_by_assignee("qa")
        world.complete_card(src_card, metadata={"items": ["a", "b", "c"]})
        world.tick()

        sink_card = world.get_card_id_by_assignee("developer")
        body = world.get_card_body(sink_card)
        assert body == "Items: ['a', 'b', 'c']", \
            f"List repr should be in body, got: {body}"
    finally:
        world.cleanup()
    print("OK: test_df_integration_list_output_flows_to_body")


def test_df_integration_none_output_flows_as_string():
    """End-to-end: node A output value is None; B body shows 'None'."""
    world = FakeWorld()
    try:
        world.add_template({
            "id": "none-flow",
            "name": "None flow",
            "nodes": [
                {"id": "src", "profile": "qa", "skill": "live-testing",
                 "body_template": "produce nothing useful"},
                {"id": "sink", "profile": "developer", "skill": "developer-loop",
                 "body_template": "Result: [${nodes.src.output.result}]",
                 "depends_on": ["src"]},
            ],
        })
        world.start("none-flow")
        world.tick()
        src_card = world.get_card_id_by_assignee("qa")
        # Metadata with explicit null — JSON null → Python None
        world.complete_card(src_card, metadata={"result": None})
        world.tick()

        sink_card = world.get_card_id_by_assignee("developer")
        body = world.get_card_body(sink_card)
        assert body == "Result: [None]", \
            f"None should appear as literal 'None', got: {body}"
    finally:
        world.cleanup()
    print("OK: test_df_integration_none_output_flows_as_string")


def test_df_integration_bool_output_flows_as_python_str():
    """End-to-end: node A output is a bool; B body shows 'True'/'False'."""
    world = FakeWorld()
    try:
        world.add_template({
            "id": "bool-flow",
            "name": "Bool flow",
            "nodes": [
                {"id": "src", "profile": "qa", "skill": "live-testing",
                 "body_template": "produce flag"},
                {"id": "sink", "profile": "developer", "skill": "developer-loop",
                 "body_template": "Passed: ${nodes.src.output.passed}",
                 "depends_on": ["src"]},
            ],
        })
        world.start("bool-flow")
        world.tick()
        src_card = world.get_card_id_by_assignee("qa")
        world.complete_card(src_card, metadata={"passed": True})
        world.tick()

        sink_card = world.get_card_id_by_assignee("developer")
        body = world.get_card_body(sink_card)
        assert body == "Passed: True", \
            f"Bool True should appear as 'True' (Python str), got: {body}"
    finally:
        world.cleanup()
    print("OK: test_df_integration_bool_output_flows_as_python_str")


def test_df_integration_nonexistent_output_key_is_empty():
    """End-to-end: B references an output key A never produced → empty in body."""
    world = FakeWorld()
    try:
        world.add_template({
            "id": "ghost-key",
            "name": "Ghost key",
            "nodes": [
                {"id": "src", "profile": "qa", "skill": "live-testing",
                 "body_template": "produce real only"},
                {"id": "sink", "profile": "developer", "skill": "developer-loop",
                 "body_template": "real=[${nodes.src.output.real}] ghost=[${nodes.src.output.ghost}]",
                 "depends_on": ["src"]},
            ],
        })
        world.start("ghost-key")
        world.tick()
        src_card = world.get_card_id_by_assignee("qa")
        world.complete_card(src_card, metadata={"real": "YES"})
        world.tick()

        sink_card = world.get_card_id_by_assignee("developer")
        body = world.get_card_body(sink_card)
        assert body == "real=[YES] ghost=[]", \
            f"Real key resolves, ghost key is empty, got: {body}"
    finally:
        world.cleanup()
    print("OK: test_df_integration_nonexistent_output_key_is_empty")


def test_df_integration_nonexistent_node_reference():
    """End-to-end: B references a node that doesn't exist in the template.

    The variable is stripped to empty. No crash.
    """
    world = FakeWorld()
    try:
        world.add_template({
            "id": "ghost-node",
            "name": "Ghost node",
            "nodes": [
                {"id": "only", "profile": "qa", "skill": "live-testing",
                 "body_template": "val=[${nodes.ghost.output.v}]"},
            ],
        })
        world.start("ghost-node")
        world.tick()

        only_card = world.get_card_id_by_assignee("qa")
        body = world.get_card_body(only_card)
        assert body == "val=[]", \
            f"Non-existent node ref should be empty, got: {body}"
    finally:
        world.cleanup()
    print("OK: test_df_integration_nonexistent_node_reference")


def test_df_integration_multiple_variables_one_body():
    """End-to-end: a body with three variables from the same upstream."""
    world = FakeWorld()
    try:
        world.add_template({
            "id": "multi-var",
            "name": "Multi var",
            "nodes": [
                {"id": "src", "profile": "qa", "skill": "live-testing",
                 "body_template": "produce"},
                {"id": "sink", "profile": "developer", "skill": "developer-loop",
                 "body_template": "${nodes.src.output.a} ${nodes.src.output.b} ${nodes.src.output.c}",
                 "depends_on": ["src"]},
            ],
        })
        world.start("multi-var")
        world.tick()
        src_card = world.get_card_id_by_assignee("qa")
        world.complete_card(src_card, metadata={"a": "1", "b": "2", "c": "3"})
        world.tick()

        sink_card = world.get_card_id_by_assignee("developer")
        body = world.get_card_body(sink_card)
        assert body == "1 2 3", f"All three vars should resolve, got: {body}"
    finally:
        world.cleanup()
    print("OK: test_df_integration_multiple_variables_one_body")


def test_df_integration_trigger_context_variable():
    """End-to-end: a body references ${trigger.X} from manual start context."""
    world = FakeWorld()
    try:
        world.add_template({
            "id": "trigger-var",
            "name": "Trigger var",
            "nodes": [
                {"id": "work", "profile": "qa", "skill": "live-testing",
                 "body_template": "Project is ${trigger.project} card ${trigger.card_id}"},
            ],
        })
        world.start("trigger-var", context={"project": "acme-app", "card_id": "C-99"})
        world.tick()

        work_card = world.get_card_id_by_assignee("qa")
        body = world.get_card_body(work_card)
        assert body == "Project is acme-app card C-99", \
            f"Trigger context vars should resolve, got: {body}"
    finally:
        world.cleanup()
    print("OK: test_df_integration_trigger_context_variable")


def test_df_integration_empty_variable_in_body():
    """End-to-end: a body with literal ${} survives into the card (regex gap)."""
    world = FakeWorld()
    try:
        world.add_template({
            "id": "empty-var",
            "name": "Empty var",
            "nodes": [
                {"id": "work", "profile": "qa", "skill": "live-testing",
                 "body_template": "before ${} after"},
            ],
        })
        world.start("empty-var")
        world.tick()

        work_card = world.get_card_id_by_assignee("qa")
        body = world.get_card_body(work_card)
        # The regex cleanup \$\{[^}]+\} requires 1+ chars, so ${} survives
        assert body == "before ${} after", \
            f"Empty ${{}} survives as literal in card body, got: {body}"
    finally:
        world.cleanup()
    print("OK: test_df_integration_empty_variable_in_body")


def test_df_integration_unicode_output_flows():
    """End-to-end: node A produces unicode; B body shows it intact."""
    world = FakeWorld()
    try:
        world.add_template({
            "id": "unicode-flow",
            "name": "Unicode flow",
            "nodes": [
                {"id": "src", "profile": "qa", "skill": "live-testing",
                 "body_template": "produce name"},
                {"id": "sink", "profile": "developer", "skill": "developer-loop",
                 "body_template": "Name: ${nodes.src.output.name}",
                 "depends_on": ["src"]},
            ],
        })
        world.start("unicode-flow")
        world.tick()
        src_card = world.get_card_id_by_assignee("qa")
        world.complete_card(src_card, metadata={"name": "café ☕ 日本語"})
        world.tick()

        sink_card = world.get_card_id_by_assignee("developer")
        body = world.get_card_body(sink_card)
        assert body == "Name: café ☕ 日本語", \
            f"Unicode should flow intact through the tick loop, got: {body}"
    finally:
        world.cleanup()
    print("OK: test_df_integration_unicode_output_flows")


def test_df_integration_long_string_output():
    """End-to-end: node A produces a 10000-char value; it fits in B's body."""
    world = FakeWorld()
    try:
        world.add_template({
            "id": "long-flow",
            "name": "Long flow",
            "nodes": [
                {"id": "src", "profile": "qa", "skill": "live-testing",
                 "body_template": "produce blob"},
                {"id": "sink", "profile": "developer", "skill": "developer-loop",
                 "body_template": "pre:${nodes.src.output.blob}:post",
                 "depends_on": ["src"]},
            ],
        })
        long_val = "Z" * 10000
        world.start("long-flow")
        world.tick()
        src_card = world.get_card_id_by_assignee("qa")
        world.complete_card(src_card, metadata={"blob": long_val})
        world.tick()

        sink_card = world.get_card_id_by_assignee("developer")
        body = world.get_card_body(sink_card)
        assert body == f"pre:{long_val}:post", \
            f"10000-char value should fit in body ({len(body)} chars)"
    finally:
        world.cleanup()
    print("OK: test_df_integration_long_string_output")


def test_df_integration_deeply_nested_metadata_output():
    """End-to-end: node A output is a 5-level nested dict; B body shows repr."""
    world = FakeWorld()
    try:
        world.add_template({
            "id": "nested-flow",
            "name": "Nested flow",
            "nodes": [
                {"id": "src", "profile": "qa", "skill": "live-testing",
                 "body_template": "produce nested"},
                {"id": "sink", "profile": "developer", "skill": "developer-loop",
                 "body_template": "Nested: ${nodes.src.output.tree}",
                 "depends_on": ["src"]},
            ],
        })
        nested = {"l1": {"l2": {"l3": {"l4": {"l5": "deep"}}}}}
        world.start("nested-flow")
        world.tick()
        src_card = world.get_card_id_by_assignee("qa")
        world.complete_card(src_card, metadata={"tree": nested})
        world.tick()

        sink_card = world.get_card_id_by_assignee("developer")
        body = world.get_card_body(sink_card)
        assert "'l5': 'deep'" in body, f"Nested repr should reach l5, got: {body}"
        assert body == f"Nested: {nested!r}", \
            f"Full nested Python repr in body, got: {body}"
    finally:
        world.cleanup()
    print("OK: test_df_integration_deeply_nested_metadata_output")


def test_df_integration_title_not_resolved():
    """End-to-end: a variable in a conceptual 'title' is NOT resolved.

    The engine hardcodes the card title as f"[{node.id}] {skill}" and only
    resolves variables in body_template. There's no title_template field.
    This test documents that titles never contain resolved variables.
    """
    world = FakeWorld()
    try:
        world.add_template({
            "id": "title-test",
            "name": "Title test",
            "nodes": [
                {"id": "work", "profile": "qa", "skill": "live-testing",
                 "body_template": "Project ${trigger.project}"},
            ],
        })
        world.start("title-test", context={"project": "acme"})
        world.tick()

        conn = sqlite3.connect(str(world.board_db))
        row = conn.execute("SELECT title FROM tasks WHERE assignee = 'qa'").fetchone()
        conn.close()
        title = row[0] if row else ""
        # Title is hardcoded: "[work] live-testing" — no variable resolution
        assert title == "[work] live-testing", \
            f"Title should be hardcoded (no var resolution), got: {title}"
        assert "${trigger.project}" not in title, \
            "Title must not contain unresolved variables"
    finally:
        world.cleanup()
    print("OK: test_df_integration_title_not_resolved")


def test_df_integration_condition_gates_dispatch_on_output_value():
    """End-to-end: a downstream node's condition reads upstream output and gates."""
    world = FakeWorld()
    try:
        world.add_template({
            "id": "cond-gate",
            "name": "Cond gate",
            "nodes": [
                {"id": "check", "profile": "qa", "skill": "live-testing",
                 "body_template": "check"},
                {"id": "ship", "profile": "developer", "skill": "developer-loop",
                 "body_template": "ship it",
                 "depends_on": ["check"],
                 "condition": "${nodes.check.output.verdict} == 'PASS'"},
                {"id": "fix", "profile": "debugger", "skill": "debug-loop",
                 "body_template": "fix it",
                 "depends_on": ["check"],
                 "condition": "${nodes.check.output.verdict} == 'FAIL'"},
            ],
        })
        world.start("cond-gate")
        world.tick()
        check_card = world.get_card_id_by_assignee("qa")
        world.complete_card(check_card, metadata={"verdict": "PASS"})
        actions = world.tick()

        assert any("ship" in a and "DISPATCHED" in a for a in actions), \
            f"ship should dispatch on PASS, got: {actions}"
        assert not any("fix" in a and "DISPATCHED" in a for a in actions), \
            f"fix should NOT dispatch on PASS, got: {actions}"
    finally:
        world.cleanup()
    print("OK: test_df_integration_condition_gates_dispatch_on_output_value")


def test_df_integration_condition_with_none_output():
    """End-to-end: condition evaluates when upstream output is None/missing.

    The condition '${nodes.check.output.verdict} == 'PASS'' with a missing
    verdict → str(None) == 'PASS' → False. Node does not dispatch.
    """
    world = FakeWorld()
    try:
        world.add_template({
            "id": "cond-none",
            "name": "Cond none",
            "nodes": [
                {"id": "check", "profile": "qa", "skill": "live-testing",
                 "body_template": "check"},
                {"id": "ship", "profile": "developer", "skill": "developer-loop",
                 "body_template": "ship",
                 "depends_on": ["check"],
                 "condition": "${nodes.check.output.verdict} == 'PASS'"},
            ],
        })
        world.start("cond-none")
        world.tick()
        check_card = world.get_card_id_by_assignee("qa")
        # Complete with NO verdict key at all
        world.complete_card(check_card, metadata={"other": "x"})
        actions = world.tick()

        # verdict missing from context → context.get returns None → str(None)='None' != 'PASS'
        assert not any("ship" in a and "DISPATCHED" in a for a in actions), \
            f"ship should NOT dispatch when verdict missing, got: {actions}"
    finally:
        world.cleanup()
    print("OK: test_df_integration_condition_with_none_output")


def test_df_integration_output_persists_in_state_db():
    """End-to-end: after completion, node output is persisted in the state DB
    so a downstream node (or a restart) can read it.
    """
    world = FakeWorld()
    try:
        world.add_template({
            "id": "persist",
            "name": "Persist",
            "nodes": [
                {"id": "src", "profile": "qa", "skill": "live-testing",
                 "body_template": "produce"},
                {"id": "sink", "profile": "developer", "skill": "developer-loop",
                 "body_template": "got ${nodes.src.output.path}",
                 "depends_on": ["src"]},
            ],
        })
        world.start("persist")
        world.tick()
        src_card = world.get_card_id_by_assignee("qa")
        world.complete_card(src_card, metadata={"path": "/tmp/x.md", "count": 7})
        world.tick()

        # Read the state DB directly
        conn = sqlite3.connect(str(world.state_db_path))
        row = conn.execute(
            "SELECT output FROM node_states WHERE node_id = 'src'"
        ).fetchone()
        conn.close()
        output = json.loads(row[0]) if row else {}
        assert output.get("path") == "/tmp/x.md", f"State DB should persist output, got: {output}"
        assert output.get("count") == 7
    finally:
        world.cleanup()
    print("OK: test_df_integration_output_persists_in_state_db")


def test_df_integration_circular_template_references():
    """End-to-end: two nodes whose bodies reference each other's output.

    Because depends_on creates a DAG (enforced by the dispatch ordering), a
    true runtime circular dependency can't form through normal depends_on.
    But we can test that two sibling nodes (no dep between them) both
    referencing a third don't interfere, and that a body referencing an
    un-produced sibling output degrades to empty gracefully.
    """
    world = FakeWorld()
    try:
        world.add_template({
            "id": "circular-ref",
            "name": "Circular ref",
            "nodes": [
                {"id": "a", "profile": "qa", "skill": "live-testing",
                 "body_template": "a sees ${nodes.b.output.v}",
                 "depends_on": ["seed"]},
                {"id": "b", "profile": "developer", "skill": "developer-loop",
                 "body_template": "b sees ${nodes.a.output.v}",
                 "depends_on": ["seed"]},
                {"id": "seed", "profile": "researcher", "skill": "web-research",
                 "body_template": "seed"},
            ],
        })
        world.start("circular-ref")
        world.tick()  # dispatch seed only

        seed_card = world.get_card_id_by_assignee("researcher")
        world.complete_card(seed_card, metadata={"start": "go"})
        world.tick()  # seed done → dispatch a and b in parallel

        # a and b reference each other's output, but neither has completed yet,
        # so both bodies have empty refs. No crash, no infinite loop.
        a_card = world.get_card_id_by_assignee("qa")
        b_card = world.get_card_id_by_assignee("developer")
        assert a_card and b_card, "Both a and b should dispatch"
        a_body = world.get_card_body(a_card)
        b_body = world.get_card_body(b_card)
        assert a_body == "a sees ", \
            f"a's ref to b (not yet done) should be empty, got: {a_body}"
        assert b_body == "b sees ", \
            f"b's ref to a (not yet done) should be empty, got: {b_body}"
    finally:
        world.cleanup()
    print("OK: test_df_integration_circular_template_references")


def test_df_integration_dotted_output_key_flows():
    """End-to-end: an output key with dots in its name flows to a body ref.

    The context key is nodes.<id>.output.<dotted.key>. The body must use the
    exact same dotted string to match.
    """
    world = FakeWorld()
    try:
        world.add_template({
            "id": "dotted-flow",
            "name": "Dotted flow",
            "nodes": [
                {"id": "src", "profile": "qa", "skill": "live-testing",
                 "body_template": "produce"},
                {"id": "sink", "profile": "developer", "skill": "developer-loop",
                 "body_template": "deep=${nodes.src.output.my.complex.key}",
                 "depends_on": ["src"]},
            ],
        })
        world.start("dotted-flow")
        world.tick()
        src_card = world.get_card_id_by_assignee("qa")
        world.complete_card(src_card, metadata={"my.complex.key": "found_it"})
        world.tick()

        sink_card = world.get_card_id_by_assignee("developer")
        body = world.get_card_body(sink_card)
        assert body == "deep=found_it", \
            f"Dotted output key should flow to dotted ref, got: {body}"
    finally:
        world.cleanup()
    print("OK: test_df_integration_dotted_output_key_flows")


# ─── 20. Output mutation between ticks ─────────────────────────────────────

def test_df_integration_output_mutation_between_ticks():
    """End-to-end: a node's card metadata changes AFTER the node is marked done.

    WEAKNESS: Once a node is DONE, the engine does not re-read its card
    metadata on subsequent ticks (it only checks for regression to
    todo/ready/running). So a post-completion metadata edit on the card is
    NOT picked up by downstream nodes that haven't dispatched yet — but if
    the downstream already dispatched with the old value, it's too late.

    This test verifies the snapshot semantics: the value captured at the
    tick where the card first becomes 'done' is the value downstream sees.
    """
    world = FakeWorld()
    try:
        world.add_template({
            "id": "mutate",
            "name": "Mutate",
            "nodes": [
                {"id": "src", "profile": "qa", "skill": "live-testing",
                 "body_template": "produce v1"},
                {"id": "sink", "profile": "developer", "skill": "developer-loop",
                 "body_template": "version=${nodes.src.output.version}",
                 "depends_on": ["src"]},
            ],
        })
        world.start("mutate")
        world.tick()
        src_card = world.get_card_id_by_assignee("qa")
        world.complete_card(src_card, metadata={"version": "v1"})
        world.tick()  # src done (captures v1), dispatches sink with v1

        sink_card = world.get_card_id_by_assignee("developer")
        body_before = world.get_card_body(sink_card)
        assert body_before == "version=v1", \
            f"Sink should capture v1 at dispatch, got: {body_before}"

        # Now mutate src's card metadata to v2 (simulating post-completion edit)
        conn = sqlite3.connect(str(world.board_db))
        # Add a NEW completed run with v2 metadata
        conn.execute(
            "INSERT INTO task_runs (task_id, outcome, summary, metadata) "
            "VALUES (?, 'completed', '', ?)",
            (src_card, json.dumps({"version": "v2"})),
        )
        conn.commit()
        conn.close()

        # Tick again — src is already DONE, engine won't re-read it
        world.tick()

        # The sink card body was already set at dispatch time; it doesn't change
        body_after = world.get_card_body(sink_card)
        assert body_after == "version=v1", \
            f"Sink body is immutable after dispatch (captured v1), got: {body_after}"

        # The state DB also retains the v1 snapshot (not updated post-done)
        conn = sqlite3.connect(str(world.state_db_path))
        row = conn.execute(
            "SELECT output FROM node_states WHERE node_id = 'src'"
        ).fetchone()
        conn.close()
        output = json.loads(row[0]) if row else {}
        assert output.get("version") == "v1", \
            f"State DB should retain v1 snapshot (not re-read post-done), got: {output}"
    finally:
        world.cleanup()
    print("OK: test_df_integration_output_mutation_between_ticks")


def test_df_integration_output_read_on_completion_tick():
    """End-to-end: the engine reads card metadata exactly when status→done.

    Verifies the happy path: metadata is read on the tick where the card
    transitions to done, and that value propagates. This is the complement
    to the mutation test — confirming the read happens at the right time.
    """
    world = FakeWorld()
    try:
        world.add_template({
            "id": "read-timing",
            "name": "Read timing",
            "nodes": [
                {"id": "src", "profile": "qa", "skill": "live-testing",
                 "body_template": "produce"},
                {"id": "sink", "profile": "developer", "skill": "developer-loop",
                 "body_template": "val=${nodes.src.output.x}",
                 "depends_on": ["src"]},
            ],
        })
        world.start("read-timing")
        world.tick()
        src_card = world.get_card_id_by_assignee("qa")

        # Card not done yet — tick should not read metadata
        world.tick()
        sink_card = world.get_card_id_by_assignee("developer")
        assert sink_card is None, "Sink should not dispatch while src not done"

        # Now complete src
        world.complete_card(src_card, metadata={"x": "CAPTURED"})
        actions = world.tick()

        # This tick: src detected done, x read, sink dispatched with CAPTURED
        sink_card = world.get_card_id_by_assignee("developer")
        assert sink_card, "Sink should dispatch after src completes"
        body = world.get_card_body(sink_card)
        assert body == "val=CAPTURED", \
            f"Metadata read on completion tick should propagate, got: {body}"
    finally:
        world.cleanup()
    print("OK: test_df_integration_output_read_on_completion_tick")


# ─── Bonus: escaped variable patterns ──────────────────────────────────────

def test_df_integration_adjacent_variables():
    """End-to-end: two variables with no space between them both resolve."""
    world = FakeWorld()
    try:
        world.add_template({
            "id": "adjacent",
            "name": "Adjacent",
            "nodes": [
                {"id": "src", "profile": "qa", "skill": "live-testing",
                 "body_template": "produce"},
                {"id": "sink", "profile": "developer", "skill": "developer-loop",
                 "body_template": "${nodes.src.output.a}${nodes.src.output.b}",
                 "depends_on": ["src"]},
            ],
        })
        world.start("adjacent")
        world.tick()
        src_card = world.get_card_id_by_assignee("qa")
        world.complete_card(src_card, metadata={"a": "foo", "b": "bar"})
        world.tick()

        sink_card = world.get_card_id_by_assignee("developer")
        body = world.get_card_body(sink_card)
        assert body == "foobar", \
            f"Adjacent variables should concatenate, got: {body}"
    finally:
        world.cleanup()
    print("OK: test_df_integration_adjacent_variables")


def test_df_integration_variable_in_condition_context():
    """End-to-end: a condition referencing trigger context gates dispatch."""
    world = FakeWorld()
    try:
        world.add_template({
            "id": "cond-trigger",
            "name": "Cond trigger",
            "nodes": [
                {"id": "work", "profile": "qa", "skill": "live-testing",
                 "body_template": "work",
                 "condition": "${trigger.spec_path} exists"},
            ],
        })
        # With spec_path present → work dispatches
        world.start("cond-trigger", context={"spec_path": "/tmp/spec.md"})
        actions = world.tick()
        assert any("work" in a and "DISPATCHED" in a for a in actions), \
            f"work should dispatch when trigger.spec_path exists, got: {actions}"
    finally:
        world.cleanup()
    print("OK: test_df_integration_variable_in_condition_context")


def test_df_integration_condition_absent_trigger_context():
    """End-to-end: a condition referencing absent trigger context blocks dispatch."""
    world = FakeWorld()
    try:
        world.add_template({
            "id": "cond-trigger-absent",
            "name": "Cond trigger absent",
            "nodes": [
                {"id": "work", "profile": "qa", "skill": "live-testing",
                 "body_template": "work",
                 "condition": "${trigger.spec_path} exists"},
            ],
        })
        # Without spec_path → work does NOT dispatch
        world.start("cond-trigger-absent", context={})
        actions = world.tick()
        assert not any("work" in a and "DISPATCHED" in a for a in actions), \
            f"work should NOT dispatch when trigger.spec_path absent, got: {actions}"
        assert world.count_cards() == 0
    finally:
        world.cleanup()
    print("OK: test_df_integration_condition_absent_trigger_context")


# ═══════════════════════════════════════════════════════════════════════════
# TEST RUNNER
# ═══════════════════════════════════════════════════════════════════════════

ALL_TESTS = [
    # Unit tests — typed value resolution
    test_df_resolve_dict_value,
    test_df_resolve_list_value,
    test_df_resolve_list_of_dicts,
    test_df_resolve_none_value,
    test_df_resolve_none_absent_key,
    test_df_resolve_bool_true,
    test_df_resolve_bool_false,
    test_df_resolve_int_value,
    test_df_resolve_float_value,
    test_df_resolve_zero_and_empty_string,
    # Circular refs (unit)
    test_df_resolve_circular_references_unit,
    # Dotted keys (unit)
    test_df_resolve_dotted_key_in_name,
    test_df_resolve_dotted_key_with_dashes,
    # Non-existent references (unit)
    test_df_resolve_nonexistent_node,
    test_df_resolve_nonexistent_output_key,
    # Multiple variables (unit)
    test_df_resolve_multiple_variables,
    test_df_resolve_repeated_variable,
    test_df_resolve_partial_mixed,
    # Recursive expansion (unit)
    test_df_resolve_recursive_expansion,
    test_df_resolve_recursive_expansion_reverse_order,
    test_df_resolve_recursive_no_target,
    # Empty / spaced variables (unit)
    test_df_resolve_empty_variable_no_context,
    test_df_resolve_empty_variable_empty_context_key,
    test_df_resolve_variable_with_spaces,
    test_df_resolve_variable_with_spaces_exact_key,
    # Condition edge cases (unit)
    test_df_condition_trigger_context_exists,
    test_df_condition_with_regex_chars,
    test_df_condition_inequality,
    test_df_condition_is_empty,
    test_df_condition_bool_value,
    test_df_condition_none_value,
    test_df_condition_malformed,
    # Escaped / literal (unit)
    test_df_resolve_literal_dollar_brace_not_variable,
    test_df_resolve_unmatched_brace,
    # Long / unicode (unit)
    test_df_resolve_very_long_string,
    test_df_resolve_unicode_value,
    test_df_resolve_unicode_key,
    # Nested metadata (unit)
    test_df_resolve_deeply_nested_dict_metadata,
    test_df_resolve_deeply_nested_list_metadata,
    # Integration tests — full tick loop
    test_df_integration_dict_output_flows_to_body,
    test_df_integration_list_output_flows_to_body,
    test_df_integration_none_output_flows_as_string,
    test_df_integration_bool_output_flows_as_python_str,
    test_df_integration_nonexistent_output_key_is_empty,
    test_df_integration_nonexistent_node_reference,
    test_df_integration_multiple_variables_one_body,
    test_df_integration_trigger_context_variable,
    test_df_integration_empty_variable_in_body,
    test_df_integration_unicode_output_flows,
    test_df_integration_long_string_output,
    test_df_integration_deeply_nested_metadata_output,
    test_df_integration_title_not_resolved,
    test_df_integration_condition_gates_dispatch_on_output_value,
    test_df_integration_condition_with_none_output,
    test_df_integration_output_persists_in_state_db,
    test_df_integration_circular_template_references,
    test_df_integration_dotted_output_key_flows,
    test_df_integration_output_mutation_between_ticks,
    test_df_integration_output_read_on_completion_tick,
    test_df_integration_adjacent_variables,
    test_df_integration_variable_in_condition_context,
    test_df_integration_condition_absent_trigger_context,
]


if __name__ == "__main__":
    passed = 0
    failed = 0
    for test in ALL_TESTS:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"FAIL: {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR: {test.__name__}: {type(e).__name__}: {e}")
            failed += 1

    print(f"\n{'='*60}")
    print(f"Dataflow test results: {passed} passed, {failed} failed, {len(ALL_TESTS)} total")
    if failed == 0:
        print("ALL DATAFLOW TESTS PASSED")
    else:
        print(f"{failed} TEST(S) FAILED")
    sys.exit(0 if failed == 0 else 1)
