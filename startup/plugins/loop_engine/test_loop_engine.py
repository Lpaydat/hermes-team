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


@dataclass
class _FakeTask:
    """Minimal stand-in for hermes_cli.kanban_db.Task (the fields we read).

    T6 durability reconciliation reads the terminal card's ``status`` to decide
    whether an in-flight iteration has finished (re-park) or produced a verdict
    (decide). The default ``status='done'`` keeps every prior re-invoke test
    green — they always assumed the terminal was already complete.
    """
    id: str = ""
    status: str = "done"
    assignee: str = None


class FakeKanbanDB:
    """Records every kanban_db API call and returns canned responses.

    Mirrors the FakeKanbanDB in test_kanban_chains.py, extended with:
      * latest_run(conn, task_id)         — the re-invoke result read path
      * preseed_comments                  - {task_id: [_Comment, ...]} to plant
                                            board state (loop_state) for tests
      * run_for_task                      - {task_id: _FakeRun} for latest_run
    """

    def __init__(self, create_ids=None, block_result=True,
                 preseed_comments=None, run_for_task=None, task_status=None):
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
        # T6: per-task status overrides for reconciliation tests. Default is
        # 'done' (see _FakeTask) so existing re-invoke tests are unaffected.
        self._task_status = dict(task_status or {})

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

    def get_task(self, conn, task_id):
        self.calls.append(("get_task", (conn, task_id), {}))
        return _FakeTask(
            id=task_id,
            status=self._task_status.get(task_id, "done"),
        )

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
                 preseed_comments=None, run_for_task=None, task_status=None):
    """Convenience: run loop_engine with a FakeKanbanDB, return (parsed, fake)."""
    fake = FakeKanbanDB(create_ids=create_ids, block_result=block_result,
                        preseed_comments=preseed_comments,
                        run_for_task=run_for_task, task_status=task_status)
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
        # goal is the only hard requirement; execution OR phases satisfies anyOf
        # (a phases-only call is valid — _validate enforces the real invariant).
        params = le_schemas.LOOP_ENGINE["parameters"]
        self.assertEqual(params["required"], ["goal"])
        any_of = params["anyOf"]
        req_sets = [set(x["required"]) for x in any_of]
        self.assertIn({"execution"}, req_sets)
        self.assertIn({"phases"}, req_sets)

    def test_phases_only_call_accepted_by_validate(self):
        # A phases-only call (no top-level execution) passes _validate — the
        # primary std/high call shape is buildable by a schema-strict driver.
        err = le_tools._validate({"goal": "ship the ADR", "phases": [
            {"execution": _execution_t2(), "verifier": _verifier(),
             "max_iterations": 3}]})
        self.assertIsNone(err)

    def test_execution_only_call_still_accepted(self):
        err = le_tools._validate({"goal": "ship it",
                                  "execution": _execution_t2(),
                                  "verifier": _verifier()})
        self.assertIsNone(err)

    def test_execution_step_required_fields(self):
        step = le_schemas.LOOP_ENGINE["parameters"]["properties"]["execution"]
        # T5: assignee is now OPTIONAL — the resolved runner (configured -> worker
        # -> default) is the default assignee when a card omits it.
        self.assertEqual(set(step["required"]), {"title", "body"})

    def test_schema_has_runner_property(self):
        props = le_schemas.LOOP_ENGINE["parameters"]["properties"]
        self.assertIn("runner", props)
        self.assertEqual(props["runner"]["type"], "string")

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
        # T1 hard cap = 1: one execution -> report result, terminate. The
        # terminal signal is workflow_complete (matching T2 semantics) so the
        # driver's "on workflow_complete" step fires for both tiers.
        self.assertEqual(parsed["status"], "complete")
        self.assertEqual(parsed["iteration"], 1)
        self.assertEqual(parsed["decision"], "workflow_complete")
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
        # OVERRIDE CLOSED: recommendation='advance' NO LONGER overrides a missing
        # dod_met. The engine does not trust recommendation to advance a failed
        # DoD — it replans (or escalates) instead. (artifact-neutral verdict:
        # no behaviors/defect_traces, so the gate defers to dod_met, which is
        # falsy here.)
        seeded = _loop_state_comment_verifier(
            "t_root", verifier_card="t_verifier", iteration_counter=1)
        verdict = {"recommendation": "advance", "gaps": []}  # dod_met absent
        parsed, fake = _run_handler(
            args={"goal": "x", "execution": _execution_t2(),
                  "verifier": _verifier()},
            create_ids=["t_root", "t_exec2", "t_verifier2"],
            preseed_comments={"t_root": [seeded]},
            run_for_task={"t_verifier":
                          _verifier_run(verdict)},
        )
        self.assertNotEqual(parsed["status"], "complete")
        self.assertNotEqual(parsed["decision"], "advance")

    def test_no_verdict_when_verifier_run_missing(self):
        # T6: a done terminal with no verdict (dropped/stale completion — the
        # optimistic-lock-drop residual risk) is NOT treated as not-met->replan,
        # which would phantom-decide on empty evidence. The engine re-evaluates
        # (dispatches a fresh verifier for the same iteration).
        seeded = _loop_state_comment_verifier(
            "t_root", verifier_card="t_verifier", iteration_counter=1,
            max_iterations=3)
        parsed, fake = _run_handler(
            args={"goal": "x", "execution": _execution_t2(),
                  "verifier": _verifier()},
            create_ids=["t_root", "t_reeval1"],
            preseed_comments={"t_root": [seeded]},
            run_for_task={},  # no verdict — stale/dropped completion
        )
        # Done terminal, no verdict -> re-evaluate (not replan, not phantom).
        self.assertEqual(parsed["status"], "blocked")
        self.assertEqual(parsed["decision"], "reevaluate")


