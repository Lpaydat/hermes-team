#!/usr/bin/env python3
"""
B7 (hermes-teams-2ep) / T6 (hermes-teams-prz) — loop_engine root_id keying.

This structurally removes the defect-#5 class (hermes-teams-5w9): goal-byte
drift across promotions orphaned a converging loop because the root dedup key
was salted with sha1(goal)[:10]. Once goal bytes drifted, ``create_task`` minted
a NEW root, loop_state was None, phase_index reset, and the loop never advanced.

DECISION (T6): the durable identity of a loop = ``root_id`` (the root card's
task id), NOT the goal hash. ``loop_engine`` already returns ``root_id`` on
every response; re-invocation now ACCEPTS it back as ``loop_id`` (aliased to
``root_id``) and the engine resolves the root via that handle directly.
``goal_hash`` is demoted to a bootstrap-only fallback — byte-for-byte today's
path, so any caller that omits ``loop_id`` behaves identically to before.

Resolution order on entry (replaces the unconditional ``_idempotency_key`` call):
  1. loop_id SUPPLIED (PRIMARY, drift-immune): engine trusts it as root_id,
     opens that card, reads loop_state. No goal_hash derivation.
  2. loop_id ABSENT (FALLBACK = today's behavior verbatim): derive
     loop:{my_card_id}:{sha1(goal)[:10]} and create_task with it.

If loop_id is supplied but does not resolve (stale/garbage handle), the engine
fires a ``loop_id_mismatch`` event and falls back to the goal_hash path — never
trust a handle that doesn't resolve.

These tests are mock-based (no live kanban DB), mirroring the style of
test_loop_engine.py. The fake kanban_db persists state ACROSS loop_engine calls
so the drift-killer case can drive two real calls through the engine sharing one
board. ``get_task`` returns None for UNKNOWN task ids (so a stale loop_id is
detectable), which is the one behavioral difference from test_loop_engine.py's
FakeKanbanDB.
"""

import hashlib
import json
import sys
import unittest
from collections import namedtuple
from unittest.mock import patch

# Path setup — import loop_engine as a PACKAGE (mirrors test_loop_engine.py).
import os  # noqa: E402
from pathlib import Path  # noqa: E402

PLUGIN_DIR = Path(__file__).resolve().parent
PLUGINS_DIR = PLUGIN_DIR.parent
sys.path.insert(0, str(PLUGINS_DIR))

from loop_engine import tools as le_tools  # noqa: E402


# =============================================================================
# Mock kanban_db — persists across loop_engine calls; get_task returns None for
# unknown task ids (the property the loop_id_mismatch case needs).
# =============================================================================

BLACKBOARD_PREFIX = "[swarm:blackboard] "

_Comment = namedtuple("_Comment", ["author", "body"])


class _FakeTask:
    def __init__(self, task_id, status="done"):
        self.id = task_id
        self.status = status


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


class RootIdFakeDB:
    """Records every kanban_db API call; persists _idem + _comments + _tasks.

    Unlike test_loop_engine.FakeKanbanDB, ``get_task`` returns None for task ids
    that were never minted (so a stale loop_id that doesn't resolve is
    detectable). Newly create_task'd ids are registered with status='done'.
    """

    def __init__(self, create_ids=None, known_task_status=None,
                 run_for_task=None):
        self.calls = []
        self._idem = {}            # idempotency_key -> task_id
        self._comments = {}        # task_id -> [(author, body)]
        self._tasks = {}           # task_id -> _FakeTask
        self._create_ids = list(create_ids) if create_ids else []
        self._counter = 0
        self._run_for_task = run_for_task or {}
        for tid, status in (known_task_status or {}).items():
            self._tasks[tid] = _FakeTask(tid, status)

    # ── connection ────────────────────────────────────────────────────────
    def connect_closing(self, board=None):
        self.calls.append(("connect_closing", (), {"board": board}))
        return _ContextManager(self)

    # ── task lifecycle ────────────────────────────────────────────────────
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
        self._tasks[tid] = _FakeTask(tid, "done")
        if idempotency_key is not None:
            self._idem[idempotency_key] = tid
        return tid

    def get_task(self, conn, task_id):
        self.calls.append(("get_task", (conn, task_id), {}))
        return self._tasks.get(task_id)  # None if unknown (the B7 contract)

    def complete_task(self, conn, task_id, summary=None, metadata=None):
        self.calls.append(("complete_task", (conn, task_id),
                           {"summary": summary, "metadata": metadata}))
        return False  # no-op (already done)

    def latest_run(self, conn, task_id):
        self.calls.append(("latest_run", (conn, task_id), {}))
        return self._run_for_task.get(task_id, _FakeRun())

    # ── blackboard + dependency parking ───────────────────────────────────
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


# =============================================================================
# Test helpers
# =============================================================================

def _execution(title="build it", body="ship it"):
    return {"assignee": "worker", "title": title, "body": body}


