#!/usr/bin/env python3
"""
TDD for hermes-teams-g9t1 (B3) — next-branch transition in on_session_end.

When a grill session ends AND the backlog is NON-EMPTY (open decision/fact nodes
remain), the plugin creates a next-branch kanban card on hermes-hq: a fresh PO
session instructed to recover the graph + grill the top open nodes (NOT re-do
resolved). The card is created via the hermes kanban CLI (subprocess.run) with
HERMES_HOME pinned to the startup root and HERMES_KANBAN_BOARD pinned to hermes-hq.

The EMPTY-backlog case is B4 (GRILL COMPLETE) — B3 does NOT fire there. Non-grill
sessions (didn't touch the graph, or grill already complete) are a no-op too.

The kanban-create subprocess is MOCKED so no real card is ever created.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# ── path setup: import context_graph as a PACKAGE (mirrors B2 tests) ─────────
PLUGIN_DIR = Path(__file__).resolve().parent          # .../plugins/context_graph
PLUGINS_DIR = PLUGIN_DIR.parent                        # .../plugins
sys.path.insert(0, str(PLUGINS_DIR))

import context_graph as cgplugin  # noqa: E402  (package: hook + transition)
from context_graph import context_graph as cg  # noqa: E402  (core graph module)


def _create_calls(run_mock):
    """The unittest ``call`` objects for every ``kanban ... create`` invocation
    on the mocked subprocess.

    The serialize guard (B3/B4 follow-up) issues a ``kanban list`` call BEFORE
    any create, so create-path tests assert on create calls specifically rather
    than on overall call count.
    """
    return [c for c in run_mock.call_args_list if "create" in c.args[0]]


class NextBranchTransitionTest(unittest.TestCase):
    """B3: grill session-end with a non-empty backlog → next-branch card."""

    def setUp(self):
        # Fresh temp DB so tests never touch the real startup/context_graph.db.
        self._prior_db_path = cg.DB_PATH
        self._tmpdir = tempfile.TemporaryDirectory()
        cg.init_db(os.path.join(self._tmpdir.name, "graph.db"))
        cgplugin._GRAPH_TOUCHED_SESSIONS.clear()
        self.addCleanup(self._restore)

    def _restore(self):
        cgplugin._GRAPH_TOUCHED_SESSIONS.clear()
        cg.DB_PATH = self._prior_db_path
        self._tmpdir.cleanup()

    # ── the transition: grill + non-empty backlog → card created ─────────────
    def test_card_created_when_grill_session_and_open_nodes(self):
        """A mid-grill session ending with open nodes → a next-branch card is
        created on hermes-hq via the kanban CLI, with the right title/body/flags."""
        # grill in progress: open root tagged with the venture slug topic + an
        # open decision node (non-empty backlog)
        cg.add_node("root", "venture: TestVenture", topics=["testventure"])
        cg.add_node("decision", "an open decision")  # open → backlog non-empty
        cgplugin._on_post_tool_call(tool_name="graph_frontier", session_id="s-grill")

        with mock.patch.object(cgplugin, "subprocess") as mock_subprocess:
            mock_subprocess.run.return_value = mock.MagicMock(
                returncode=0, stdout="created t_abc123", stderr=""
            )
            result = cgplugin._on_session_end(session_id="s-grill", completed=True)

        # B1/B2 invariants preserved: returns None, drains the per-session tracker
        self.assertIsNone(result)
        self.assertNotIn("s-grill", cgplugin._GRAPH_TOUCHED_SESSIONS)

        # SERIALIZE GUARD: the guard's `kanban list` fires first (the mocked
        # board returns no running [grill-loop] card → empty-ish stdout → guard
        # passes), THEN exactly one create fires.
        create_calls = _create_calls(mock_subprocess.run)
        self.assertEqual(len(create_calls), 1)
        cmd = create_calls[0].args[0]
        env = create_calls[0].kwargs["env"]

        # cmd shape: hermes kanban create <title> --assignee ... --skill ... --body ...
        self.assertEqual(cmd[0], "hermes")
        self.assertIn("kanban", cmd)
        self.assertIn("create", cmd)
        self.assertIn("--assignee", cmd)
        self.assertEqual(cmd[cmd.index("--assignee") + 1], "product-owner")
        self.assertIn("--skill", cmd)
        self.assertEqual(cmd[cmd.index("--skill") + 1], "decision-tree-grill")

        # the title carries the venture slug (from the open root's topic) + count
        title = cmd[cmd.index("create") + 1]
        self.assertIn("[grill-loop]", title)
        self.assertIn("testventure", title)
        self.assertIn("1 open nodes remain", title)

        # the body instructs: recover graph FIRST via graph_pull('<slug>'), then
        # grill top open nodes, do NOT re-do resolved
        body = cmd[cmd.index("--body") + 1]
        self.assertIn("graph_pull('testventure')", body)
        self.assertIn("type=root", body)
        self.assertIn("graph_frontier()", body)
        self.assertIn("do NOT re-do resolved nodes", body)

        # HERMES_HOME pinned to the startup root + board pinned to hermes-hq
        # (deterministic; the persisted current-board could be anything)
        self.assertTrue(
            env["HERMES_HOME"].endswith("startup"),
            f"HERMES_HOME must be the startup root, got {env['HERMES_HOME']!r}",
        )
        self.assertEqual(env["HERMES_KANBAN_BOARD"], "hermes-hq")

    # ── no card when the session was NOT a grill session ─────────────────────
    def test_no_card_when_session_did_not_touch_graph(self):
        """Open root + open nodes exist, but the session never touched the graph
        (a chart session / unrelated PO work) → NOT a grill session → no card."""
        cg.add_node("root", "venture: TestVenture", topics=["testventure"])
        cg.add_node("decision", "an open decision")
        # NOTE: no post_tool_call for s-chart → is_grill_session is False

        with mock.patch.object(cgplugin, "subprocess") as mock_subprocess:
            cgplugin._on_session_end(session_id="s-chart", completed=True)
        mock_subprocess.run.assert_not_called()

    def test_no_card_when_grill_already_complete(self):
        """Session touched the graph but the grill is complete (root resolved) →
        no open root → not a mid-grill session → no card (B3's transition)."""
        root_id = cg.add_node("root", "venture: TestVenture", topics=["testventure"])
        cg.add_node("decision", "an open decision")
        cg.resolve_node(root_id)  # grill complete → no open root
        cgplugin._on_post_tool_call(tool_name="graph_remaining", session_id="s-done")

        with mock.patch.object(cgplugin, "subprocess") as mock_subprocess:
            cgplugin._on_session_end(session_id="s-done", completed=True)
        mock_subprocess.run.assert_not_called()

    # ── no NEXT-BRANCH card when the backlog is EMPTY (B4 territory, not B3) ──
    def test_no_card_when_backlog_empty(self):
        """A grill session (touched graph + open root) but graph_remaining() is
        EMPTY → B3's non-empty transition does NOT fire. (EMPTY is B4: the chart
        transition — _create_chart_card is mocked here to isolate B3; B4's own
        tests cover the chart card.) No next-branch card created here."""
        cg.add_node("root", "venture: TestVenture", topics=["testventure"])
        # an already-resolved decision → NOT in graph_remaining → backlog empty
        resolved = cg.add_node("decision", "resolved decision")
        cg.resolve_node(resolved)
        cgplugin._on_post_tool_call(tool_name="graph_frontier", session_id="s-empty")

        # mock the chart helper so B4's subprocess call is swallowed here — this
        # test asserts ONLY that B3's next-branch path (the kanban subprocess)
        # is not taken on an empty backlog.
        with mock.patch.object(cgplugin, "subprocess") as mock_subprocess, \
             mock.patch.object(cgplugin, "_create_chart_card"):
            cgplugin._on_session_end(session_id="s-empty", completed=True)
        mock_subprocess.run.assert_not_called()

    # ── the card-creation helper directly (cmd shape; reusable by B4) ────────
    def test_create_next_branch_card_helper_invokes_kanban_cli(self):
        """The helper builds the kanban-create cmd from a slug + count and runs
        it with the pinned env. Reusable by B4 (the empty-backlog transition)."""
        with mock.patch.object(cgplugin, "subprocess") as mock_subprocess:
            mock_subprocess.run.return_value = mock.MagicMock(
                returncode=0, stdout="t_xyz", stderr=""
            )
            cgplugin._create_next_branch_card("acme", 7)

        # guard lists first (no running card), then exactly one create
        create_calls = _create_calls(mock_subprocess.run)
        self.assertEqual(len(create_calls), 1)
        cmd = create_calls[0].args[0]
        env = create_calls[0].kwargs["env"]
        title = cmd[cmd.index("create") + 1]
        self.assertIn("acme", title)
        self.assertIn("7 open nodes remain", title)
        self.assertEqual(env["HERMES_KANBAN_BOARD"], "hermes-hq")
        self.assertTrue(env["HERMES_HOME"].endswith("startup"))

    # ── SERIALIZE GUARD (B3/B4 follow-up): one grill-loop per venture ────────
    #
    # Root cause this fixes: every grill session-end created a [grill-loop]
    # card, so CONCURRENT session-ends spawned MULTIPLE [grill-loop] cards that
    # collided on the same VB (intercom contention) → decisions never resolved
    # → infinite loop. Fix: SERIALIZE — before creating, check hermes-hq for a
    # RUNNING card of the same type+venture; if one exists, SKIP.

    def test_has_running_card_true_when_running_marker_and_slug_match(self):
        """_has_running_card returns True when a RUNNING line carries the marker
        AND the venture slug. A running line carries BOTH the '●' icon and the
        literal status word 'running' (see kanban._fmt_task_line)."""
        running_line = (
            "● t_abc123  running   product-owner        "
            "[grill-loop] acme: continue grill — 9 open nodes remain"
        )
        with mock.patch.object(cgplugin, "subprocess") as mock_subprocess:
            mock_subprocess.run.return_value = mock.MagicMock(
                returncode=0, stdout=running_line, stderr=""
            )
            self.assertTrue(cgplugin._has_running_card("[grill-loop]", "acme"))

    def test_has_running_card_false_when_no_matching_card(self):
        """Empty board (or no card of this type+venture) → False → create."""
        with mock.patch.object(cgplugin, "subprocess") as mock_subprocess:
            mock_subprocess.run.return_value = mock.MagicMock(
                returncode=0, stdout="", stderr=""
            )
            self.assertFalse(cgplugin._has_running_card("[grill-loop]", "acme"))

    def test_has_running_card_false_when_card_done_not_running(self):
        """A DONE card (✓ done) carrying the marker+slug does NOT count — only
        RUNNING cards block, so a finished grill-loop never blocks the next."""
        done_line = (
            "✓ t_abc123  done     product-owner        "
            "[grill-loop] acme: continue grill — 9 open nodes remain"
        )
        with mock.patch.object(cgplugin, "subprocess") as mock_subprocess:
            mock_subprocess.run.return_value = mock.MagicMock(
                returncode=0, stdout=done_line, stderr=""
            )
            self.assertFalse(cgplugin._has_running_card("[grill-loop]", "acme"))

    def test_has_running_card_false_for_different_venture_slug(self):
        """A running [grill-loop] card for a DIFFERENT venture does not block —
        serialization is per-venture, so concurrent grills on distinct ventures
        may each keep looping."""
        running_line = (
            "● t_abc123  running   product-owner        "
            "[grill-loop] otherco: continue grill — 2 open nodes remain"
        )
        with mock.patch.object(cgplugin, "subprocess") as mock_subprocess:
            mock_subprocess.run.return_value = mock.MagicMock(
                returncode=0, stdout=running_line, stderr=""
            )
            self.assertFalse(cgplugin._has_running_card("[grill-loop]", "acme"))

    def test_has_running_card_false_on_subprocess_error(self):
        """Fire-and-log: if the kanban-list subprocess raises, the guard returns
        False (treat as 'no running card') so the transition is never blocked."""
        with mock.patch.object(cgplugin, "subprocess") as mock_subprocess:
            mock_subprocess.run.side_effect = OSError("kanban CLI blew up")
            self.assertFalse(cgplugin._has_running_card("[grill-loop]", "acme"))

    def test_next_branch_card_skipped_when_grill_loop_already_running(self):
        """SERIALIZE: when a RUNNING [grill-loop] card for the same venture
        already exists on hermes-hq, _create_next_branch_card SKIPS — it issues
        the guard's `list` call but does NOT issue any `create` call."""
        running_line = (
            "● t_abc123  running   product-owner        "
            "[grill-loop] acme: continue grill — 9 open nodes remain"
        )
        with mock.patch.object(cgplugin, "subprocess") as mock_subprocess:
            mock_subprocess.run.return_value = mock.MagicMock(
                returncode=0, stdout=running_line, stderr=""
            )
            result = cgplugin._create_next_branch_card("acme", 5)

        self.assertIsNone(result)  # skipped → no card created
        # the guard's list call fired, but NO create call
        self.assertEqual(
            len(_create_calls(mock_subprocess.run)), 0,
            "must not create a duplicate [grill-loop] card when one is running",
        )

    def test_next_branch_card_created_when_no_running_duplicate(self):
        """SERIALIZE happy path: no running [grill-loop] for the venture → the
        guard's list fires, THEN exactly one create fires (the card is made)."""
        with mock.patch.object(cgplugin, "subprocess") as mock_subprocess:
            mock_subprocess.run.return_value = mock.MagicMock(
                returncode=0, stdout="", stderr=""
            )
            cgplugin._create_next_branch_card("acme", 3)

        self.assertEqual(len(_create_calls(mock_subprocess.run)), 1)

    def test_no_duplicate_grill_loop_card_via_session_end(self):
        """The full on_session_end transition respects the guard: a mid-grill
        session with a non-empty backlog creates a [grill-loop] card ONLY if no
        running one exists for the venture. Here one is running → no create."""
        cg.add_node("root", "venture: Acme", topics=["acme"])
        cg.add_node("decision", "an open decision")  # non-empty backlog
        cgplugin._on_post_tool_call(tool_name="graph_frontier", session_id="s-grill")

        running_line = (
            "● t_abc123  running   product-owner        "
            "[grill-loop] acme: continue grill — 9 open nodes remain"
        )
        with mock.patch.object(cgplugin, "subprocess") as mock_subprocess:
            mock_subprocess.run.return_value = mock.MagicMock(
                returncode=0, stdout=running_line, stderr=""
            )
            cgplugin._on_session_end(session_id="s-grill", completed=True)

        self.assertEqual(
            len(_create_calls(mock_subprocess.run)), 0,
            "session-end must not spawn a duplicate grill-loop",
        )


if __name__ == "__main__":
    unittest.main()
