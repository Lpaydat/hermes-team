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
        self._idem = {}  # idempotency_key -> task_id (mirrors the DB's UNIQUE index)

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
        # Idempotent re-create: return the same task id WITHOUT consuming a new
        # one (mirrors the DB's idempotency_key UNIQUE index). This lets a single
        # FakeKanbanDB instance be reused across multiple handler invocations in
        # the converge-loop test, exactly as the durable board dedups root cards.
        if idempotency_key is not None and idempotency_key in self._idem:
            return self._idem[idempotency_key]
        if self._create_idx < len(self.create_ids):
            tid = self.create_ids[self._create_idx]
            self._create_idx += 1
        else:
            tid = f"t_fallback_{self._create_idx}"
        if idempotency_key is not None:
            self._idem[idempotency_key] = tid
        return tid

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

    def _append_event(self, conn, task_id, kind, payload=None, *, run_id=None):
        # Records the event-emission seam (T4 HITL escalation). Mirrors the real
        # kanban_db._append_event signature: (conn, task_id, kind, payload, *, run_id).
        self.calls.append(("_append_event",
                           (conn, task_id, kind, payload),
                           {"run_id": run_id}))


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


# -- T2 (verifier-gated) helpers -------------------------------------------------

def _execution_t2(assignee="developer", title="build the thing",
                  body="ship it", skill=None):
    """Same shape as _execution; named for readability in T2 tests."""
    return _execution(assignee=assignee, title=title, body=body, skill=skill)


def _verifier(assignee="verifier", title="verify the thing",
              body="DoD: tests pass; no regressions. Write dod_verdict.",
              skill=None):
    step = {"assignee": assignee, "title": title, "body": body}
    if skill is not None:
        step["skill"] = skill
    return step


def _dod_verdict(dod_met=False, score=None, gaps=None,
                 recommendation=None):
    """Build a structured dod_verdict as the verifier writes it.

    recommendation defaults to "advance"/"replan" to match dod_met when not
    given, so tests only assert on the axis they care about.
    """
    if recommendation is None:
        recommendation = "advance" if dod_met else "replan"
    verdict = {"dod_met": dod_met, "recommendation": recommendation}
    if score is not None:
        verdict["score"] = score
    verdict["gaps"] = gaps if gaps is not None else ([] if dod_met
                                                     else [{"dimension": "tests",
                                                            "issue": "still failing"}])
    return verdict


def _verifier_run(verdict, summary="verified",
                  task_id="t_verifier"):
    """A _FakeRun whose metadata carries a dod_verdict (the verifier's handoff)."""
    return _FakeRun(task_id=task_id, summary=summary,
                    metadata={"dod_verdict": verdict}, outcome="completed")


def _loop_state_comment_verifier(root_id, execution_card="t_exec",
                                 verifier_card="t_verifier",
                                 iteration_counter=1, max_iterations=5):
    """T2 loop_state: driver parked on the verifier (terminal parent)."""
    payload = json.dumps({
        "key": "loop_state",
        "value": {
            "phase_index": 0,
            "iteration_counter": iteration_counter,
            "terminal_ids": [verifier_card],
            "execution_card": execution_card,
            "verifier_card": verifier_card,
            "max_iterations": max_iterations,
        },
    })
    return _Comment("loop_engine", f"[swarm:blackboard] {payload}")


def _run_with_fake(fake, args, task_id="t_driver"):
    """Run loop_engine against an EXISTING FakeKanbanDB (reused across calls).

    Unlike _run_handler, this does NOT construct a fresh fake — so the mutable
    blackboard (_comments) and idempotency index (_idem) persist between
    invocations, mirroring the durable board. Used by the converge-loop test.
    """
    with patch.object(le_tools, "_kb", return_value=fake):
        result = le_tools.loop_engine(args=args, task_id=task_id)
    return json.loads(result), fake


def _create_calls_new(fake):
    """create_task calls that actually minted a NEW card (idempotent root
    re-creates excluded) — i.e. the execution + verifier cards the engine
    dispatched. Filters on cards that have parents (root has none)."""
    return [kw for (method, _, kw) in fake.calls
            if method == "create_task" and kw.get("parents")]


# -- T3 (multi-phase) helpers --------------------------------------------------

def _last_loop_state(fake, root_id):
    """Return the last loop_state value written on root's blackboard, or None."""
    states = []
    for (args, _kw) in _calls(fake, "add_comment"):
        _conn, tid, _author, text = args
        if tid != root_id or not text.startswith("[swarm:blackboard]"):
            continue
        try:
            payload = json.loads(text[len("[swarm:blackboard] "):])
        except (ValueError, TypeError):
            continue
        if payload.get("key") == "loop_state":
            states.append(payload["value"])
    return states[-1] if states else None


def _phases(n=2, with_verifier=True):
    """Build n ordered phases, each with execution + optional verifier (DoD)."""
    result = []
    for i in range(n):
        phase = {
            "execution": _execution(
                assignee="developer",
                title=f"phase {i}: build",
                body=f"phase {i} work"),
        }
        if with_verifier:
            phase["verifier"] = _verifier(
                assignee="verifier",
                title=f"phase {i}: verify",
                body=f"phase {i} DoD: tests pass. Write dod_verdict.")
        result.append(phase)
    return result


def _loop_state_comment_phases(root_id, phases, phase_index=0,
                               execution_card="t_exec",
                               verifier_card="t_verifier",
                               iteration_counter=1, max_iterations=5):
    """T3 multi-phase loop_state: driver parked on a phase's verifier."""
    value = {
        "phase_index": phase_index,
        "phases": phases,
        "iteration_counter": iteration_counter,
        "terminal_ids": [verifier_card],
        "execution_card": execution_card,
        "verifier_card": verifier_card,
        "max_iterations": max_iterations,
    }
    payload = json.dumps({"key": "loop_state", "value": value})
    return _Comment("loop_engine", f"[swarm:blackboard] {payload}")


# -- T4 (layered exits + HITL escalation) helpers ------------------------------

def _blocks_with_kind(fake, kind):
    """Return kwargs dicts for every block_task call matching `kind`."""
    return [kw for (_a, kw) in _calls(fake, "block_task") if kw.get("kind") == kind]


def _events(fake, kind):
    """Return (args, kwargs) for every _append_event call whose event kind matches."""
    return [(args, kw) for (m, args, kw) in fake.calls
            if m == "_append_event" and args[2] == kind]