def _run(args, fake, task_id="t_driver"):
    """Run loop_engine against ``fake``; return the parsed JSON response."""
    with patch.object(le_tools, "_kb", return_value=fake):
        raw = le_tools.loop_engine(args=args, task_id=task_id)
    return json.loads(raw)


def _calls_after(fake, marker_call):
    """Return calls recorded strictly after ``marker_call`` (by identity)."""
    seen = False
    out = []
    for c in fake.calls:
        if c is marker_call:
            seen = True
            continue
        if seen:
            out.append(c)
    return out


def _calls_in(fake, method_name):
    return [(m, a, kw) for (m, a, kw) in fake.calls if m == method_name]


def _goal_hash_key(my_card_id, goal):
    salt = hashlib.sha1(goal.encode("utf-8")).hexdigest()[:10]
    return f"loop:{my_card_id}:{salt}"


# =============================================================================
# Tests
# =============================================================================

class RootIdKeyingTests(unittest.TestCase):
    """B7: loop_id (root_id) is the durable loop identity; goal_hash is
    bootstrap fallback. defect-#5 class killed."""

    # ── 1. DRIFT-KILLER (the main one) ────────────────────────────────────
    def test_loop_id_constant_with_goal_byte_drift_reopens_same_root_and_preserves_loop_state(self):
        """defect-#5 scenario: goal bytes drift across a promotion, but loop_id
        stays constant. The SAME root card must be reopened and loop_state
        PRESERVED (re-invoke path, counter advanced) — NOT reset to a fresh
        first-invocation on a newly minted root.

        Today (pre-B7) this fails: different goal bytes -> different sha1 salt
        -> create_task mints a NEW root -> loop_state None -> first-call reset.
        """
        fake = RootIdFakeDB(create_ids=["t_root", "t_exec", "t_drifted_root"])

        # Call 1 — bootstrap (no loop_id yet): engine mints the root R via the
        # goal_hash fallback and writes loop_state (phase_index=0, counter=0).
        resp1 = _run(
            {"goal": "alpha goal bytes", "execution": _execution()},
            fake, task_id="t_driver")
        self.assertEqual(resp1["status"], "blocked")  # first-invocation parks
        root_r = resp1["root_id"]
        self.assertEqual(root_r, "t_root")  # sanity: first create_id consumed

        # Call 2 — goal bytes DRIFT (simulating promotion drift), loop_id pins R.
        drifted_goal = "BETA completely different goal bytes — would orphan pre-B7"
        self.assertNotEqual(
            _goal_hash_key("t_driver", "alpha goal bytes"),
            _goal_hash_key("t_driver", drifted_goal),
            "test setup sanity: the two goals must hash differently")

        call2_marker = fake.calls[-1]  # fence for _calls_after
        resp2 = _run(
            {"goal": drifted_goal, "execution": _execution(),
             "loop_id": root_r},
            fake, task_id="t_driver")

        # (a) SAME root reopened despite goal drift — defect-#5 killed.
        self.assertEqual(resp2["root_id"], root_r,
                         "loop_id must pin the root; goal drift must NOT mint "
                         "a new root")

        # (b) Re-invoke path ran (loop_state was READ on R, not None) — proof
        # the existing loop_state was preserved rather than reset to first-call.
        self.assertEqual(resp2["status"], "complete",
                         "preserved loop_state -> re-invoke (complete); a reset "
                         "would have returned status=blocked (first-invocation)")
        self.assertEqual(resp2["decision"], "workflow_complete")

        # (c) Counter ADVANCED from the preserved loop_state (0 -> 1), not reset.
        self.assertEqual(resp2["iteration"], 1,
                         "iteration_counter advanced from the preserved state; "
                         "a first-call reset would report iteration=0")

        # (d) PRIMARY path ran: the engine opened R by id (get_task), it did NOT
        # derive/consult goal_hash for root resolution.
        get_task_ids = [a[1] for (m, a, kw) in fake.calls if m == "get_task"]
        self.assertIn(root_r, get_task_ids,
                      "loop_id PRIMARY path must open the root card by id")

        # (e) No goal_hash-salted root was minted for the drifted goal on call 2
        # (the drifted idempotency key was never used by create_task).
        drifted_key = _goal_hash_key("t_driver", drifted_goal)
        call2_creates = [
            kw.get("idempotency_key")
            for (m, a, kw) in _calls_after(fake, call2_marker)
            if m == "create_task"
        ]
        self.assertNotIn(drifted_key, call2_creates,
                         "the drifted goal's goal_hash key must never be used "
                         "when loop_id is supplied")

    # ── 2. FALLBACK zero-regression ───────────────────────────────────────
    def test_no_loop_id_uses_goal_hash_fallback_verbatim(self):
        """With NO loop_id, the engine derives the goal_hash idempotency key
        exactly like today (loop:{driver}:{sha1(goal)[:10]}). Zero regression by
        construction: any caller that ignores loop_id behaves identically to now.
        """
        fake = RootIdFakeDB(create_ids=["t_root", "t_exec"])
        goal = "fallback goal"
        resp = _run(
            {"goal": goal, "execution": _execution()},
            fake, task_id="t_driver")

        # The root was minted via the goal_hash key (today's path verbatim).
        root_creates = [
            kw for (m, a, kw) in _calls_in(fake, "create_task")
            if kw.get("idempotency_key")
            and not kw.get("parents")  # the root has no parent; exec card does
        ]
        self.assertTrue(root_creates, "a root create_task must have run")
        expected_key = _goal_hash_key("t_driver", goal)
        self.assertEqual(root_creates[0]["idempotency_key"], expected_key,
                         "fallback path must use the goal_hash key verbatim")
        self.assertEqual(resp["status"], "blocked")  # first-invocation
        self.assertEqual(resp["root_id"], "t_root")

        # loop_id was absent -> no root lookup by id attempted for resolution.
        # (No loop_id_mismatch event either.)
        events = [(a[2], a[3]) for (m, a, kw) in fake.calls
                  if m == "_append_event"]
        self.assertFalse(any(k == "loop_id_mismatch" for (k, p) in events),
                         "no mismatch event when loop_id is absent")
        self.assertNotIn("loop_id_mismatch", resp,
                         "response carries no mismatch flag in fallback mode")

    # ── 3. loop_id PRIMARY — no goal_hash dependency ──────────────────────
    def test_loop_id_supplied_does_not_derive_goal_hash(self):
        """With loop_id supplied (and resolving), the engine does NOT derive or
        depend on goal_hash at all — root identity is the loop_id handle."""
        fake = RootIdFakeDB(create_ids=["t_root", "t_exec"])
        # Pre-mint a root R (as a prior bootstrap call would have).
        resp0 = _run(
            {"goal": "original", "execution": _execution()},
            fake, task_id="t_driver")
        root_r = resp0["root_id"]

        goal = "some other goal whose hash must not be consulted"
        fence = fake.calls[-1]
        resp = _run(
            {"goal": goal, "execution": _execution(), "loop_id": root_r},
            fake, task_id="t_driver")

        # The PRIMARY path opened R by id.
        self.assertEqual(resp["root_id"], root_r)

        # The goal_hash key for THIS call's goal was never used (the engine
        # trusted loop_id; it never computed goal_hash for root resolution).
        would_be_key = _goal_hash_key("t_driver", goal)
        call_creates = [
            kw.get("idempotency_key")
            for (m, a, kw) in _calls_after(fake, fence)
            if m == "create_task"
        ]
        self.assertNotIn(would_be_key, call_creates,
                         "goal_hash must not be derived when loop_id is supplied")
        # And no root mint via ANY goal_hash key on this call.
        self.assertFalse(
            any(k and k.startswith("loop:t_driver:") and ":phase" not in k
                for k in call_creates),
            "no goal_hash-salted root key on a loop_id-resolved call")

    # ── 4. loop_id_mismatch event ─────────────────────────────────────────
    def test_loop_id_mismatch_fires_event_and_falls_back_when_handle_unresolved(self):
        """When loop_id is supplied but does NOT resolve to an existing card
        (stale/garbage handle), the engine fires a loop_id_mismatch event and
        falls back to the goal_hash path (safe). It never trusts a handle that
        doesn't resolve."""
        fake = RootIdFakeDB(create_ids=["t_root", "t_exec"])

        # No card with id "ghost-root" exists; get_task returns None for it.
        resp = _run(
            {"goal": "recover via fallback", "execution": _execution(),
             "loop_id": "ghost-root"},
            fake, task_id="t_driver")

        # (a) The mismatch event fired on the driver card, naming the bad handle.
        events = [(a, kw) for (m, a, kw) in fake.calls
                  if m == "_append_event" and a[2] == "loop_id_mismatch"]
        self.assertTrue(events, "loop_id_mismatch event must fire")
        _conn, task_id, kind, payload = events[0][0]
        self.assertEqual(task_id, "t_driver",
                         "event is recorded on the driver card")
        self.assertEqual(payload.get("supplied"), "ghost-root")
        self.assertEqual(payload.get("fallback"), "goal_hash")

        # (b) The response surfaces the mismatch (observability).
        self.assertTrue(resp.get("loop_id_mismatch"),
                        "response must surface loop_id_mismatch=True")

        # (c) The engine fell back to the goal_hash path: a root was minted via
        # the goal_hash key, and the loop proceeded (first-invocation).
        root_creates = [
            kw for (m, a, kw) in _calls_in(fake, "create_task")
            if kw.get("idempotency_key") and not kw.get("parents")
        ]
        self.assertTrue(root_creates)
        expected_key = _goal_hash_key("t_driver", "recover via fallback")
        self.assertEqual(root_creates[0]["idempotency_key"], expected_key,
                         "unresolved loop_id falls back to goal_hash mint")
        self.assertEqual(resp["status"], "blocked")  # first-invocation proceeded


if __name__ == "__main__":
    unittest.main()