# =============================================================================
# 9b. DoD artifact gate — the engine validates defect_traces before trusting dod_met
# =============================================================================

class TestDoDArtifactGate(unittest.TestCase):
    """The verifier's dod_met is a self-report; the engine independently asserts
    the defect-coverage artifact is complete and carries no latent_defect."""

    def _verdict_with_traces(self, dod_met=True, trace_status="traced",
                             fabricated=False, n_behaviors=1, n_traces=None):
        behaviors = [{"behavior": f"b{i}"} for i in range(n_behaviors)]
        nt = n_traces if n_traces is not None else n_behaviors
        traces = [{"behavior": f"b{i}", "citation": f"cite{i}",
                   "status": trace_status, "fabricated": fabricated}
                  for i in range(nt)]
        return {"dod_met": dod_met, "recommendation": "advance",
                "behaviors": behaviors, "defect_traces": traces,
                "gaps": [], "score": 0.9, "design_version_ref": "v1"}

    def test_advance_when_artifact_complete_all_traced(self):
        seeded = _loop_state_comment_verifier(
            "t_root", verifier_card="t_verifier", iteration_counter=1)
        parsed, fake = _run_handler(
            args={"goal": "x", "execution": _execution_t2(),
                  "verifier": _verifier()},
            create_ids=["t_root"],
            preseed_comments={"t_root": [seeded]},
            run_for_task={"t_verifier":
                          _verifier_run(self._verdict_with_traces())},
        )
        self.assertEqual(parsed["status"], "complete")
        self.assertEqual(parsed["decision"], "advance")

    def test_rejects_dod_met_true_when_traces_missing(self):
        # dod_met=true but defect_traces empty -> NOT advance (self-report
        # untrusted; the artifact must be complete).
        seeded = _loop_state_comment_verifier(
            "t_root", verifier_card="t_verifier", iteration_counter=1)
        verdict = {"dod_met": True, "recommendation": "advance",
                   "behaviors": [{"behavior": "b1"}], "defect_traces": [],
                   "gaps": []}
        parsed, fake = _run_handler(
            args={"goal": "x", "execution": _execution_t2(),
                  "verifier": _verifier()},
            create_ids=["t_root", "t_exec2", "t_verifier2"],
            preseed_comments={"t_root": [seeded]},
            run_for_task={"t_verifier": _verifier_run(verdict)},
        )
        self.assertNotEqual(parsed["status"], "complete")

    def test_rejects_dod_met_true_when_fewer_traces_than_behaviors(self):
        seeded = _loop_state_comment_verifier(
            "t_root", verifier_card="t_verifier", iteration_counter=1)
        # 2 behaviors, 1 trace -> under-covered -> NOT advance.
        verdict = self._verdict_with_traces(n_behaviors=2, n_traces=1)
        parsed, fake = _run_handler(
            args={"goal": "x", "execution": _execution_t2(),
                  "verifier": _verifier()},
            create_ids=["t_root", "t_exec2", "t_verifier2"],
            preseed_comments={"t_root": [seeded]},
            run_for_task={"t_verifier": _verifier_run(verdict)},
        )
        self.assertNotEqual(parsed["status"], "complete")

    def test_rejects_dod_met_true_when_a_trace_is_latent_defect(self):
        # The headline fix: a latent_defect trace hard-blocks advance even when
        # the verifier mistakenly wrote dod_met=true.
        seeded = _loop_state_comment_verifier(
            "t_root", verifier_card="t_verifier", iteration_counter=1)
        verdict = self._verdict_with_traces(dod_met=True,
                                            trace_status="latent_defect")
        parsed, fake = _run_handler(
            args={"goal": "x", "execution": _execution_t2(),
                  "verifier": _verifier()},
            create_ids=["t_root", "t_exec2", "t_verifier2"],
            preseed_comments={"t_root": [seeded]},
            run_for_task={"t_verifier": _verifier_run(verdict)},
        )
        self.assertNotEqual(parsed["status"], "complete")

    def test_rejects_dod_met_true_when_a_trace_is_fabricated(self):
        seeded = _loop_state_comment_verifier(
            "t_root", verifier_card="t_verifier", iteration_counter=1)
        verdict = self._verdict_with_traces(dod_met=True, fabricated=True)
        parsed, fake = _run_handler(
            args={"goal": "x", "execution": _execution_t2(),
                  "verifier": _verifier()},
            create_ids=["t_root", "t_exec2", "t_verifier2"],
            preseed_comments={"t_root": [seeded]},
            run_for_task={"t_verifier": _verifier_run(verdict)},
        )
        self.assertNotEqual(parsed["status"], "complete")

    def test_artifact_neutral_when_not_required_advances_on_dod_met(self):
        # Generic / ADR-convention: artifact_required not set (default False) +
        # no behaviors/traces -> artifact-neutral -> dod_met alone advances.
        # (Keeps the engine usable by consumers that return simple verdicts.)
        seeded = _loop_state_comment_verifier(
            "t_root", verifier_card="t_verifier", iteration_counter=1)
        verdict = {"dod_met": True, "recommendation": "advance",
                   "gaps": []}  # no behaviors/defect_traces
        parsed, fake = _run_handler(
            args={"goal": "x", "execution": _execution_t2(),
                  "verifier": _verifier()},
            create_ids=["t_root"],
            preseed_comments={"t_root": [seeded]},
            run_for_task={"t_verifier": _verifier_run(verdict)},
        )
        self.assertEqual(parsed["status"], "complete")

    def test_artifact_required_blocks_lazy_verifier(self):
        # A converge phase opts in (artifact_required=True). A verifier that
        # omits behaviors/defect_traces is lazy -> gate FAILS -> does NOT
        # advance on dod_met=true alone (the escape hatch is closed for opted-in
        # phases).
        seeded = _loop_state_comment_verifier(
            "t_root", verifier_card="t_verifier", iteration_counter=1)
        verdict = {"dod_met": True, "recommendation": "advance", "gaps": []}
        verifier_req = _verifier()
        verifier_req["artifact_required"] = True
        parsed, fake = _run_handler(
            args={"goal": "x", "execution": _execution_t2(),
                  "verifier": verifier_req},
            create_ids=["t_root", "t_exec2", "t_verifier2"],
            preseed_comments={"t_root": [seeded]},
            run_for_task={"t_verifier": _verifier_run(verdict)},
        )
        self.assertNotEqual(parsed["status"], "complete")

    def test_artifact_required_advances_when_artifact_complete(self):
        # artifact_required=True + a complete artifact (one traced trace per
        # behavior, no latent_defect) -> advances.
        seeded = _loop_state_comment_verifier(
            "t_root", verifier_card="t_verifier", iteration_counter=1)
        verifier_req = _verifier()
        verifier_req["artifact_required"] = True
        parsed, fake = _run_handler(
            args={"goal": "x", "execution": _execution_t2(),
                  "verifier": verifier_req},
            create_ids=["t_root"],
            preseed_comments={"t_root": [seeded]},
            run_for_task={"t_verifier":
                          _verifier_run(self._verdict_with_traces())},
        )
        self.assertEqual(parsed["status"], "complete")

    def test_council_state_persisted_to_root_after_verdict(self):
        # The driver (not the grandchild verifier) persists council:last_iteration
        # + council:best_so_far to the root blackboard so replan workers can read
        # the last verdict + best-so-far for keep/discard.
        seeded = _loop_state_comment_verifier(
            "t_root", verifier_card="t_verifier", iteration_counter=1)
        verdict = self._verdict_with_traces(dod_met=True, trace_status="traced")
        parsed, fake = _run_handler(
            args={"goal": "x", "execution": _execution_t2(),
                  "verifier": _verifier()},
            create_ids=["t_root"],
            preseed_comments={"t_root": [seeded]},
            run_for_task={"t_verifier": _verifier_run(verdict)},
        )
        last = le_tools._read_blackboard(fake, fake, "t_root",
                                         "council:last_iteration")
        best = le_tools._read_blackboard(fake, fake, "t_root",
                                         "council:best_so_far")
        self.assertIsNotNone(last)
        self.assertEqual(last["dod_verdict"]["dod_met"], True)
        self.assertEqual(last["design_version_ref"], "v1")
        self.assertIsNotNone(best)
        self.assertEqual(best["score"], 0.9)

    def test_best_so_far_updates_only_on_higher_score(self):
        # A regressing iteration (lower score) does NOT overwrite best_so_far.
        seeded = _loop_state_comment_verifier(
            "t_root", verifier_card="t_verifier", iteration_counter=1)
        # Pre-seed a best_so_far at 0.9; this iteration scores 0.5 -> stays 0.9.
        _bb_payload = json.dumps({"key": "council:best_so_far",
                                  "value": {"score": 0.9,
                                            "design_version_ref": "v0"}})
        best_seed = _Comment("loop_engine",
                             f"[swarm:blackboard] {_bb_payload}")
        verdict = self._verdict_with_traces(dod_met=False, trace_status="traced")
        verdict["score"] = 0.5
        verdict["design_version_ref"] = "v1"
        parsed, fake = _run_handler(
            args={"goal": "x", "execution": _execution_t2(),
                  "verifier": _verifier()},
            create_ids=["t_root", "t_exec2", "t_verifier2"],
            preseed_comments={"t_root": [seeded, best_seed]},
            run_for_task={"t_verifier": _verifier_run(verdict)},
        )
        best = le_tools._read_blackboard(fake, fake, "t_root",
                                         "council:best_so_far")
        self.assertEqual(best["score"], 0.9)  # unchanged — regression discarded
        self.assertEqual(best["design_version_ref"], "v0")


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
# 24. T5 — runner profile config + fallback (single resolver, per-card override)
# =============================================================================

