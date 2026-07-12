#!/usr/bin/env python3
"""
Test suite for loop_engine — the loop-engineering control tool (T1 spine).

T1 = the "Plugin spine" slice: ONE phase, ONE iteration, execute-and-read.
These tests run WITHOUT a live kanban DB: they mock the kanban_db module the
handler imports via _kb(), and assert the EXACT sequence of API calls — the
same pattern as test_kanban_chains.py.

Coverage (the T1 acceptance criteria):
  1. Plugin registers a control tool (loop_engine) AND an observer hook
     (kanban_task_completed) — the first plugin to register both.
  2. First invocation inits `loop_state` on the root card's blackboard
     ([swarm:blackboard] comment, key=loop_state, with phase_index,
      iteration_counter, terminal_ids).
  3. First invocation creates ONE execution card parented on the root
     (create_task parents=[root]).
  4. First invocation dependency-parks the driver (link_tasks to the
     execution card + block_task kind="dependency").
  5. Re-invocation reads the execution card's result and stub-decides
     (T1 hard cap = 1 iteration -> report the result; no verifier/DoD).
"""

import json
import sys
import unittest
from collections import namedtuple
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

# -- Path setup -----------------------------------------------------------------
# Import loop_engine as a PACKAGE (parent dir on sys.path) so __init__.py's
# `from . import schemas, tools` resolves, and register() is callable. This
# mirrors how the real plugin loader imports plugins.
PLUGIN_DIR = Path(__file__).resolve().parent          # .../plugins/loop_engine
PLUGINS_DIR = PLUGIN_DIR.parent                        # .../plugins
sys.path.insert(0, str(PLUGINS_DIR))

import loop_engine as le_init          # package; __init__.py exposes register()
from loop_engine import tools as le_tools
from loop_engine import schemas as le_schemas


# =============================================================================
# Mock kanban_db
# =============================================================================

_Comment = namedtuple("_Comment", ["author", "body"])


@dataclass
class _FakeRun:
    """Minimal stand-in for hermes_cli.kanban_db.Run (the fields we read)."""
    id: int = 1
    task_id: str = ""
    summary: str = None
    metadata: dict = None
    outcome: str = "completed"


class FakeKanbanDB:
    """Records every kanban_db API call and returns canned responses.

    Mirrors the FakeKanbanDB in test_kanban_chains.py, extended with:
      * latest_run(conn, task_id)         — the re-invoke result read path
      * preseed_comments                  - {task_id: [_Comment, ...]} to plant
                                            board state (loop_state) for tests
      * run_for_task                      - {task_id: _FakeRun} for latest_run
    """

    def __init__(self, create_ids=None, block_result=True,
                 preseed_comments=None, run_for_task=None):
        self.create_ids = create_ids or []
        self.block_result = block_result
        self._create_idx = 0
        self.calls = []  # list of (method_name, args_tuple, kwargs_dict)
        self._comments = {}  # task_id -> list of _Comment (mutable blackboard)
        if preseed_comments:
            for tid, comments in preseed_comments.items():
                self._comments[tid] = list(comments)
        self.run_for_task = run_for_task or {}

    # -- context manager for connect_closing --

    def connect_closing(self, board=None):
        self.calls.append(("connect_closing", (), {"board": board}))
        return self

    def __enter__(self):
        return "fake_conn"

    def __exit__(self, *args):
        return False

    # -- kanban_db API methods --

    def create_task(self, conn, title=None, body=None, assignee=None,
                    created_by=None, parents=None, skills=None,
                    workspace_path=None, priority=0, idempotency_key=None,
                    initial_status="running"):
        kwargs = {
            "title": title,
            "body": body,
            "assignee": assignee,
            "created_by": created_by,
            "parents": parents,
            "skills": skills,
            "workspace_path": workspace_path,
            "priority": priority,
            "idempotency_key": idempotency_key,
            "initial_status": initial_status,
        }
        self.calls.append(("create_task", (conn,), kwargs))
        if self._create_idx < len(self.create_ids):
            tid = self.create_ids[self._create_idx]
            self._create_idx += 1
            return tid
        return f"t_fallback_{self._create_idx}"

    def add_comment(self, conn, task_id, author, text):
        self.calls.append(("add_comment", (conn, task_id, author, text), {}))
        self._comments.setdefault(task_id, []).append(_Comment(author, text))

    def list_comments(self, conn, task_id):
        self.calls.append(("list_comments", (conn, task_id), {}))
        return list(self._comments.get(task_id, []))

    def complete_task(self, conn, task_id, result=None, summary=None,
                      metadata=None):
        self.calls.append(("complete_task", (conn, task_id),
                           {"result": result, "summary": summary,
                            "metadata": metadata}))

    def link_tasks(self, conn, parent_id, child_id):
        self.calls.append(("link_tasks", (conn, parent_id, child_id), {}))

    def block_task(self, conn, task_id, reason=None, kind=None,
                   expected_run_id=None):
        self.calls.append(("block_task", (conn, task_id),
                           {"reason": reason, "kind": kind,
                            "expected_run_id": expected_run_id}))
        return self.block_result

    def latest_run(self, conn, task_id):
        self.calls.append(("latest_run", (conn, task_id), {}))
        return self.run_for_task.get(task_id)


