#!/usr/bin/env python3
"""TDD for hermes-teams-22y (T8) — defensive-hardening bundle.

4 independent defensive fixes, each test-first (red -> green):

  1. goal polymorphism (schemas.py): the LOOP_ENGINE schema types ``goal`` as
     string-only, but the engine ALSO accepts a non-empty ``[Claim]`` array
     (the T2 structural fast-pass — ``_validate`` at tools.py:694 + the handler
     at tools.py:1638 reads a ``[Claim]`` goal). Surface BOTH types so an agent
     reading the schema can discover the array form.
  2. root_id alias (schemas.py): the engine reads
     ``args.get("loop_id") or args.get("root_id")`` (tools.py:1670) — root_id
     is an accepted-but-undocumented alias. Surface it as an EXPLICIT property
     (today it hides behind loop_id's description text only).
  3. ``_resolve_phase_specs`` bounds check (tools.py): the indexed lookup
     ``stored_phases[phase_index]`` is unguarded; a stale/corrupt loop_state
     (phase_index out of [0, len)) raises IndexError and crashes the driver.
     Fall back to the top-level execution/verifier instead of crashing.
  4. ``_resolve_root`` ownership check (tools.py): when a supplied loop_id
     resolves to an EXISTING card, the engine trusts it as the loop root with
     NO check the card is actually a loop_engine root. A stale/garbage loop_id
     colliding with an unrelated card would drive that stranger's topology.
     Reject the card unless it carries a loop_state blackboard OR a ``loop:``
     idempotency-key marker -> loop_id_mismatch fallback.

Discipline: the test for each fix is RED today, GREEN after the minimum fix.
Bead: ``bd show hermes-teams-22y``.
"""

import json
import sys
import unittest
from collections import namedtuple
from unittest.mock import patch

from pathlib import Path  # noqa: E402

PLUGIN_DIR = Path(__file__).resolve().parent
PLUGINS_DIR = PLUGIN_DIR.parent
sys.path.insert(0, str(PLUGINS_DIR))

from loop_engine import schemas  # noqa: E402
from loop_engine import tools as le_tools  # noqa: E402


# =============================================================================
# helpers
# =============================================================================

BLACKBOARD_PREFIX = "[swarm:blackboard] "

_Comment = namedtuple("_Comment", ["author", "body"])


class _FakeTask:
    def __init__(self, task_id, status="done", idempotency_key=None):
        self.id = task_id
        self.status = status
        # real loop roots are create_task'd with idempotency_key="loop:...".
        # a stranger card carries no such marker (None).
        self.idempotency_key = idempotency_key


class _FakeRun:
    def __init__(self, summary=None, metadata=None, outcome="completed"):
        self.summary = summary
        self.metadata = metadata
        self.outcome = outcome


class _FakeConn:
    """Opaque connection handle (the engine never inspects it)."""


class _ContextManager:
    def __init__(self, fake):
        self._fake = fake

    def __enter__(self):
        return _FakeConn()

    def __exit__(self, *exc):
        return False


class T8FakeDB:
    """Compact kanban_db stub: persists idempotency keys + blackboard comments
    + tasks. ``get_task`` returns None for unknown ids. ``list_comments``
    returns the blackboard comments written via add_comment (so a real loop
    root carries a ``loop_state`` blackboard; a stranger card does not)."""

    def __init__(self, create_ids=None, known_tasks=None, run_for_task=None):
        self.calls = []
        self._idem = {}            # idempotency_key -> task_id
        self._comments = {}        # task_id -> [(author, body)]
        self._tasks = {}           # task_id -> _FakeTask
        self._create_ids = list(create_ids) if create_ids else []
        self._counter = 0
        self._run_for_task = run_for_task or {}
        for tid, spec in (known_tasks or {}).items():
            if isinstance(spec, _FakeTask):
                self._tasks[tid] = spec
            else:
                self._tasks[tid] = _FakeTask(tid, spec)

    def connect_closing(self, board=None):
        self.calls.append(("connect_closing", (), {"board": board}))
        return _ContextManager(self)

    def create_task(self, conn, title=None, body=None, assignee=None,
                    created_by=None, parents=None, priority=0,
                    idempotency_key=None, workspace_path=None, **kw):
        kwargs = dict(title=title, body=body, assignee=assignee,
                      created_by=created_by, parents=parents, priority=priority,
                      idempotency_key=idempotency_key,
                      workspace_path=workspace_path)
        self.calls.append(("create_task", (conn,), kwargs))
        if idempotency_key is not None and idempotency_key in self._idem:
            return self._idem[idempotency_key]
        if self._create_ids:
            tid = self._create_ids.pop(0)
        else:
            tid = f"t{self._counter}"
        self._counter += 1
        self._tasks[tid] = _FakeTask(tid, "done",
                                     idempotency_key=idempotency_key)
        if idempotency_key is not None:
            self._idem[idempotency_key] = tid
        return tid

    def get_task(self, conn, task_id):
        self.calls.append(("get_task", (conn, task_id), {}))
        return self._tasks.get(task_id)  # None if unknown

    def complete_task(self, conn, task_id, summary=None, metadata=None):
        self.calls.append(("complete_task", (conn, task_id),
                           {"summary": summary, "metadata": metadata}))
        return False

    def latest_run(self, conn, task_id):
        self.calls.append(("latest_run", (conn, task_id), {}))
        return self._run_for_task.get(task_id, _FakeRun())

    def list_comments(self, conn, task_id):
        self.calls.append(("list_comments", (conn, task_id), {}))
        return [_Comment(a, b) for (a, b) in self._comments.get(task_id, [])]

    def add_comment(self, conn, task_id, author, body):
        self.calls.append(("add_comment", (conn, task_id, author, body), {}))
        self._comments.setdefault(task_id, []).append((author, body))

    def block_task(self, conn, task_id, reason=None, kind=None, **kw):
        self.calls.append(("block_task", (conn, task_id),
                           {"reason": reason, "kind": kind}))
        return True

    def link_tasks(self, conn, parent_id, child_id, **kw):
        self.calls.append(("link_tasks", (conn, parent_id, child_id), {}))

    def _append_event(self, conn, task_id, kind, payload=None, *, run_id=None):
        self.calls.append(("_append_event", (conn, task_id, kind, payload),
                           {"run_id": run_id}))