def _loop_state_comment_budget(root_id, execution_card="t_exec",
                               verifier_card="t_verifier",
                               iteration_counter=1, max_iterations=10,
                               budget=2, no_progress_threshold=2):
    """T4 loop_state pre-seeded with budget + no-progress tracking fields."""
    payload = json.dumps({
        "key": "loop_state",
        "value": {
            "phase_index": 0,
            "iteration_counter": iteration_counter,
            "terminal_ids": [verifier_card],
            "execution_card": execution_card,
            "verifier_card": verifier_card,
            "max_iterations": max_iterations,
            "budget": budget,
            "iteration_cost": 1,
            "no_progress_threshold": no_progress_threshold,
            "exit_counters": {
                "hard_cap": 0,
                "budget_remaining": budget,
                "no_progress_streak": 0,
            },
            "last_state_hash": None,
        },
    })
    return _Comment("loop_engine", f"[swarm:blackboard] {payload}")


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

    def test_schema_has_t4_layered_exit_properties(self):
        props = le_schemas.LOOP_ENGINE["parameters"]["properties"]
        self.assertIn("budget", props)
        self.assertEqual(props["budget"]["type"], "integer")
        self.assertIn("no_progress_threshold", props)
        self.assertEqual(props["no_progress_threshold"]["type"], "integer")


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

    def test_invalid_budget_rejected(self):
        fake = FakeKanbanDB(create_ids=[])
        with patch.object(le_tools, "_kb", return_value=fake):
            result = le_tools.loop_engine(
                args={"goal": "x", "execution": _execution(),
                      "budget": 0}, task_id="t_driver")
        parsed = json.loads(result)
        self.assertIn("error", parsed)
        self.assertIn("budget", parsed["error"])

    def test_invalid_no_progress_threshold_rejected(self):
        fake = FakeKanbanDB(create_ids=[])
        with patch.object(le_tools, "_kb", return_value=fake):
            result = le_tools.loop_engine(
                args={"goal": "x", "execution": _execution(),
                      "no_progress_threshold": 0}, task_id="t_driver")
        parsed = json.loads(result)
        self.assertIn("error", parsed)
        self.assertIn("no_progress_threshold", parsed["error"])


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
# 8. T2 — verifier card dispatched as terminal parent of driver
#     (gated: only when `verifier` is supplied. T1 tests above omit it and so
#      exercise the unchanged execute-and-read path.)
# =============================================================================

class TestVerifierDispatch(unittest.TestCase):

    def test_first_invocation_creates_verifier_card_parented_on_execution(self):
        parsed, fake = _run_handler(
            args={"goal": "fix the bug",
                  "execution": _execution_t2(),
                  "verifier": _verifier(),
                  "max_iterations": 3},
            create_ids=["t_root", "t_exec", "t_verifier"],
        )
        creates = _create_calls(fake)
        # Three cards: root, execution (parent=root), verifier (parent=exec).
        self.assertEqual(len(creates), 3)
        self.assertIsNone(creates[0]["parents"])           # root
        self.assertEqual(creates[1]["parents"], ["t_root"])  # execution on root
        self.assertEqual(creates[2]["parents"], ["t_exec"])  # verifier on exec
        # The verifier card is surfaced so the caller can track it.
        self.assertEqual(parsed["verifier_card"], "t_verifier")

    def test_verifier_card_carries_assignee_title_body(self):
        parsed, fake = _run_handler(
            args={"goal": "fix the bug",
                  "execution": _execution_t2(),
                  "verifier": _verifier(assignee="verifier",
                                        title="Verify: fix",
                                        body="DoD: green; write dod_verdict")},
            create_ids=["t_root", "t_exec", "t_verifier"],
        )
        creates = _create_calls(fake)
        v_create = creates[2]
        self.assertEqual(v_create["assignee"], "verifier")
        self.assertEqual(v_create["title"], "Verify: fix")
        self.assertIn("dod_verdict", v_create["body"])

    def test_driver_parks_on_verifier_as_terminal_parent(self):
        parsed, fake = _run_handler(
            args={"goal": "fix the bug",
                  "execution": _execution_t2(),
                  "verifier": _verifier()},
            create_ids=["t_root", "t_exec", "t_verifier"],
            task_id="t_driver",
        )
        # The driver is linked to the VERIFIER (not the execution card).
        links = _calls(fake, "link_tasks")
        self.assertEqual(len(links), 1)
        _conn, parent_id, child_id = links[0][0]
        self.assertEqual(parent_id, "t_verifier")
        self.assertEqual(child_id, "t_driver")
        # And dependency-blocked on the verifier (terminal parent).
        blocks = _calls(fake, "block_task")
        self.assertEqual(len(blocks), 1)
        _conn, tid = blocks[0][0]
        self.assertEqual(tid, "t_driver")
        self.assertEqual(blocks[0][1]["kind"], "dependency")
        self.assertIn("t_verifier", blocks[0][1]["reason"])

    def test_loop_state_records_verifier_as_terminal(self):
        parsed, fake = _run_handler(
            args={"goal": "fix the bug",
                  "execution": _execution_t2(),
                  "verifier": _verifier(),
                  "max_iterations": 3},
            create_ids=["t_root", "t_exec", "t_verifier"],
        )
        state_comments = []
        for (args, _kw) in _calls(fake, "add_comment"):
            _conn, tid, _author, text = args
            if tid != "t_root" or not text.startswith("[swarm:blackboard]"):
                continue
            payload = json.loads(text[len("[swarm:blackboard] "):])
            if payload.get("key") == "loop_state":
                state_comments.append(payload["value"])
        self.assertEqual(len(state_comments), 1)
        state = state_comments[0]
        self.assertEqual(state["terminal_ids"], ["t_verifier"])
        self.assertEqual(state["verifier_card"], "t_verifier")
        self.assertEqual(state["execution_card"], "t_exec")
        self.assertEqual(state["iteration_counter"], 1)
        self.assertEqual(state["max_iterations"], 3)

    def test_first_invocation_returns_blocked_with_verifier(self):
        parsed, fake = _run_handler(
            args={"goal": "fix the bug",
                  "execution": _execution_t2(),
                  "verifier": _verifier()},
            create_ids=["t_root", "t_exec", "t_verifier"],
        )
        self.assertEqual(parsed["status"], "blocked")
        self.assertEqual(parsed["terminal_ids"], ["t_verifier"])
        self.assertEqual(parsed["iteration"], 1)


# =============================================================================
# 9. T2 — driver reads the verifier's dod_verdict on promotion + decides advance
# =============================================================================

class TestDoDVerdictRead(unittest.TestCase):

    def test_reinvoke_reads_verifier_verdict_via_latest_run(self):
        seeded = _loop_state_comment_verifier(
            "t_root", execution_card="t_exec", verifier_card="t_verifier",
            iteration_counter=1)
        verdict = _dod_verdict(dod_met=True)
        parsed, fake = _run_handler(
            args={"goal": "fix the bug",
                  "execution": _execution_t2(),
                  "verifier": _verifier()},
            create_ids=["t_root"],
            preseed_comments={"t_root": [seeded]},
            run_for_task={"t_verifier": _verifier_run(verdict)},
        )
        # The driver read the VERIFIER's closing run for the verdict.
        latest = _calls(fake, "latest_run")
        self.assertEqual(len(latest), 1)
        self.assertEqual(latest[0][0][1], "t_verifier")

    def test_dod_met_advances_to_complete(self):
        seeded = _loop_state_comment_verifier(
            "t_root", execution_card="t_exec", verifier_card="t_verifier",
            iteration_counter=1)
        verdict = _dod_verdict(dod_met=True, score=1.0,
                               recommendation="advance")
        parsed, fake = _run_handler(
            args={"goal": "fix the bug",
                  "execution": _execution_t2(),
                  "verifier": _verifier()},
            create_ids=["t_root"],
            preseed_comments={"t_root": [seeded]},
            run_for_task={"t_verifier": _verifier_run(verdict)},
        )
        self.assertEqual(parsed["status"], "complete")
        self.assertEqual(parsed["decision"], "advance")
        self.assertEqual(parsed["iteration"], 1)
        self.assertTrue(parsed["verdict"]["dod_met"])

    def test_dod_met_via_recommendation_advance_only(self):
        # dod_met missing but recommendation=advance still advances.
        seeded = _loop_state_comment_verifier(
            "t_root", verifier_card="t_verifier", iteration_counter=1)
        verdict = {"recommendation": "advance", "gaps": []}
        parsed, fake = _run_handler(
            args={"goal": "x", "execution": _execution_t2(),
                  "verifier": _verifier()},
            create_ids=["t_root"],
            preseed_comments={"t_root": [seeded]},
            run_for_task={"t_verifier":
                          _verifier_run(verdict)},
        )
        self.assertEqual(parsed["status"], "complete")
        self.assertEqual(parsed["decision"], "advance")

    def test_no_verdict_when_verifier_run_missing(self):
        # Verifier never completed (no run) -> treat as not-met, replan under cap.
        seeded = _loop_state_comment_verifier(
            "t_root", verifier_card="t_verifier", iteration_counter=1,
            max_iterations=3)
        parsed, fake = _run_handler(
            args={"goal": "x", "execution": _execution_t2(),
                  "verifier": _verifier()},
            create_ids=["t_root", "t_exec2", "t_verifier2"],
            preseed_comments={"t_root": [seeded]},
            run_for_task={},  # no verifier run
        )
        # No verdict -> not met -> replan (under cap).
        self.assertEqual(parsed["status"], "blocked")
        self.assertEqual(parsed["decision"], "replan")