# =============================================================================
# Test helpers
# =============================================================================

def _create_calls(fake):
    """Return list of kwargs dicts for every create_task call."""
    return [kw for (method, _, kw) in fake.calls if method == "create_task"]


def _calls(fake, method_name):
    """Return list of (args, kwargs) for every call matching method_name."""
    return [(args, kw) for (m, args, kw) in fake.calls if m == method_name]


def _execution(assignee="developer", title="build the thing",
               body="ship it", skill=None):
    step = {"assignee": assignee, "title": title, "body": body}
    if skill is not None:
        step["skill"] = skill
    return step


def _run_handler(args, create_ids, block_result=True, task_id="t_driver",
                 preseed_comments=None, run_for_task=None):
    """Convenience: run loop_engine with a FakeKanbanDB, return (parsed, fake)."""
    fake = FakeKanbanDB(create_ids=create_ids, block_result=block_result,
                        preseed_comments=preseed_comments,
                        run_for_task=run_for_task)
    with patch.object(le_tools, "_kb", return_value=fake):
        result = le_tools.loop_engine(args=args, task_id=task_id)
    return json.loads(result), fake


def _loop_state_comment(root_id, author="loop_engine", execution_card="t_exec",
                        iteration_counter=0):
    """Build a [swarm:blackboard] loop_state comment as the board would hold it."""
    payload = json.dumps({
        "key": "loop_state",
        "value": {
            "phase_index": 0,
            "iteration_counter": iteration_counter,
            "terminal_ids": [execution_card],
            "execution_card": execution_card,
        },
    })
    return _Comment(author, f"[swarm:blackboard] {payload}")


# =============================================================================
# 1. Schema
# =============================================================================

class TestSchema(unittest.TestCase):

    def test_schema_exists(self):
        self.assertTrue(hasattr(le_schemas, "LOOP_ENGINE"))

    def test_schema_name(self):
        self.assertEqual(le_schemas.LOOP_ENGINE["name"], "loop_engine")

    def test_required_goal_and_execution(self):
        required = le_schemas.LOOP_ENGINE["parameters"]["required"]
        self.assertIn("goal", required)
        self.assertIn("execution", required)

    def test_execution_step_required_fields(self):
        step = le_schemas.LOOP_ENGINE["parameters"]["properties"]["execution"]
        self.assertEqual(set(step["required"]), {"assignee", "title", "body"})


# =============================================================================
# 2. Plugin registration — registers BOTH a tool and a hook
# =============================================================================

class _RecordingCtx:
    """Stand-in PluginContext that records register_tool/register_hook calls."""

    def __init__(self):
        self.tools = []
        self.hooks = []

    def register_tool(self, name=None, toolset=None, schema=None,
                      handler=None, **kw):
        self.tools.append({
            "name": name, "toolset": toolset, "schema": schema,
            "handler": handler,
        })

    def register_hook(self, hook_name=None, callback=None, **kw):
        self.hooks.append({"hook_name": hook_name, "callback": callback})


class TestRegistration(unittest.TestCase):

    def test_registers_loop_engine_tool(self):
        ctx = _RecordingCtx()
        le_init.register(ctx)
        self.assertEqual(len(ctx.tools), 1)
        self.assertEqual(ctx.tools[0]["name"], "loop_engine")
        self.assertEqual(ctx.tools[0]["schema"], le_schemas.LOOP_ENGINE)
        self.assertTrue(callable(ctx.tools[0]["handler"]))

    def test_registers_kanban_task_completed_hook(self):
        ctx = _RecordingCtx()
        le_init.register(ctx)
        # First plugin to register BOTH a tool and a hook.
        self.assertEqual(len(ctx.tools), 1)
        self.assertGreaterEqual(len(ctx.hooks), 1)
        hook_names = [h["hook_name"] for h in ctx.hooks]
        self.assertIn("kanban_task_completed", hook_names)
        # Hooks are observer-only: the callback must be callable.
        for h in ctx.hooks:
            self.assertTrue(callable(h["callback"]))

    def test_plugin_yaml_lists_tool_and_hook(self):
        src = (PLUGIN_DIR / "plugin.yaml").read_text()
        self.assertRegex(src, r"name:\s*loop_engine")
        self.assertIn("- loop_engine", src)
        self.assertIn("kanban_task_completed", src)