def _execution(title="build it", body="ship it"):
    return {"assignee": "worker", "title": title, "body": body}


def _claim(text="add() returns the sum"):
    return {"text": text,
            "citations": [{"artifact_type": "file_line", "locator": "calc.py:10"}]}


def _run(args, fake, task_id="t_driver"):
    """Run loop_engine against ``fake``; return the parsed JSON response."""
    with patch.object(le_tools, "_kb", return_value=fake):
        raw = le_tools.loop_engine(args=args, task_id=task_id)
    return json.loads(raw)


SCHEMA_PROPS = schemas.LOOP_ENGINE["parameters"]["properties"]


# =============================================================================
# Fix 1 — goal polymorphism (schemas.py)
# =============================================================================

class TestFix1GoalPolymorphism(unittest.TestCase):
    """T8#1: the goal schema must declare BOTH the string and the [Claim] array
    form (the engine already accepts + validates both)."""

    def test_goal_schema_declares_string_and_array_types(self):
        """RED today: schema types goal as {"type": "string"} only."""
        goal_prop = SCHEMA_PROPS["goal"]
        declared = goal_prop["type"]
        types = declared if isinstance(declared, list) else [declared]
        self.assertIn("string", types, "goal must still accept a string")
        self.assertIn("array", types, (
            "goal schema must accept an array (the [Claim] structural "
            f"fast-pass form); declared types = {types}"))

    def test_claim_array_goal_passes_engine_validation(self):
        """The [Claim] form must pass ``_validate`` (the fast-pass seam). This
        already works at the engine level — the schema gap is the only hole."""
        err = le_tools._validate({"goal": [_claim()], "execution": _execution()})
        self.assertIsNone(err, f"[Claim] goal must validate: {err}")


# =============================================================================
# Fix 2 — root_id alias surfaced (schemas.py)
# =============================================================================

class TestFix2RootIdAlias(unittest.TestCase):
    """T8#2: root_id is an accepted alias of loop_id (tools.py:1670). Surface
    it as an explicit property so an agent reading the schema discovers it."""

    def test_root_id_is_an_explicit_property(self):
        """RED today: root_id is not a property key (only mentioned in loop_id's
        description). The fix adds it as an explicit string property."""
        self.assertIn("root_id", SCHEMA_PROPS, (
            "root_id must be an explicit property (accepted alias of loop_id)"))

    def test_root_id_property_is_a_string(self):
        """The explicit root_id property must be typed string (an id handle)."""
        # guard: if the property doesn't exist yet, fail loudly here too.
        self.assertIn("root_id", SCHEMA_PROPS)
        self.assertEqual(SCHEMA_PROPS["root_id"]["type"], "string")


# =============================================================================
# Fix 3 — _resolve_phase_specs bounds check (tools.py)
# =============================================================================