# =============================================================================
# 10. T2 — replan (dod_met=false, under cap) dispatches fresh execution + verifier
# =============================================================================

class TestReplan(unittest.TestCase):

    def test_replan_creates_fresh_execution_and_verifier(self):
        seeded = _loop_state_comment_verifier(
            "t_root", execution_card="t_exec", verifier_card="t_verifier",
            iteration_counter=1, max_iterations=3)
        verdict = _dod_verdict(dod_met=False, recommendation="replan")
        parsed, fake = _run_handler(
            args={"goal": "fix the bug",
                  "execution": _execution_t2(),
                  "verifier": _verifier()},
            create_ids=["t_root", "t_exec2", "t_verifier2"],
            preseed_comments={"t_root": [seeded]},
            run_for_task={"t_verifier": _verifier_run(verdict)},
        )
        self.assertEqual(parsed["status"], "blocked")
        self.assertEqual(parsed["decision"], "replan")
        self.assertEqual(parsed["iteration"], 2)
        # A fresh execution card and a fresh verifier card were dispatched.
        new_cards = _create_calls_new(fake)
        self.assertEqual(len(new_cards), 2)
        self.assertEqual(new_cards[0]["parents"], ["t_root"])     # exec on root
        self.assertEqual(new_cards[1]["parents"], ["t_exec2"])    # verifier on exec

    def test_replan_parks_driver_on_new_verifier(self):
        seeded = _loop_state_comment_verifier(
            "t_root", execution_card="t_exec", verifier_card="t_verifier",
            iteration_counter=1, max_iterations=3)
        verdict = _dod_verdict(dod_met=False, recommendation="replan")
        parsed, fake = _run_handler(
            args={"goal": "fix the bug",
                  "execution": _execution_t2(),
                  "verifier": _verifier()},
            create_ids=["t_root", "t_exec2", "t_verifier2"],
            preseed_comments={"t_root": [seeded]},
            run_for_task={"t_verifier": _verifier_run(verdict)},
            task_id="t_driver",
        )
        links = _calls(fake, "link_tasks")
        _conn, parent_id, child_id = links[-1][0]
        self.assertEqual(parent_id, "t_verifier2")
        self.assertEqual(child_id, "t_driver")
        blocks = _calls(fake, "block_task")
        self.assertEqual(blocks[-1][1]["kind"], "dependency")
        self.assertIn("t_verifier2", blocks[-1][1]["reason"])

    def test_replan_persists_advanced_iteration_counter(self):
        seeded = _loop_state_comment_verifier(
            "t_root", execution_card="t_exec", verifier_card="t_verifier",
            iteration_counter=1, max_iterations=3)
        verdict = _dod_verdict(dod_met=False, recommendation="replan")
        parsed, fake = _run_handler(
            args={"goal": "fix the bug",
                  "execution": _execution_t2(),
                  "verifier": _verifier()},
            create_ids=["t_root", "t_exec2", "t_verifier2"],
            preseed_comments={"t_root": [seeded]},
            run_for_task={"t_verifier": _verifier_run(verdict)},
        )
        # The advanced loop_state is the last loop_state write on the root.
        state_writes = []
        for (args, _kw) in _calls(fake, "add_comment"):
            _conn, tid, _author, text = args
            if tid != "t_root" or not text.startswith("[swarm:blackboard]"):
                continue
            payload = json.loads(text[len("[swarm:blackboard] "):])
            if payload.get("key") == "loop_state":
                state_writes.append(payload["value"])
        self.assertEqual(state_writes[-1]["iteration_counter"], 2)
        self.assertEqual(state_writes[-1]["verifier_card"], "t_verifier2")
        self.assertEqual(state_writes[-1]["terminal_ids"], ["t_verifier2"])


# =============================================================================
# 11. T2 — converge loop: 2 replans then advance (single shared fake, multi-invocation)
# =============================================================================

class TestConvergeLoop(unittest.TestCase):

    def test_two_replans_then_advance_converges(self):
        """Drive a 3-iteration converge loop by re-invoking the handler against
        ONE stateful fake (blackboard + idempotency persist between calls).

        Iteration 1 -> replan, iteration 2 -> replan, iteration 3 -> advance.
        """
        args = {"goal": "fix the flake",
                "execution": _execution_t2(),
                "verifier": _verifier(),
                "max_iterations": 5}
        fake = FakeKanbanDB(create_ids=[
            "t_root", "t_exec1", "t_verifier1",
            "t_exec2", "t_verifier2",
            "t_exec3", "t_verifier3",
        ], run_for_task={
            "t_verifier1": _verifier_run(_dod_verdict(
                dod_met=False, recommendation="replan",
                gaps=[{"dimension": "a", "issue": "1"}])),
            "t_verifier2": _verifier_run(_dod_verdict(
                dod_met=False, recommendation="replan",
                gaps=[{"dimension": "b", "issue": "2"}])),
            "t_verifier3": _verifier_run(_dod_verdict(
                dod_met=True, recommendation="advance")),
        })

        # Invocation 1 — first: dispatch root + exec1 + verifier1, park.
        p1, _ = _run_with_fake(fake, args)
        self.assertEqual(p1["status"], "blocked")
        self.assertEqual(p1["iteration"], 1)

        # Invocation 2 — verifier1 said replan: dispatch exec2 + verifier2, park.
        p2, _ = _run_with_fake(fake, args)
        self.assertEqual(p2["status"], "blocked")
        self.assertEqual(p2["decision"], "replan")
        self.assertEqual(p2["iteration"], 2)

        # Invocation 3 — verifier2 said replan: dispatch exec3 + verifier3, park.
        p3, _ = _run_with_fake(fake, args)
        self.assertEqual(p3["status"], "blocked")
        self.assertEqual(p3["decision"], "replan")
        self.assertEqual(p3["iteration"], 3)

        # Invocation 4 — verifier3 said advance: phase complete.
        p4, _ = _run_with_fake(fake, args)
        self.assertEqual(p4["status"], "complete")
        self.assertEqual(p4["decision"], "advance")
        self.assertEqual(p4["iteration"], 3)
        self.assertTrue(p4["verdict"]["dod_met"])

    def test_three_execution_cards_dispatched_across_converge(self):
        args = {"goal": "fix the flake",
                "execution": _execution_t2(),
                "verifier": _verifier(),
                "max_iterations": 5}
        fake = FakeKanbanDB(create_ids=[
            "t_root", "t_exec1", "t_verifier1",
            "t_exec2", "t_verifier2",
            "t_exec3", "t_verifier3",
        ], run_for_task={
            "t_verifier1": _verifier_run(_dod_verdict(
                recommendation="replan",
                gaps=[{"dimension": "a", "issue": "1"}])),
            "t_verifier2": _verifier_run(_dod_verdict(
                recommendation="replan",
                gaps=[{"dimension": "b", "issue": "2"}])),
            "t_verifier3": _verifier_run(_dod_verdict(dod_met=True)),
        })
        for _ in range(4):  # first + 3 re-invocations
            _run_with_fake(fake, args)
        # Exactly 3 execution cards and 3 verifier cards were dispatched.
        new_cards = _create_calls_new(fake)
        exec_cards = [c for c in new_cards if c["parents"] == ["t_root"]]
        self.assertEqual(len(exec_cards), 3)
        # Each verifier parented on its execution card.
        self.assertEqual(new_cards[1]["parents"], ["t_exec1"])
        self.assertEqual(new_cards[3]["parents"], ["t_exec2"])
        self.assertEqual(new_cards[5]["parents"], ["t_exec3"])