class TestRunnerResolver(unittest.TestCase):
    """The resolver is the SINGLE documented function implementing the
    resolution order: configured runner -> worker -> default.

    A candidate is 'available' when known_profiles is None (accept any) or
    contains it. This lets a deployment's known-profile set steer the fallback:
    an unknown configured runner -> worker, an unknown worker -> default.
    """

    def test_configured_runner_wins(self):
        self.assertEqual(le_tools._resolve_runner("debugger"), "debugger")

    def test_runner_unset_falls_back_to_worker(self):
        self.assertEqual(le_tools._resolve_runner(None), "worker")

    def test_worker_available_returns_worker_when_known(self):
        self.assertEqual(
            le_tools._resolve_runner(None, known_profiles={"worker", "qa"}),
            "worker")

    def test_worker_unavailable_falls_back_to_default(self):
        # worker absent from the known set -> default is the last resort.
        self.assertEqual(
            le_tools._resolve_runner(None, known_profiles={"default"}),
            "default")

    def test_unknown_configured_runner_falls_back_to_worker(self):
        # debugger not known -> worker (which IS known) is the next candidate.
        self.assertEqual(
            le_tools._resolve_runner("debugger", known_profiles={"worker"}),
            "worker")

    def test_default_is_unconditional_last_resort(self):
        # nothing in the known set matches -> default regardless.
        self.assertEqual(
            le_tools._resolve_runner(None, known_profiles=set()),
            "default")

    def test_empty_string_runner_treated_as_unset(self):
        self.assertEqual(le_tools._resolve_runner(""), "worker")

    def test_resolver_is_single_documented_function(self):
        # The resolver exists, is callable, and is the documented entry point.
        self.assertTrue(callable(le_tools._resolve_runner))
        self.assertIn("configured runner", le_tools._resolve_runner.__doc__)
        self.assertIn("worker", le_tools._resolve_runner.__doc__)
        self.assertIn("default", le_tools._resolve_runner.__doc__)