# =============================================================================
# 3. First invocation — init loop_state + create one execution card on root
# =============================================================================

class TestFirstInvocation(unittest.TestCase):

    def test_inits_loop_state_on_root(self):
        parsed, fake = _run_handler(
            args={"goal": "debug the flake", "execution": _execution()},
            create_ids=["t_root", "t_exec"],
        )
        # A [swarm:blackboard] comment with key=loop_state lands on the root.
        state_comments = []
        for (args, _kw) in _calls(fake, "add_comment"):
            _conn, tid, _author, text = args
            if tid != "t_root" or not text.startswith("[swarm:blackboard]"):
                continue
            payload = json.loads(text[len("[swarm:blackboard] "):])
            if payload.get("key") == "loop_state":
                state_comments.append(payload["value"])
        self.assertEqual(len(state_comments), 1,
                         "first invocation must init exactly one loop_state")
        state = state_comments[0]
        self.assertEqual(state["phase_index"], 0)
        self.assertEqual(state["iteration_counter"], 0)
        self.assertEqual(state["terminal_ids"], ["t_exec"])

    def test_creates_root_then_one_execution_card_parented_on_root(self):
        parsed, fake = _run_handler(
            args={"goal": "debug the flake", "execution": _execution()},
            create_ids=["t_root", "t_exec"],
        )
        creates = _create_calls(fake)
        self.assertEqual(len(creates), 2, "T1 spine: root + ONE execution card")

        # Root created first, then the single execution card parented on it.
        self.assertIsNone(creates[0]["parents"])  # root has no parents
        self.assertEqual(creates[1]["parents"], ["t_root"])
        self.assertEqual(parsed["root_id"], "t_root")
        self.assertEqual(parsed["execution_card"], "t_exec")

    def test_root_completed_so_execution_card_can_promote(self):
        parsed, fake = _run_handler(
            args={"goal": "debug the flake", "execution": _execution()},
            create_ids=["t_root", "t_exec"],
        )
        completes = _calls(fake, "complete_task")
        root_completes = [c for c in completes if c[0][1] == "t_root"]
        self.assertEqual(len(root_completes), 1,
                         "root must be completed so its child can promote")

    def test_returns_blocked_status(self):
        parsed, fake = _run_handler(
            args={"goal": "debug the flake", "execution": _execution()},
            create_ids=["t_root", "t_exec"],
        )
        self.assertEqual(parsed["status"], "blocked")
        self.assertEqual(parsed["terminal_ids"], ["t_exec"])


# =============================================================================
# 4. First invocation — dependency-park the driver
# =============================================================================

class TestDependencyPark(unittest.TestCase):

    def test_links_driver_to_execution_card(self):
        parsed, fake = _run_handler(
            args={"goal": "debug the flake", "execution": _execution()},
            create_ids=["t_root", "t_exec"],
            task_id="t_driver",
        )
        links = _calls(fake, "link_tasks")
        self.assertEqual(len(links), 1)
        _conn, parent_id, child_id = links[0][0]
        self.assertEqual(parent_id, "t_exec")    # execution card is the parent
        self.assertEqual(child_id, "t_driver")   # driver becomes the child

    def test_blocks_driver_as_dependency(self):
        parsed, fake = _run_handler(
            args={"goal": "debug the flake", "execution": _execution()},
            create_ids=["t_root", "t_exec"],
            task_id="t_driver",
        )
        blocks = _calls(fake, "block_task")
        self.assertEqual(len(blocks), 1)
        _conn, task_id = blocks[0][0]
        block_kw = blocks[0][1]
        self.assertEqual(task_id, "t_driver")
        self.assertEqual(block_kw["kind"], "dependency")
        # dependency-park must NOT trip block_recurrences: only kind=dependency
        # routes to todo without touching the recurrence counter.
        self.assertIn("t_exec", block_kw["reason"])

    def test_block_failure_returns_error(self):
        parsed, fake = _run_handler(
            args={"goal": "debug the flake", "execution": _execution()},
            create_ids=["t_root", "t_exec"],
            block_result=False,
        )
        self.assertIn("error", parsed)
        self.assertIn("Block failed", parsed["error"])


# =============================================================================
# 5. Re-invocation — read the execution result and stub-decide
#     T1 hard cap = 1 iteration: report the result, no verifier/DoD.
# =============================================================================