# =============================================================================
# 12. T2 — hard-cap escalation when DoD never met (T4: was complete/hard_cap,
#     now a sticky HITL block + named event)
# =============================================================================

class TestHardCap(unittest.TestCase):

    def test_hard_cap_escalates_when_dod_never_met(self):
        """max_iterations=2; verifier always returns replan (distinct gaps each
        iteration so the no-progress guard does not fire first). After 2
        attempts the loop ESCALATES to a sticky HITL block (decision=hard_cap)."""
        args = {"goal": "impossible goal",
                "execution": _execution_t2(),
                "verifier": _verifier(),
                "max_iterations": 2}
        fake = FakeKanbanDB(create_ids=[
            "t_root", "t_exec1", "t_verifier1",
            "t_exec2", "t_verifier2",
        ], run_for_task={
            "t_verifier1": _verifier_run(_dod_verdict(
                dod_met=False, recommendation="replan",
                gaps=[{"dimension": "a", "issue": "1"}])),
            "t_verifier2": _verifier_run(_dod_verdict(
                dod_met=False, recommendation="replan",
                gaps=[{"dimension": "b", "issue": "2"}])),
        })

        # Invocation 1 — first: dispatch attempt 1.
        p1, _ = _run_with_fake(fake, args)
        self.assertEqual(p1["status"], "blocked")
        self.assertEqual(p1["iteration"], 1)

        # Invocation 2 — replan allowed (1 < 2): dispatch attempt 2.
        p2, _ = _run_with_fake(fake, args)
        self.assertEqual(p2["status"], "blocked")
        self.assertEqual(p2["decision"], "replan")
        self.assertEqual(p2["iteration"], 2)

        # Invocation 3 — cap reached (2 < 2 is false): ESCALATE (sticky block).
        p3, _ = _run_with_fake(fake, args, task_id="t_driver")
        self.assertEqual(p3["status"], "escalated")
        self.assertEqual(p3["decision"], "hard_cap")
        self.assertEqual(p3["iteration"], 2)

    def test_hard_cap_emits_sticky_needs_input_block(self):
        """The hard-cap escalation blocks the driver kind=needs_input (sticky —
        recompute_ready will NOT auto-promote it; unblock_task is the resume)."""
        args = {"goal": "impossible goal",
                "execution": _execution_t2(),
                "verifier": _verifier(),
                "max_iterations": 2}
        fake = FakeKanbanDB(create_ids=[
            "t_root", "t_exec1", "t_verifier1",
            "t_exec2", "t_verifier2",
        ], run_for_task={
            "t_verifier1": _verifier_run(_dod_verdict(
                recommendation="replan",
                gaps=[{"dimension": "a", "issue": "1"}])),
            "t_verifier2": _verifier_run(_dod_verdict(
                recommendation="replan",
                gaps=[{"dimension": "b", "issue": "2"}])),
        })
        for _ in range(3):  # first + replan + hard-cap escalation
            _run_with_fake(fake, args, task_id="t_driver")
        needs = _blocks_with_kind(fake, "needs_input")
        self.assertEqual(len(needs), 1,
                         "hard cap must emit exactly one sticky needs_input block")
        self.assertEqual(needs[0]["kind"], "needs_input")
        # The dependency parks are a DIFFERENT kind and must not be confused.
        dep = _blocks_with_kind(fake, "dependency")
        self.assertGreaterEqual(len(dep), 1)

    def test_hard_cap_emits_named_loop_escalated_event(self):
        """The escalation emits a named event describing what the human owes."""
        args = {"goal": "impossible goal",
                "execution": _execution_t2(),
                "verifier": _verifier(),
                "max_iterations": 2}
        fake = FakeKanbanDB(create_ids=[
            "t_root", "t_exec1", "t_verifier1",
            "t_exec2", "t_verifier2",
        ], run_for_task={
            "t_verifier1": _verifier_run(_dod_verdict(
                recommendation="replan",
                gaps=[{"dimension": "a", "issue": "1"}])),
            "t_verifier2": _verifier_run(_dod_verdict(
                recommendation="replan",
                gaps=[{"dimension": "b", "issue": "2"}])),
        })
        for _ in range(3):
            _run_with_fake(fake, args, task_id="t_driver")
        events = _events(fake, "loop_escalated")
        self.assertEqual(len(events), 1)
        _args, _kw = events[0]
        _conn, task_id, kind, payload = _args
        self.assertEqual(task_id, "t_driver",
                         "event lands on the blocked driver card")
        self.assertEqual(kind, "loop_escalated")
        self.assertEqual(payload["exit"], "hard_cap")
        self.assertEqual(payload["phase_index"], 0)
        self.assertEqual(payload["iteration"], 2)
        self.assertIn("human_owes", payload)
        self.assertIsInstance(payload["human_owes"], str)
        self.assertTrue(payload["human_owes"],
                         "human_owes must name what the human owes")

    def test_hard_cap_does_not_dispatch_new_cards(self):
        args = {"goal": "impossible goal",
                "execution": _execution_t2(),
                "verifier": _verifier(),
                "max_iterations": 2}
        fake = FakeKanbanDB(create_ids=[
            "t_root", "t_exec1", "t_verifier1",
            "t_exec2", "t_verifier2",
        ], run_for_task={
            "t_verifier1": _verifier_run(_dod_verdict(
                recommendation="replan",
                gaps=[{"dimension": "a", "issue": "1"}])),
            "t_verifier2": _verifier_run(_dod_verdict(
                recommendation="replan",
                gaps=[{"dimension": "b", "issue": "2"}])),
        })
        for _ in range(3):  # first + 2 re-invocations -> hard cap escalation
            parsed, _ = _run_with_fake(fake, args)
        self.assertEqual(parsed["decision"], "hard_cap")
        # Only 2 execution cards dispatched (attempts 1 and 2); no 3rd.
        exec_cards = [c for c in _create_calls_new(fake)
                      if c["parents"] == ["t_root"]]
        self.assertEqual(len(exec_cards), 2)