class TestRunnerCardAssignee(unittest.TestCase):
    """T5: the resolved runner is the DEFAULT assignee for execution/verifier
    cards. An explicit per-card assignee overrides it."""

    def test_runner_set_execution_card_gets_runner(self):
        parsed, fake = _run_handler(
            args={"goal": "debug it", "runner": "debugger",
                  "execution": {"title": "repro", "body": "reproduce the bug"}},
            create_ids=["t_root", "t_exec"],
        )
        creates = _create_calls(fake)
        self.assertEqual(creates[1]["assignee"], "debugger")

    def test_runner_set_verifier_card_gets_runner(self):
        parsed, fake = _run_handler(
            args={"goal": "debug it", "runner": "debugger",
                  "execution": {"title": "repro", "body": "..."},
                  "verifier": {"title": "verify", "body": "DoD: ..."}},
            create_ids=["t_root", "t_exec", "t_verifier"],
        )
        creates = _create_calls(fake)
        self.assertEqual(creates[1]["assignee"], "debugger")  # exec
        self.assertEqual(creates[2]["assignee"], "debugger")  # verifier

    def test_runner_unset_execution_card_gets_worker(self):
        parsed, fake = _run_handler(
            args={"goal": "x",
                  "execution": {"title": "work", "body": "do it"}},
            create_ids=["t_root", "t_exec"],
        )
        creates = _create_calls(fake)
        self.assertEqual(creates[1]["assignee"], "worker")

    def test_runner_unset_verifier_card_gets_worker(self):
        parsed, fake = _run_handler(
            args={"goal": "x",
                  "execution": {"title": "work", "body": "do it"},
                  "verifier": {"title": "verify", "body": "DoD: ..."}},
            create_ids=["t_root", "t_exec", "t_verifier"],
        )
        creates = _create_calls(fake)
        self.assertEqual(creates[2]["assignee"], "worker")

    def test_per_card_override_wins_over_runner(self):
        parsed, fake = _run_handler(
            args={"goal": "x", "runner": "debugger",
                  "execution": {"assignee": "developer",
                                "title": "w", "body": "b"},
                  "verifier": {"assignee": "verifier",
                               "title": "v", "body": "vb"}},
            create_ids=["t_root", "t_exec", "t_verifier"],
        )
        creates = _create_calls(fake)
        self.assertEqual(creates[1]["assignee"], "developer")
        self.assertEqual(creates[2]["assignee"], "verifier")

    def test_resolved_runner_stored_in_loop_state(self):
        parsed, fake = _run_handler(
            args={"goal": "x", "runner": "debugger",
                  "execution": {"title": "w", "body": "b"},
                  "verifier": {"title": "v", "body": "vb"}},
            create_ids=["t_root", "t_exec", "t_verifier"],
        )
        state = _last_loop_state(fake, "t_root")
        self.assertEqual(state["resolved_runner"], "debugger")

    def test_runner_applied_on_replan(self):
        """A replan (fresh exec + verifier) must apply the resolved runner
        stored in loop_state to the new cards."""
        phases = _phases(1)  # single-phase, but via phases path is fine; use T2
        seeded = _loop_state_comment_verifier(
            "t_root", execution_card="t_exec", verifier_card="t_verifier",
            iteration_counter=1, max_iterations=3)
        # Inject resolved_runner into the seeded loop_state.
        seeded = _loop_state_comment_with_runner(
            "t_root", resolved_runner="debugger",
            execution_card="t_exec", verifier_card="t_verifier",
            iteration_counter=1, max_iterations=3)
        verdict = _dod_verdict(dod_met=False, recommendation="replan")
        parsed, fake = _run_handler(
            args={"goal": "fix it", "runner": "debugger",
                  "execution": {"title": "w", "body": "b"},
                  "verifier": {"title": "v", "body": "vb"}},
            create_ids=["t_root", "t_exec2", "t_verifier2"],
            preseed_comments={"t_root": [seeded]},
            run_for_task={"t_verifier": _verifier_run(verdict)},
        )
        new_cards = _create_calls_new(fake)
        self.assertEqual(len(new_cards), 2)
        self.assertEqual(new_cards[0]["assignee"], "debugger")  # exec
        self.assertEqual(new_cards[1]["assignee"], "debugger")  # verifier

    def test_runner_applied_on_phase_advance(self):
        """A multi-phase advance must apply the resolved runner to the next
        phase's execution + verifier cards (phases omit assignee so the runner
        default applies)."""
        phases = [
            {"execution": {"title": "p0", "body": "b0"},
             "verifier": {"title": "v0", "body": "vb0"}},
            {"execution": {"title": "p1", "body": "b1"},
             "verifier": {"title": "v1", "body": "vb1"}},
        ]
        seeded = _loop_state_comment_phases_runner(
            "t_root", phases, resolved_runner="debugger", phase_index=0,
            execution_card="t_exec0", verifier_card="t_verifier0",
            iteration_counter=1)
        parsed, fake = _run_handler(
            args={"goal": "ship it", "runner": "debugger", "phases": phases},
            create_ids=["t_root", "t_exec1", "t_verifier1"],
            preseed_comments={"t_root": [seeded]},
            run_for_task={"t_verifier0":
                          _verifier_run(_dod_verdict(dod_met=True))},
        )
        new_cards = _create_calls_new(fake)
        self.assertEqual(len(new_cards), 2)
        self.assertEqual(new_cards[0]["assignee"], "debugger")  # exec
        self.assertEqual(new_cards[1]["assignee"], "debugger")  # verifier

    def test_phase_override_wins_over_runner(self):
        """A phase that explicitly sets assignee overrides the runner."""
        phases = [
            {"execution": {"assignee": "developer",
                           "title": "p0", "body": "b0"},
             "verifier": {"assignee": "verifier",
                          "title": "v0", "body": "vb0"}},
        ]
        parsed, fake = _run_handler(
            args={"goal": "ship it", "runner": "debugger", "phases": phases},
            create_ids=["t_root", "t_exec0", "t_verifier0"],
        )
        new_cards = _create_calls_new(fake)
        self.assertEqual(new_cards[0]["assignee"], "developer")
        self.assertEqual(new_cards[1]["assignee"], "verifier")