class TestFix3ResolvePhaseSpecsBounds(unittest.TestCase):
    """T8#3: an out-of-bounds phase_index must NOT crash the driver — fall back
    to the top-level execution/verifier (defensive vs stale/corrupt state)."""

    def test_phase_index_beyond_length_falls_back_not_indexerror(self):
        """RED today: stored_phases[5] on a 1-element list raises IndexError."""
        top_exec = {"title": "top", "body": "b"}
        top_ver = {"title": "v", "body": "vb"}
        corrupt = {"phases": [{"execution": {"title": "p0", "body": "b"}}],
                   "phase_index": 5}
        # Must NOT raise; must return the top-level fallback specs.
        exec_spec, ver_spec = le_tools._resolve_phase_specs(
            corrupt, top_exec, top_ver)
        self.assertIs(exec_spec, top_exec,
                      "out-of-bounds phase_index must fall back to top-level "
                      "execution, not crash")
        self.assertIs(ver_spec, top_ver,
                      "out-of-bounds phase_index must fall back to top-level "
                      "verifier, not crash")

    def test_empty_stored_phases_falls_back_not_indexerror(self):
        """An empty phases list with phase_index 0 must also fall back."""
        top_exec = {"title": "top", "body": "b"}
        corrupt_empty = {"phases": [], "phase_index": 0}
        exec_spec, ver_spec = le_tools._resolve_phase_specs(
            corrupt_empty, top_exec, None)
        self.assertIs(exec_spec, top_exec)
        self.assertIsNone(ver_spec)

    def test_negative_phase_index_falls_back(self):
        """A negative phase_index (also out of bounds) must fall back."""
        top_exec = {"title": "top", "body": "b"}
        corrupt_neg = {"phases": [{"execution": {"title": "p0", "body": "b"}}],
                        "phase_index": -1}
        exec_spec, _ = le_tools._resolve_phase_specs(
            corrupt_neg, top_exec, None)
        self.assertIs(exec_spec, top_exec)

    def test_valid_phase_index_still_resolves_from_stored_phases(self):
        """Regression guard: an in-bounds phase_index must still read the stored
        phase spec (the happy path is unchanged by the bounds check)."""
        stored_exec = {"title": "p0-stored", "body": "stored"}
        stored_ver = {"title": "p0-ver", "body": "stored-ver"}
        loop_state = {"phases": [{"execution": stored_exec, "verifier": stored_ver}],
                      "phase_index": 0}
        exec_spec, ver_spec = le_tools._resolve_phase_specs(
            loop_state, {"title": "top", "body": "b"}, None)
        self.assertIs(exec_spec, stored_exec)
        self.assertIs(ver_spec, stored_ver)


# =============================================================================
# Fix 4 — _resolve_root ownership check (tools.py)
# =============================================================================

class TestFix4ResolveRootOwnership(unittest.TestCase):
    """T8#4: a supplied loop_id resolving to an UNRELATED card (no loop_state,
    no loop: marker) must be rejected -> None -> loop_id_mismatch fallback."""

    def test_resolve_root_rejects_non_loop_card_unit(self):
        """RED today: _resolve_root returns any resolvable id, even a stranger
        card with no loop_state / no loop: marker. The fix rejects it -> None."""
        # a stranger card exists but carries NO loop_state blackboard and NO
        # loop: idempotency-key marker.
        fake = T8FakeDB(known_tasks={"t_stranger": _FakeTask("t_stranger", "done")})
        result = le_tools._resolve_root(fake, _FakeConn(), "t_stranger")
        self.assertIsNone(result, (
            "a non-loop card must be rejected by the ownership check "
            "(no loop_state, no loop: marker) -> caller falls back"))

    def test_resolve_root_accepts_card_with_loop_state(self):
        """Regression guard: a real loop root (loop_state on its blackboard) is
        accepted. The ownership check must not reject legitimate roots."""
        fake = T8FakeDB(
            known_tasks={"t_root": _FakeTask("t_root", "done", idempotency_key="loop:drv:abc")})
        # write a loop_state blackboard onto the root (as the engine does)
        le_tools._write_blackboard(fake, _FakeConn(), "t_root", "loop_engine",
                                   "loop_state", {"phase_index": 0})
        result = le_tools._resolve_root(fake, _FakeConn(), "t_root")
        self.assertEqual(result, "t_root",
                         "a card carrying loop_state is a real loop root -> accepted")

    def test_resolve_root_accepts_card_with_loop_idempotency_marker(self):
        """A card whose idempotency_key starts with 'loop:' is a loop root even
        before loop_state is written (the marker is the create-time signal)."""
        fake = T8FakeDB(known_tasks={
            "t_root": _FakeTask("t_root", "done",
                                idempotency_key="loop:t_drv:deadbeef")})
        # NO loop_state blackboard on this one — only the loop: marker.
        result = le_tools._resolve_root(fake, _FakeConn(), "t_root")
        self.assertEqual(result, "t_root",
                         "a card with a loop: idempotency marker is a loop root")

    def test_loop_id_to_non_loop_card_fires_mismatch_and_falls_back(self):
        """END-TO-END: a loop_id that collides with a stranger card must NOT
        drive that card. The engine fires loop_id_mismatch and falls back to
        the goal_hash path (mints a fresh root)."""
        fake = T8FakeDB(
            create_ids=["t_fresh_root", "t_exec"],
            known_tasks={"t_stranger": _FakeTask("t_stranger", "done")})
        resp = _run({"goal": "some goal", "execution": _execution(),
                     "loop_id": "t_stranger"}, fake, task_id="t_drv")
        # the stranger card must NOT be the root (a fresh root is minted)
        self.assertNotEqual(resp["root_id"], "t_stranger",
                            "the non-loop stranger card must NOT be driven")
        self.assertEqual(resp["root_id"], "t_fresh_root",
                         "the engine must fall back to a fresh goal_hash root")
        # the mismatch must be surfaced on the response (observability)
        self.assertTrue(resp.get("loop_id_mismatch"),
                        "loop_id colliding with a non-loop card must surface "
                        "loop_id_mismatch on the response")


if __name__ == "__main__":
    unittest.main()