# =============================================================================
# 13. T3 — schema + validation for multi-phase decomposition
# =============================================================================

class TestPhaseSchema(unittest.TestCase):

    def test_schema_has_phases_property(self):
        props = le_schemas.LOOP_ENGINE["parameters"]["properties"]
        self.assertIn("phases", props)
        self.assertEqual(props["phases"]["type"], "array")

    def test_phase_item_has_execution_and_optional_verifier(self):
        props = le_schemas.LOOP_ENGINE["parameters"]["properties"]
        phase_item = props["phases"]["items"]
        self.assertIn("execution", phase_item["properties"])
        self.assertIn("verifier", phase_item["properties"])


class TestPhaseValidation(unittest.TestCase):

    def test_empty_phases_rejected(self):
        fake = FakeKanbanDB(create_ids=[])
        with patch.object(le_tools, "_kb", return_value=fake):
            result = le_tools.loop_engine(
                args={"goal": "x", "phases": []}, task_id="t_driver")
        parsed = json.loads(result)
        self.assertIn("error", parsed)

    def test_phases_missing_execution_rejected(self):
        fake = FakeKanbanDB(create_ids=[])
        with patch.object(le_tools, "_kb", return_value=fake):
            result = le_tools.loop_engine(
                args={"goal": "x",
                      "phases": [{"verifier": _verifier()}]},
                task_id="t_driver")
        parsed = json.loads(result)
        self.assertIn("error", parsed)

    def test_valid_phases_accepted_without_top_level_execution(self):
        """When phases is supplied, top-level execution is NOT required."""
        parsed, fake = _run_handler(
            args={"goal": "ship it", "phases": _phases(2)},
            create_ids=["t_root", "t_exec0", "t_verifier0"],
        )
        self.assertNotIn("error", parsed)


# =============================================================================
# 14. T3 — goal decomposes into ≥2 ordered phases with per-phase DoD
# =============================================================================

class TestPhaseDecomposition(unittest.TestCase):

    def test_first_invocation_stores_phase_plan(self):
        phases = _phases(2)
        parsed, fake = _run_handler(
            args={"goal": "ship the feature", "phases": phases},
            create_ids=["t_root", "t_exec0", "t_verifier0"],
        )
        state = _last_loop_state(fake, "t_root")
        self.assertIsNotNone(state)
        self.assertEqual(state["phase_index"], 0)
        self.assertEqual(len(state["phases"]), 2)

    def test_first_phase_execution_card_created_on_root(self):
        phases = _phases(2)
        parsed, fake = _run_handler(
            args={"goal": "ship the feature", "phases": phases},
            create_ids=["t_root", "t_exec0", "t_verifier0"],
        )
        creates = _create_calls_new(fake)
        # Phase 0: exec on root, verifier on exec.
        self.assertEqual(len(creates), 2)
        self.assertEqual(creates[0]["parents"], ["t_root"])
        self.assertEqual(creates[1]["parents"], ["t_exec0"])

    def test_first_invocation_returns_blocked(self):
        phases = _phases(2)
        parsed, fake = _run_handler(
            args={"goal": "ship the feature", "phases": phases},
            create_ids=["t_root", "t_exec0", "t_verifier0"],
        )
        self.assertEqual(parsed["status"], "blocked")
        self.assertEqual(parsed["terminal_ids"], ["t_verifier0"])

    def test_per_phase_dod_in_verifier_body(self):
        """Each phase carries its own DoD embedded in its verifier body."""
        phases = [
            {"execution": _execution(title="phase 0: build API"),
             "verifier": _verifier(body="DoD: API returns 200")},
            {"execution": _execution(title="phase 1: build UI"),
             "verifier": _verifier(body="DoD: UI renders data")},
        ]
        parsed, fake = _run_handler(
            args={"goal": "ship it", "phases": phases},
            create_ids=["t_root", "t_exec0", "t_verifier0"],
        )
        creates = _create_calls_new(fake)
        # Phase 0 verifier carries phase 0's DoD.
        self.assertIn("API returns 200", creates[1]["body"])

    def test_driver_parks_on_phase_zero_verifier(self):
        phases = _phases(2)
        parsed, fake = _run_handler(
            args={"goal": "ship it", "phases": phases},
            create_ids=["t_root", "t_exec0", "t_verifier0"],
            task_id="t_driver",
        )
        links = _calls(fake, "link_tasks")
        _conn, parent_id, child_id = links[-1][0]
        self.assertEqual(parent_id, "t_verifier0")
        self.assertEqual(child_id, "t_driver")


# =============================================================================
# 15. T3 — DoD-met on phase N creates phase N+1 sub-graph + advances phase_index
# =============================================================================

class TestPhaseAdvance(unittest.TestCase):

    def test_dod_met_creates_next_phase_subgraph(self):
        phases = _phases(2)
        seeded = _loop_state_comment_phases(
            "t_root", phases, phase_index=0,
            execution_card="t_exec0", verifier_card="t_verifier0",
            iteration_counter=1)
        parsed, fake = _run_handler(
            args={"goal": "ship it", "phases": phases},
            create_ids=["t_root", "t_exec1", "t_verifier1"],
            preseed_comments={"t_root": [seeded]},
            run_for_task={"t_verifier0":
                          _verifier_run(_dod_verdict(dod_met=True))},
        )
        self.assertEqual(parsed["status"], "blocked")
        self.assertEqual(parsed["decision"], "phase_advance")
        new_cards = _create_calls_new(fake)
        self.assertEqual(len(new_cards), 2)
        self.assertEqual(new_cards[0]["parents"], ["t_root"])
        self.assertEqual(new_cards[1]["parents"], ["t_exec1"])

    def test_dod_met_advances_phase_index(self):
        phases = _phases(2)
        seeded = _loop_state_comment_phases(
            "t_root", phases, phase_index=0,
            execution_card="t_exec0", verifier_card="t_verifier0")
        parsed, fake = _run_handler(
            args={"goal": "ship it", "phases": phases},
            create_ids=["t_root", "t_exec1", "t_verifier1"],
            preseed_comments={"t_root": [seeded]},
            run_for_task={"t_verifier0":
                          _verifier_run(_dod_verdict(dod_met=True))},
        )
        state = _last_loop_state(fake, "t_root")
        self.assertEqual(state["phase_index"], 1)
        self.assertEqual(state["execution_card"], "t_exec1")
        self.assertEqual(state["verifier_card"], "t_verifier1")

    def test_dod_met_parks_driver_on_new_phase_verifier(self):
        phases = _phases(2)
        seeded = _loop_state_comment_phases(
            "t_root", phases, phase_index=0,
            execution_card="t_exec0", verifier_card="t_verifier0")
        parsed, fake = _run_handler(
            args={"goal": "ship it", "phases": phases},
            create_ids=["t_root", "t_exec1", "t_verifier1"],
            preseed_comments={"t_root": [seeded]},
            run_for_task={"t_verifier0":
                          _verifier_run(_dod_verdict(dod_met=True))},
            task_id="t_driver",
        )
        links = _calls(fake, "link_tasks")
        _conn, parent_id, child_id = links[-1][0]
        self.assertEqual(parent_id, "t_verifier1")
        self.assertEqual(child_id, "t_driver")


# =============================================================================
# 16. T3 — last-phase DoD-met → workflow complete
# =============================================================================