class TestRunnerValidation(unittest.TestCase):

    def test_runner_must_be_nonempty_string(self):
        fake = FakeKanbanDB(create_ids=[])
        with patch.object(le_tools, "_kb", return_value=fake):
            result = le_tools.loop_engine(
                args={"goal": "x", "runner": "   ",
                      "execution": _execution()}, task_id="t_driver")
        parsed = json.loads(result)
        self.assertIn("error", parsed)
        self.assertIn("runner", parsed["error"])

    def test_runner_missing_assignee_accepted_when_runner_set(self):
        parsed, fake = _run_handler(
            args={"goal": "x", "runner": "debugger",
                  "execution": {"title": "w", "body": "b"}},
            create_ids=["t_root", "t_exec"],
        )
        self.assertNotIn("error", parsed)

    def test_runner_missing_assignee_accepted_when_runner_unset(self):
        # No runner, no assignee -> resolver fills in 'worker'.
        parsed, fake = _run_handler(
            args={"goal": "x",
                  "execution": {"title": "w", "body": "b"}},
            create_ids=["t_root", "t_exec"],
        )
        self.assertNotIn("error", parsed)


# -- T5 (runner) helpers --------------------------------------------------------

def _loop_state_comment_with_runner(root_id, resolved_runner="worker",
                                    execution_card="t_exec",
                                    verifier_card="t_verifier",
                                    iteration_counter=1, max_iterations=5):
    """T2 loop_state pre-seeded with resolved_runner (the T5 durability field)."""
    payload = json.dumps({
        "key": "loop_state",
        "value": {
            "phase_index": 0,
            "iteration_counter": iteration_counter,
            "terminal_ids": [verifier_card],
            "execution_card": execution_card,
            "verifier_card": verifier_card,
            "max_iterations": max_iterations,
            "resolved_runner": resolved_runner,
        },
    })
    return _Comment("loop_engine", f"[swarm:blackboard] {payload}")