class TestReinvokeStubDecide(unittest.TestCase):

    def test_reads_execution_result_via_latest_run(self):
        # Board already carries loop_state (first invocation already happened)
        # and the execution card is done with a summary.
        seeded = _loop_state_comment("t_root", execution_card="t_exec",
                                     iteration_counter=0)
        run = _FakeRun(task_id="t_exec", summary="tests green; root cause fixed",
                       metadata={"tests_passed": 12}, outcome="completed")
        parsed, fake = _run_handler(
            args={"goal": "debug the flake", "execution": _execution()},
            create_ids=["t_root"],  # root resolved idempotently; no new exec card
            preseed_comments={"t_root": [seeded]},
            run_for_task={"t_exec": run},
        )
        # The handler read the execution card's run for its result.
        latest = _calls(fake, "latest_run")
        self.assertEqual(len(latest), 1)
        self.assertEqual(latest[0][0][1], "t_exec")

    def test_stub_decides_complete_at_hard_cap_one(self):
        seeded = _loop_state_comment("t_root", execution_card="t_exec",
                                     iteration_counter=0)
        run = _FakeRun(task_id="t_exec", summary="tests green; root cause fixed",
                       metadata={"tests_passed": 12}, outcome="completed")
        parsed, fake = _run_handler(
            args={"goal": "debug the flake", "execution": _execution()},
            create_ids=["t_root"],
            preseed_comments={"t_root": [seeded]},
            run_for_task={"t_exec": run},
        )
        # T1 hard cap = 1: one execution -> report result, terminate.
        self.assertEqual(parsed["status"], "complete")
        self.assertEqual(parsed["iteration"], 1)
        self.assertEqual(parsed["decision"], "hard_cap_reached")
        # The execution card's structured result flows back to the caller.
        self.assertEqual(parsed["result"]["outcome"], "completed")
        self.assertEqual(parsed["result"]["metadata"], {"tests_passed": 12})
        self.assertIn("tests green", parsed["result"]["summary"])

    def test_reinvoke_does_not_rebuild_execution_card(self):
        seeded = _loop_state_comment("t_root", execution_card="t_exec",
                                     iteration_counter=0)
        run = _FakeRun(task_id="t_exec", summary="done")
        parsed, fake = _run_handler(
            args={"goal": "debug the flake", "execution": _execution()},
            create_ids=["t_root"],
            preseed_comments={"t_root": [seeded]},
            run_for_task={"t_exec": run},
        )
        creates = _create_calls(fake)
        # Only the root (resolved idempotently) — no second execution card.
        self.assertEqual(len(creates), 1)
        self.assertIsNone(creates[0]["parents"])


# =============================================================================
# 6. Observer hook is a harmless no-op telemetry stub
# =============================================================================

class TestObserverHook(unittest.TestCase):

    def test_hook_callback_runs_without_error(self):
        ctx = _RecordingCtx()
        le_init.register(ctx)
        cb = next(h["callback"] for h in ctx.hooks
                  if h["hook_name"] == "kanban_task_completed")
        # Observer-only: any kwargs the dispatcher passes must be tolerated,
        # and the return value is ignored by the host.
        cb(task_id="t_exec", board="team", assignee="developer",
           run_id=42, profile_name="developer", summary="done")


# =============================================================================
# 7. Validation + compile check
# =============================================================================

class TestValidation(unittest.TestCase):

    def test_missing_task_id_returns_error(self):
        fake = FakeKanbanDB(create_ids=["t_root", "t_exec"])
        with patch.object(le_tools, "_kb", return_value=fake):
            result = le_tools.loop_engine(
                args={"goal": "x", "execution": _execution()})
        parsed = json.loads(result)
        self.assertIn("error", parsed)

    def test_missing_goal_returns_error_without_db_calls(self):
        fake = FakeKanbanDB(create_ids=[])
        with patch.object(le_tools, "_kb", return_value=fake):
            result = le_tools.loop_engine(
                args={"execution": _execution()}, task_id="t_driver")
        parsed = json.loads(result)
        self.assertIn("error", parsed)
        self.assertEqual(fake.calls, [],
                         "validation must not call kanban_db at all")


class TestCompileCheck(unittest.TestCase):

    def test_tools_py_compiles(self):
        import py_compile
        py_compile.compile(str(PLUGIN_DIR / "tools.py"), doraise=True)

    def test_schemas_py_compiles(self):
        import py_compile
        py_compile.compile(str(PLUGIN_DIR / "schemas.py"), doraise=True)

    def test_init_py_compiles(self):
        import py_compile
        py_compile.compile(str(PLUGIN_DIR / "__init__.py"), doraise=True)


# =============================================================================
# Runner
# =============================================================================

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    test_classes = [
        TestSchema,
        TestRegistration,
        TestFirstInvocation,
        TestDependencyPark,
        TestReinvokeStubDecide,
        TestObserverHook,
        TestValidation,
        TestCompileCheck,
    ]

    for cls in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    passed = result.testsRun - len(result.failures) - len(result.errors)
    print(f"\n{'='*60}")
    print(f"  {passed} passed, {len(result.failures)} failed, "
          f"{len(result.errors)} errors, {result.testsRun} total")
    print(f"{'='*60}")

    sys.exit(0 if result.wasSuccessful() else 1)