class TestPhaseWorkflowComplete(unittest.TestCase):

    def test_last_phase_dod_met_returns_workflow_complete(self):
        phases = _phases(2)
        seeded = _loop_state_comment_phases(
            "t_root", phases, phase_index=1,
            execution_card="t_exec1", verifier_card="t_verifier1")
        parsed, fake = _run_handler(
            args={"goal": "ship it", "phases": phases},
            create_ids=["t_root"],
            preseed_comments={"t_root": [seeded]},
            run_for_task={"t_verifier1":
                          _verifier_run(_dod_verdict(dod_met=True))},
        )
        self.assertEqual(parsed["status"], "complete")
        self.assertEqual(parsed["decision"], "workflow_complete")

    def test_last_phase_complete_does_not_dispatch_new_cards(self):
        phases = _phases(2)
        seeded = _loop_state_comment_phases(
            "t_root", phases, phase_index=1,
            execution_card="t_exec1", verifier_card="t_verifier1")
        parsed, fake = _run_handler(
            args={"goal": "ship it", "phases": phases},
            create_ids=["t_root"],
            preseed_comments={"t_root": [seeded]},
            run_for_task={"t_verifier1":
                          _verifier_run(_dod_verdict(dod_met=True))},
        )
        new_cards = _create_calls_new(fake)
        self.assertEqual(len(new_cards), 0)


# =============================================================================
# 17. T3 — 2-phase workflow runs start-to-complete
# =============================================================================

class TestMultiPhaseWorkflow(unittest.TestCase):

    def test_two_phase_workflow_runs_to_complete(self):
        """Drive a 2-phase workflow by re-invoking the handler against ONE
        stateful fake. Phase 0 advances, phase 1 completes."""
        phases = _phases(2)
        args = {"goal": "ship the feature", "phases": phases}
        fake = FakeKanbanDB(create_ids=[
            "t_root", "t_exec0", "t_verifier0",
            "t_exec1", "t_verifier1",
        ], run_for_task={
            "t_verifier0": _verifier_run(
                _dod_verdict(dod_met=True, recommendation="advance")),
            "t_verifier1": _verifier_run(
                _dod_verdict(dod_met=True, recommendation="advance")),
        })

        # Invocation 1 — first: build phase 0, park.
        p1, _ = _run_with_fake(fake, args)
        self.assertEqual(p1["status"], "blocked")

        # Invocation 2 — phase 0 DoD met: advance to phase 1.
        p2, _ = _run_with_fake(fake, args)
        self.assertEqual(p2["status"], "blocked")
        self.assertEqual(p2["decision"], "phase_advance")

        # Invocation 3 — phase 1 DoD met: workflow complete.
        p3, _ = _run_with_fake(fake, args)
        self.assertEqual(p3["status"], "complete")
        self.assertEqual(p3["decision"], "workflow_complete")

    def test_two_phase_workflow_dispatches_two_execution_cards(self):
        phases = _phases(2)
        args = {"goal": "ship the feature", "phases": phases}
        fake = FakeKanbanDB(create_ids=[
            "t_root", "t_exec0", "t_verifier0",
            "t_exec1", "t_verifier1",
        ], run_for_task={
            "t_verifier0": _verifier_run(_dod_verdict(dod_met=True)),
            "t_verifier1": _verifier_run(_dod_verdict(dod_met=True)),
        })
        for _ in range(3):  # first + advance + complete
            _run_with_fake(fake, args)
        new_cards = _create_calls_new(fake)
        exec_cards = [c for c in new_cards if c["parents"] == ["t_root"]]
        self.assertEqual(len(exec_cards), 2)


# =============================================================================
# 18. T4 — budget exhaustion escalates (layered exit)
# =============================================================================

class TestBudgetExhaustion(unittest.TestCase):

    def test_budget_exhaustion_escalates_before_hard_cap(self):
        """max_iterations=10 (effectively non-stop), budget=2. The budget guard
        fires after 2 iterations, well before the hard cap. Distinct verdicts
        each iteration so no-progress does not fire first."""
        args = {"goal": "spendy goal",
                "execution": _execution_t2(),
                "verifier": _verifier(),
                "max_iterations": 10,
                "budget": 2}
        fake = FakeKanbanDB(create_ids=[
            "t_root", "t_exec1", "t_verifier1",
            "t_exec2", "t_verifier2",
        ], run_for_task={
            "t_verifier1": _verifier_run(_dod_verdict(
                dod_met=False, recommendation="replan",
                gaps=[{"dimension": "a", "issue": "1"}])),
            "t_verifier2": _verifier_run(_dod_verdict(
                dod_met=False, recommendation="replan",
                gaps=[{"dimension": "b", "issue": "2"}])),
        })

        p1, _ = _run_with_fake(fake, args)
        self.assertEqual(p1["status"], "blocked")
        p2, _ = _run_with_fake(fake, args)
        self.assertEqual(p2["decision"], "replan")  # budget_remaining 1 > 0
        p3, _ = _run_with_fake(fake, args, task_id="t_driver")
        # budget_remaining hit 0 -> escalate, NOT replan and NOT hard cap.
        self.assertEqual(p3["status"], "escalated")
        self.assertEqual(p3["decision"], "budget_exhausted")

    def test_budget_escalation_emits_sticky_block_and_event(self):
        args = {"goal": "spendy goal",
                "execution": _execution_t2(),
                "verifier": _verifier(),
                "max_iterations": 10,
                "budget": 2}
        fake = FakeKanbanDB(create_ids=[
            "t_root", "t_exec1", "t_verifier1",
            "t_exec2", "t_verifier2",
        ], run_for_task={
            "t_verifier1": _verifier_run(_dod_verdict(
                recommendation="replan",
                gaps=[{"dimension": "a", "issue": "1"}])),
            "t_verifier2": _verifier_run(_dod_verdict(
                recommendation="replan",
                gaps=[{"dimension": "b", "issue": "2"}])),
        })
        for _ in range(3):
            _run_with_fake(fake, args, task_id="t_driver")
        self.assertGreaterEqual(
            len(_blocks_with_kind(fake, "needs_input")), 1)
        events = _events(fake, "loop_escalated")
        self.assertEqual(len(events), 1)
        _args, _kw = events[0]
        _conn, _tid, _kind, payload = _args
        self.assertEqual(payload["exit"], "budget_exhausted")
        self.assertEqual(payload["budget"], 2)
        self.assertIn("human_owes", payload)

    def test_no_budget_means_unbounded_by_budget(self):
        """Without `budget`, the budget guard never fires (the hard cap still
        bounds). Two replans under a high cap proceed normally, then advance."""
        args = {"goal": "x",
                "execution": _execution_t2(),
                "verifier": _verifier(),
                "max_iterations": 10}
        fake = FakeKanbanDB(create_ids=[
            "t_root", "t_exec1", "t_verifier1",
            "t_exec2", "t_verifier2",
            "t_exec3", "t_verifier3",
        ], run_for_task={
            "t_verifier1": _verifier_run(_dod_verdict(
                recommendation="replan",
                gaps=[{"dimension": "a", "issue": "1"}])),
            "t_verifier2": _verifier_run(_dod_verdict(
                recommendation="replan",
                gaps=[{"dimension": "b", "issue": "2"}])),
            "t_verifier3": _verifier_run(
                _dod_verdict(dod_met=True, recommendation="advance")),
        })
        # first + 3 re-invocations (replan, replan, advance).
        for _ in range(4):
            parsed, _ = _run_with_fake(fake, args, task_id="t_driver")
        # No budget guard -> replans proceed; converges on iteration 3.
        self.assertEqual(parsed["decision"], "advance")
        # No escalation primitives touched.
        self.assertEqual(_blocks_with_kind(fake, "needs_input"), [])
        self.assertEqual(_events(fake, "loop_escalated"), [])