def _loop_state_comment_phases_runner(root_id, phases, resolved_runner="worker",
                                      phase_index=0,
                                      execution_card="t_exec",
                                      verifier_card="t_verifier",
                                      iteration_counter=1, max_iterations=5):
    """T3 multi-phase loop_state pre-seeded with resolved_runner."""
    value = {
        "phase_index": phase_index,
        "phases": phases,
        "iteration_counter": iteration_counter,
        "terminal_ids": [verifier_card],
        "execution_card": execution_card,
        "verifier_card": verifier_card,
        "max_iterations": max_iterations,
        "resolved_runner": resolved_runner,
    }
    payload = json.dumps({"key": "loop_state", "value": value})
    return _Comment("loop_engine", f"[swarm:blackboard] {payload}")


# =============================================================================
# T6 — durability: idempotent re-drive + crash-resume (unit / mock-level)
# =============================================================================

class TestCardIdempotencyKey(unittest.TestCase):
    """T6: intent-stable idempotency keys for phase cards (dedup by intent).

    A re-drive after a crash must dedup against cards already created that
    iteration. The key is stable for (driver, phase, iteration, role) and
    distinct on every axis (SPEC §Constraints respected — idempotency is a
    pre-check; we design for dedup-by-intent, not locking).
    """

    def test_key_format_and_stability(self):
        k = le_tools._card_idempotency_key("t_drv", 0, 1, "exec")
        self.assertEqual(k, "loop:t_drv:phase0:iter1:exec")
        # Stable across repeated calls (same inputs -> same key).
        self.assertEqual(
            le_tools._card_idempotency_key("t_drv", 0, 1, "exec"), k)

    def test_key_distinguishes_each_axis(self):
        base = le_tools._card_idempotency_key("t_drv", 0, 1, "exec")
        self.assertNotEqual(  # phase axis
            base, le_tools._card_idempotency_key("t_drv", 1, 1, "exec"))
        self.assertNotEqual(  # iteration axis (replan -> new cards)
            base, le_tools._card_idempotency_key("t_drv", 0, 2, "exec"))
        self.assertNotEqual(  # role axis (exec vs verify)
            base, le_tools._card_idempotency_key("t_drv", 0, 1, "verify"))
        self.assertNotEqual(  # driver axis (two workflows on one board)
            base, le_tools._card_idempotency_key("t_other", 0, 1, "exec"))