# =============================================================================
# 19. T4 — no-progress streak escalates (layered exit)
# =============================================================================

class TestNoProgress(unittest.TestCase):

    def test_no_progress_streak_escalates(self):
        """Identical verifier verdicts across consecutive iterations signal a
        dead end. With threshold=2, the third identical verdict trips the
        no-progress guard (distinct from the hard cap, which is set high)."""
        identical = _dod_verdict(dod_met=False, recommendation="replan",
                                 gaps=[{"dimension": "tests",
                                        "issue": "same gap every time"}])
        args = {"goal": "stuck goal",
                "execution": _execution_t2(),
                "verifier": _verifier(),
                "max_iterations": 10,
                "no_progress_threshold": 2}
        fake = FakeKanbanDB(create_ids=[
            "t_root", "t_exec1", "t_verifier1",
            "t_exec2", "t_verifier2",
            "t_exec3", "t_verifier3",
        ], run_for_task={
            "t_verifier1": _verifier_run(dict(identical)),
            "t_verifier2": _verifier_run(dict(identical)),
            "t_verifier3": _verifier_run(dict(identical)),
        })
        # iter 1 -> replan (streak 0); iter 2 -> replan (streak 1);
        # iter 3 -> escalate (streak 2 == threshold).
        p1, _ = _run_with_fake(fake, args)
        self.assertEqual(p1["status"], "blocked")
        p2, _ = _run_with_fake(fake, args)
        self.assertEqual(p2["decision"], "replan")
        p3, _ = _run_with_fake(fake, args, task_id="t_driver")
        self.assertEqual(p3["status"], "escalated")
        self.assertEqual(p3["decision"], "no_progress")

    def test_no_progress_escalation_emits_sticky_block_and_event(self):
        identical = _dod_verdict(dod_met=False, recommendation="replan",
                                 gaps=[{"dimension": "x", "issue": "stuck"}])
        args = {"goal": "stuck goal",
                "execution": _execution_t2(),
                "verifier": _verifier(),
                "max_iterations": 10,
                "no_progress_threshold": 2}
        fake = FakeKanbanDB(create_ids=[
            "t_root", "t_exec1", "t_verifier1",
            "t_exec2", "t_verifier2",
            "t_exec3", "t_verifier3",
        ], run_for_task={
            "t_verifier1": _verifier_run(dict(identical)),
            "t_verifier2": _verifier_run(dict(identical)),
            "t_verifier3": _verifier_run(dict(identical)),
        })
        for _ in range(3):
            _run_with_fake(fake, args, task_id="t_driver")
        self.assertGreaterEqual(
            len(_blocks_with_kind(fake, "needs_input")), 1)
        events = _events(fake, "loop_escalated")
        self.assertEqual(len(events), 1)
        _args, _kw = events[0]
        _conn, _tid, _kind, payload = _args
        self.assertEqual(payload["exit"], "no_progress")

    def test_progress_resets_streak(self):
        """A changing verdict resets the no-progress streak to 0, so a loop that
        is genuinely iterating never trips the guard."""
        args = {"goal": "iterating goal",
                "execution": _execution_t2(),
                "verifier": _verifier(),
                "max_iterations": 10,
                "no_progress_threshold": 2}
        fake = FakeKanbanDB(create_ids=[
            "t_root", "t_exec1", "t_verifier1",
            "t_exec2", "t_verifier2",
            "t_exec3", "t_verifier3",
        ], run_for_task={
            "t_verifier1": _verifier_run(_dod_verdict(
                recommendation="replan",
                gaps=[{"dimension": "a", "issue": "1"}])),
            "t_verifier2": _verifier_run(_dod_verdict(
                recommendation="replan",
                gaps=[{"dimension": "b", "issue": "2"}])),
            "t_verifier3": _verifier_run(
                _dod_verdict(dod_met=True, recommendation="advance")),
        })
        # first + 3 re-invocations (replan, replan, advance).
        for _ in range(4):
            parsed, _ = _run_with_fake(fake, args, task_id="t_driver")
        # Distinct verdicts -> streak never reaches threshold -> advance.
        self.assertEqual(parsed["decision"], "advance")
        self.assertEqual(_events(fake, "loop_escalated"), [])


# =============================================================================
# 20. T4 — verifier recommendation="escalate" routes to HITL escalation
# =============================================================================

class TestVerifierEscalate(unittest.TestCase):

    def test_verifier_escalate_routes_to_sticky_block(self):
        """When the verifier's verdict recommends escalation, the driver
        escalates immediately (sticky block + named event) — no replan."""
        seeded = _loop_state_comment_verifier(
            "t_root", execution_card="t_exec", verifier_card="t_verifier",
            iteration_counter=1, max_iterations=5)
        verdict = _dod_verdict(dod_met=False, recommendation="escalate",
                               gaps=[{"dimension": "auth",
                                      "issue": "needs human decision"}])
        parsed, fake = _run_handler(
            args={"goal": "x", "execution": _execution_t2(),
                  "verifier": _verifier()},
            create_ids=["t_root"],
            preseed_comments={"t_root": [seeded]},
            run_for_task={"t_verifier": _verifier_run(verdict)},
            task_id="t_driver",
        )
        self.assertEqual(parsed["status"], "escalated")
        self.assertEqual(parsed["decision"], "verifier_escalate")
        self.assertGreaterEqual(
            len(_blocks_with_kind(fake, "needs_input")), 1)
        events = _events(fake, "loop_escalated")
        self.assertEqual(len(events), 1)
        _args, _kw = events[0]
        _conn, _tid, _kind, payload = _args
        self.assertEqual(payload["exit"], "verifier_escalate")
        self.assertEqual(payload["phase_index"], 0)

    def test_verifier_escalate_does_not_replan(self):
        """Escalation must NOT dispatch a fresh execution/verifier pair."""
        seeded = _loop_state_comment_verifier(
            "t_root", execution_card="t_exec", verifier_card="t_verifier",
            iteration_counter=1, max_iterations=5)
        verdict = _dod_verdict(dod_met=False, recommendation="escalate")
        parsed, fake = _run_handler(
            args={"goal": "x", "execution": _execution_t2(),
                  "verifier": _verifier()},
            create_ids=["t_root"],
            preseed_comments={"t_root": [seeded]},
            run_for_task={"t_verifier": _verifier_run(verdict)},
            task_id="t_driver",
        )
        # No new execution or verifier cards dispatched.
        self.assertEqual(len(_create_calls_new(fake)), 0)


# =============================================================================
# 21. T4 — DoD-met still completes normally (no escalation regression)
# =============================================================================

class TestDoDMetNoEscalation(unittest.TestCase):

    def test_dod_met_completes_without_escalation_primitives(self):
        """A DoD-met advance must NOT touch the escalation primitives (no sticky
        block, no loop_escalated event). Confirms the happy path is unchanged."""
        seeded = _loop_state_comment_verifier(
            "t_root", execution_card="t_exec", verifier_card="t_verifier",
            iteration_counter=1)
        verdict = _dod_verdict(dod_met=True, score=1.0,
                               recommendation="advance")
        parsed, fake = _run_handler(
            args={"goal": "fix the bug",
                  "execution": _execution_t2(),
                  "verifier": _verifier()},
            create_ids=["t_root"],
            preseed_comments={"t_root": [seeded]},
            run_for_task={"t_verifier": _verifier_run(verdict)},
            task_id="t_driver",
        )
        self.assertEqual(parsed["status"], "complete")
        self.assertEqual(parsed["decision"], "advance")
        self.assertEqual(_blocks_with_kind(fake, "needs_input"), [],
                         "DoD-met must not sticky-block the driver")
        self.assertEqual(_events(fake, "loop_escalated"), [],
                         "DoD-met must not emit a loop_escalated event")

    def test_converge_loop_advances_without_escalation(self):
        """A 2-replan-then-advance converge loop never escalates (streak stays
        under the default threshold of 2)."""
        args = {"goal": "fix the flake",
                "execution": _execution_t2(),
                "verifier": _verifier(),
                "max_iterations": 5}
        fake = FakeKanbanDB(create_ids=[
            "t_root", "t_exec1", "t_verifier1",
            "t_exec2", "t_verifier2",
            "t_exec3", "t_verifier3",
        ], run_for_task={
            "t_verifier1": _verifier_run(_dod_verdict(
                dod_met=False, recommendation="replan",
                gaps=[{"dimension": "a", "issue": "1"}])),
            "t_verifier2": _verifier_run(_dod_verdict(
                dod_met=False, recommendation="replan",
                gaps=[{"dimension": "b", "issue": "2"}])),
            "t_verifier3": _verifier_run(
                _dod_verdict(dod_met=True, recommendation="advance")),
        })
        for _ in range(4):
            parsed, _ = _run_with_fake(fake, args, task_id="t_driver")
        self.assertEqual(parsed["decision"], "advance")
        self.assertEqual(_events(fake, "loop_escalated"), [])


# =============================================================================
# 22. T4 — stop-condition-optional (non-stop) mode is still bounded by the caps
# =============================================================================

class TestNonStopBounded(unittest.TestCase):

    def test_non_stop_mode_bounded_by_budget(self):
        """max_iterations=100 (non-stop intent) is still bounded: budget=2 trips
        first. No loop runs unbounded (loop-engineering tenet)."""
        args = {"goal": "force converge",
                "execution": _execution_t2(),
                "verifier": _verifier(),
                "max_iterations": 100,
                "budget": 2}
        fake = FakeKanbanDB(create_ids=[
            "t_root", "t_exec1", "t_verifier1",
            "t_exec2", "t_verifier2",
        ], run_for_task={
            "t_verifier1": _verifier_run(_dod_verdict(
                recommendation="replan",
                gaps=[{"dimension": "a", "issue": "1"}])),
            "t_verifier2": _verifier_run(_dod_verdict(
                recommendation="replan",
                gaps=[{"dimension": "b", "issue": "2"}])),
        })
        for _ in range(3):
            parsed, _ = _run_with_fake(fake, args, task_id="t_driver")
        self.assertEqual(parsed["status"], "escalated")
        self.assertEqual(parsed["decision"], "budget_exhausted")
        # Never reached anywhere near the 100-iteration cap.
        self.assertLess(parsed["iteration"], 100)

    def test_non_stop_mode_bounded_by_no_progress(self):
        """max_iterations=100 (non-stop) bounded by no-progress instead."""
        identical = _dod_verdict(dod_met=False, recommendation="replan",
                                 gaps=[{"dimension": "x", "issue": "stuck"}])
        args = {"goal": "force converge",
                "execution": _execution_t2(),
                "verifier": _verifier(),
                "max_iterations": 100,
                "no_progress_threshold": 2}
        fake = FakeKanbanDB(create_ids=[
            "t_root", "t_exec1", "t_verifier1",
            "t_exec2", "t_verifier2",
            "t_exec3", "t_verifier3",
        ], run_for_task={
            "t_verifier1": _verifier_run(dict(identical)),
            "t_verifier2": _verifier_run(dict(identical)),
            "t_verifier3": _verifier_run(dict(identical)),
        })
        for _ in range(3):
            parsed, _ = _run_with_fake(fake, args, task_id="t_driver")
        self.assertEqual(parsed["status"], "escalated")
        self.assertEqual(parsed["decision"], "no_progress")
        self.assertLess(parsed["iteration"], 100)

    def test_non_stop_mode_bounded_by_hard_cap(self):
        """With no budget and changing verdicts, the hard cap is the final
        deterministic backstop — non-stop mode still terminates."""
        args = {"goal": "force converge",
                "execution": _execution_t2(),
                "verifier": _verifier(),
                "max_iterations": 2}
        fake = FakeKanbanDB(create_ids=[
            "t_root", "t_exec1", "t_verifier1",
            "t_exec2", "t_verifier2",
        ], run_for_task={
            "t_verifier1": _verifier_run(_dod_verdict(
                recommendation="replan",
                gaps=[{"dimension": "a", "issue": "1"}])),
            "t_verifier2": _verifier_run(_dod_verdict(
                recommendation="replan",
                gaps=[{"dimension": "b", "issue": "2"}])),
        })
        for _ in range(3):
            parsed, _ = _run_with_fake(fake, args, task_id="t_driver")
        self.assertEqual(parsed["status"], "escalated")
        self.assertEqual(parsed["decision"], "hard_cap")


# =============================================================================
# 23. T4 — resume path: sticky block confirmed (unblock_task is the only exit)
# =============================================================================

class TestResumePath(unittest.TestCase):

    def test_escalation_reason_names_needs_input_for_resume(self):
        """The sticky block uses kind=needs_input, which _has_sticky_block
        treats as human-gated: recompute_ready will NOT auto-promote it.
        unblock_task is the documented resume path."""
        seeded = _loop_state_comment_verifier(
            "t_root", execution_card="t_exec", verifier_card="t_verifier",
            iteration_counter=1, max_iterations=2)
        verdict = _dod_verdict(dod_met=False, recommendation="escalate")
        parsed, fake = _run_handler(
            args={"goal": "x", "execution": _execution_t2(),
                  "verifier": _verifier()},
            create_ids=["t_root"],
            preseed_comments={"t_root": [seeded]},
            run_for_task={"t_verifier": _verifier_run(verdict)},
            task_id="t_driver",
        )
        needs = _blocks_with_kind(fake, "needs_input")
        self.assertEqual(len(needs), 1)
        # The response names the resume mechanism so the caller/human knows.
        self.assertEqual(parsed["resume_via"], "unblock_task")
        self.assertTrue(parsed["sticky_block"])


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
        TestVerifierDispatch,
        TestDoDVerdictRead,
        TestReplan,
        TestConvergeLoop,
        TestHardCap,
        TestPhaseSchema,
        TestPhaseValidation,
        TestPhaseDecomposition,
        TestPhaseAdvance,
        TestPhaseWorkflowComplete,
        TestMultiPhaseWorkflow,
        TestBudgetExhaustion,
        TestNoProgress,
        TestVerifierEscalate,
        TestDoDMetNoEscalation,
        TestNonStopBounded,
        TestResumePath,
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