class TestIntentStableCardKeys(unittest.TestCase):
    """T6: phase execution + verifier cards carry intent-stable idempotency keys
    so a crash-replay that re-enters card creation dedups against cards already
    created that iteration rather than duplicating them."""

    def test_first_invocation_t1_stamps_exec_key(self):
        parsed, fake = _run_handler(
            args={"goal": "debug the flake", "execution": _execution()},
            create_ids=["t_root", "t_exec"], task_id="t_drv",
        )
        creates = _create_calls(fake)
        # [0] root (goal-hash key from T4); [1] exec (intent-stable key).
        self.assertIsNotNone(creates[0]["idempotency_key"])  # root
        self.assertEqual(creates[1]["idempotency_key"],
                         "loop:t_drv:phase0:iter0:exec")

    def test_first_invocation_t2_stamps_exec_and_verifier_keys(self):
        parsed, fake = _run_handler(
            args={"goal": "converge the loop",
                  "execution": _execution_t2(),
                  "verifier": _verifier(), "max_iterations": 3},
            create_ids=["t_root", "t_exec", "t_ver"], task_id="t_drv",
        )
        creates = _create_calls(fake)
        self.assertEqual(len(creates), 3)
        # T2 seeds iteration_counter=1, so the first iteration's cards are iter1.
        self.assertEqual(creates[1]["idempotency_key"],
                         "loop:t_drv:phase0:iter1:exec")
        self.assertEqual(creates[2]["idempotency_key"],
                         "loop:t_drv:phase0:iter1:verify")


class TestReinvokeReconciliation(unittest.TestCase):
    """T6: re-drive reconciliation against board state.

    On re-invoke the engine checks the terminal's ACTUAL board status before
    acting on a verdict:
      * terminal NOT done (crash between create-cards and park) -> re-park on
        the EXISTING terminal. No duplicate cards, no phantom verdict.
      * terminal done but NO verdict (dropped/stale completion) -> re-evaluate
        (dispatch a fresh verifier) rather than phantom-advance or replan.
    """

    def _seed_t2(self, root_id="t_root", exec_id="t_exec", ver_id="t_ver",
                 iteration=1, reeval_counter=None):
        value = {
            "phase_index": 0,
            "iteration_counter": iteration,
            "terminal_ids": [ver_id],
            "execution_card": exec_id,
            "verifier_card": ver_id,
            "max_iterations": 5,
            "resolved_runner": "worker",
            "exit_counters": {"hard_cap": 0, "no_progress_streak": 0},
            "last_state_hash": None,
        }
        if reeval_counter is not None:
            value["reeval_counter"] = reeval_counter
        payload = json.dumps({"key": "loop_state", "value": value})
        return _Comment("loop_engine", f"[swarm:blackboard] {payload}")

    def test_terminal_not_done_reparks_without_new_cards(self):
        seeded = self._seed_t2()
        parsed, fake = _run_handler(
            args={"goal": "g", "execution": _execution_t2(),
                  "verifier": _verifier(), "max_iterations": 5},
            create_ids=["t_root"],  # root resolved idempotently; NO new cards
            preseed_comments={"t_root": [seeded]},
            task_status={"t_ver": "ready"},  # verifier still in-flight
            task_id="t_drv",
        )
        self.assertEqual(parsed["status"], "blocked")
        self.assertEqual(parsed["decision"], "repark")
        # No new exec/verifier cards on the re-drive (dedup by re-parking).
        new_cards = [c for c in _create_calls(fake) if c.get("parents")]
        self.assertEqual(new_cards, [])
        # Driver dependency-parked on the EXISTING verifier terminal.
        dep_blocks = _blocks_with_kind(fake, "dependency")
        self.assertTrue(dep_blocks)
        self.assertIn("t_ver", dep_blocks[-1]["reason"])

    def test_terminal_done_but_no_verdict_reevaluates_not_phantom_advance(self):
        seeded = self._seed_t2()
        parsed, fake = _run_handler(
            args={"goal": "g", "execution": _execution_t2(),
                  "verifier": _verifier(), "max_iterations": 5},
            create_ids=["t_root", "t_reeval1"],
            preseed_comments={"t_root": [seeded]},
            # Verifier done, but metadata carries NO dod_verdict (stale drop).
            run_for_task={"t_ver": _FakeRun(
                task_id="t_ver", summary="?", metadata=None,
                outcome="completed")},
            task_status={"t_ver": "done"},
            task_id="t_drv",
        )
        self.assertEqual(parsed["status"], "blocked")
        self.assertEqual(parsed["decision"], "reevaluate")
        # A fresh verifier card was created, parented on the (done) exec card.
        new_verifiers = [c for c in _create_calls(fake)
                         if c.get("parents") == ["t_exec"]]
        self.assertEqual(len(new_verifiers), 1)
        # The fresh verifier carries an intent-stable reeval key (iter1:reeval1).
        self.assertEqual(new_verifiers[0]["idempotency_key"],
                         "loop:t_drv:phase0:iter1:reeval1")
        # Driver parked on the fresh verifier, not the stale one.
        dep_blocks = _blocks_with_kind(fake, "dependency")
        self.assertIn(parsed["verifier_card"], dep_blocks[-1]["reason"])

    def test_t1_terminal_not_done_reparks_without_stub_decide(self):
        # T1 path: exec card still in-flight -> re-park, do NOT stub-decide on a
        # phantom result (the old bug: read latest_run of an unfinished card).
        value = {
            "phase_index": 0, "iteration_counter": 0,
            "terminal_ids": ["t_exec"], "execution_card": "t_exec",
            "resolved_runner": "worker",
        }
        payload = json.dumps({"key": "loop_state", "value": value})
        seeded = _Comment("loop_engine", f"[swarm:blackboard] {payload}")
        parsed, fake = _run_handler(
            args={"goal": "g", "execution": _execution()},
            create_ids=["t_root"],
            preseed_comments={"t_root": [seeded]},
            task_status={"t_exec": "ready"},  # exec still in-flight
            task_id="t_drv",
        )
        self.assertEqual(parsed["status"], "blocked")
        self.assertEqual(parsed["decision"], "repark")
        new_cards = [c for c in _create_calls(fake) if c.get("parents")]
        self.assertEqual(new_cards, [])

    def test_reevaluate_bound_exceeds_into_escalation(self):
        # reeval_counter already at the cap -> next stale verdict escalates to
        # HITL instead of looping forever on persistent stale drops (deterministic
        # termination, SPEC §Termination is safety-critical).
        seeded = self._seed_t2(reeval_counter=le_tools.MAX_REEVAL_ATTEMPTS)
        parsed, fake = _run_handler(
            args={"goal": "g", "execution": _execution_t2(),
                  "verifier": _verifier(), "max_iterations": 5},
            create_ids=["t_root"],
            preseed_comments={"t_root": [seeded]},
            run_for_task={"t_ver": _FakeRun(
                task_id="t_ver", summary="?", metadata=None,
                outcome="completed")},
            task_status={"t_ver": "done"},
            task_id="t_drv",
        )
        self.assertEqual(parsed["status"], "escalated")
        self.assertEqual(parsed["decision"], "stale_verdict")
        # No fresh verifier created (escalation, not another reeval).
        new_verifiers = [c for c in _create_calls(fake)
                         if c.get("parents") == ["t_exec"]]
        self.assertEqual(new_verifiers, [])


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
        TestRunnerResolver,
        TestRunnerCardAssignee,
        TestRunnerValidation,
        TestCardIdempotencyKey,
        TestIntentStableCardKeys,
        TestReinvokeReconciliation,
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
