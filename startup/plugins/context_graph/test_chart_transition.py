#!/usr/bin/env python3
"""
TDD for hermes-teams-tid8 (B4) — chart transition in on_session_end.

The SIBLING of B3. B3 handled a NON-empty backlog (-> next-branch card to keep
grilling). B4 handles the EMPTY backlog: a mid-grill session whose
graph_remaining() is EMPTY -> the grill is genuinely exhausted -> CREATE THE
CHART CARD (the grill->map transition). The chart card hands off to the
product-owner with the wayfinding-auto + wayfinder skills to chart the
wayfinding map from the brief + the pinned graph.

Detection gate (reuses B1/B2): is_grill_session(session_id) is True (session
touched the graph AND an open grill root exists) AND cg.graph_remaining() is
EMPTY. Non-grill sessions and NON-empty backlogs do NOT fire the chart card
(NON-empty is B3's next-branch transition).

The kanban-create subprocess is MOCKED so no real card is ever created.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# ── path setup: import context_graph as a PACKAGE (mirrors B3 tests) ─────────
PLUGIN_DIR = Path(__file__).resolve().parent          # .../plugins/context_graph
PLUGINS_DIR = PLUGIN_DIR.parent                        # .../plugins
sys.path.insert(0, str(PLUGINS_DIR))

import context_graph as cgplugin  # noqa: E402  (package: hook + transition)
from context_graph import context_graph as cg  # noqa: E402  (core graph module)


def _skill_values(cmd):
    """Return the list of values following every --skill flag in cmd."""
    return [
        cmd[i + 1]
        for i, token in enumerate(cmd)
        if token == "--skill" and i + 1 < len(cmd)
    ]


def _create_calls(run_mock):
    """The unittest ``call`` objects for every ``kanban ... create`` invocation
    on the mocked subprocess.

    The serialize guard (B3/B4 follow-up) issues a ``kanban list`` call BEFORE
    any create, so create-path tests assert on create calls specifically rather
    than on overall call count.
    """
    return [c for c in run_mock.call_args_list if "create" in c.args[0]]


class ChartTransitionTest(unittest.TestCase):
    """B4: grill session-end with an EMPTY backlog -> chart card."""

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

    def _empty_backlog_grill(self, session_id="s-chart"):
        """Shared fixture: an open grill root (tagged with a venture slug) +
        a session that touched the graph, with graph_remaining() EMPTY (the
        only decision is already resolved)."""
        cg.add_node("root", "venture: TestVenture", topics=["testventure"])
        resolved = cg.add_node("decision", "already-resolved decision")
        cg.resolve_node(resolved)  # resolved -> NOT in graph_remaining -> empty
        cgplugin._on_post_tool_call(tool_name="graph_frontier", session_id=session_id)

    # ── the transition: grill + EMPTY backlog -> chart card created ───────────
    def test_chart_card_created_when_grill_session_and_empty_backlog(self):
        """A mid-grill session ending with an EMPTY backlog -> the grill is
        exhausted -> a chart card is created on hermes-hq via the kanban CLI,
        with the right title/body/skills/flags."""
        self._empty_backlog_grill(session_id="s-chart")

        with mock.patch.object(cgplugin, "subprocess") as mock_subprocess:
            mock_subprocess.run.return_value = mock.MagicMock(
                returncode=0, stdout="created t_chart1", stderr=""
            )
            result = cgplugin._on_session_end(session_id="s-chart", completed=True)

        # B1/B2 invariants preserved: returns None, drains the per-session tracker
        self.assertIsNone(result)
        self.assertNotIn("s-chart", cgplugin._GRAPH_TOUCHED_SESSIONS)

        # SERIALIZE GUARD: the guard's `kanban list` fires first (no running
        # [chart] card on the mocked board → empty-ish stdout → guard passes),
        # THEN exactly one create fires (the chart card).
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

        # BOTH skills are attached: wayfinding-auto AND wayfinder
        self.assertEqual(_skill_values(cmd), ["wayfinding-auto", "wayfinder"])

        # the title carries the chart marker + venture slug + the wayfinding cue
        title = cmd[cmd.index("create") + 1]
        self.assertIn("[chart]", title)
        self.assertIn("testventure", title)
        self.assertIn("chart the wayfinding map", title)

        # the body is the CHART-THE-MAP card: shared language (graph_pull +
        # type=term), ADR location, the DO list (name destination, wayfinder:map
        # epic, child tickets), and the COMPLETE guard (chart only, resolve
        # nothing).
        body = cmd[cmd.index("--body") + 1]
        self.assertIn("CHART-THE-MAP card", body)
        self.assertIn("graph_pull('testventure')", body)
        self.assertIn("type=term", body)
        self.assertIn("docs/ventures/testventure/docs/adr/", body)
        self.assertIn("wayfinder:map", body)
        self.assertIn("chart only, resolve nothing", body)

        # HERMES_HOME pinned to the startup root + board pinned to hermes-hq
        # (deterministic; the persisted current-board could be anything)
        self.assertTrue(
            env["HERMES_HOME"].endswith("startup"),
            f"HERMES_HOME must be the startup root, got {env['HERMES_HOME']!r}",
        )
        self.assertEqual(env["HERMES_KANBAN_BOARD"], "hermes-hq")

    # ── B4 is TERMINAL: resolving the grill root (open -> resolved) ───────────
    def test_chart_transition_resolves_grill_root_on_success(self):
        """B4 is terminal: a successful chart-card creation must resolve the
        grill root (status open -> resolved). After the transition,
        has_open_root() flips False -> is_grill_session() is False -> B4 cannot
        re-fire on a later exhausted-backlog session-end. Without this, the root
        stays open and the chart transition is re-triggerable (the bug)."""
        self._empty_backlog_grill(session_id="s-chart")
        self.assertTrue(cg.has_open_root(), "fixture: grill root starts open")

        with mock.patch.object(cgplugin, "subprocess") as mock_subprocess:
            mock_subprocess.run.return_value = mock.MagicMock(
                returncode=0, stdout="created t_chart1", stderr=""
            )
            cgplugin._on_session_end(session_id="s-chart", completed=True)

        self.assertFalse(
            cg.has_open_root(),
            "B4 must resolve the grill root on a successful chart transition; "
            "an open root lets B4 re-fire (not terminal).",
        )

    def test_chart_transition_leaves_root_open_on_create_failure(self):
        """Regression guard: a chart-card create FAILURE must NOT resolve the
        grill root. _create_chart_card returns None on failure (or on a
        serialize-guard skip); the root stays open so a later exhausted-backlog
        session-end can retry the transition — the grill is not handed off
        until a chart card actually exists."""
        self._empty_backlog_grill(session_id="s-chart")
        self.assertTrue(cg.has_open_root(), "fixture: grill root starts open")

        with mock.patch.object(cgplugin, "subprocess") as mock_subprocess:
            mock_subprocess.run.side_effect = OSError("kanban CLI blew up")
            cgplugin._on_session_end(session_id="s-chart", completed=True)

        self.assertTrue(
            cg.has_open_root(),
            "a failed chart-card create must leave the root open for retry; "
            "resolve only on a successful create.",
        )

    # ── no chart card when the backlog is NON-empty (B3 fires instead) ────────
    def test_no_chart_card_when_backlog_non_empty(self):
        """A grill session with a NON-empty backlog -> B3's next-branch card
        fires, NOT the chart card. The single kanban-create call is the
        grill-loop continuation, not a chart card."""
        cg.add_node("root", "venture: TestVenture", topics=["testventure"])
        cg.add_node("decision", "an open decision")  # open -> backlog non-empty
        cgplugin._on_post_tool_call(tool_name="graph_frontier", session_id="s-grill")

        with mock.patch.object(cgplugin, "subprocess") as mock_subprocess:
            mock_subprocess.run.return_value = mock.MagicMock(
                returncode=0, stdout="t_next1", stderr=""
            )
            cgplugin._on_session_end(session_id="s-grill", completed=True)

        # exactly one create (B3's next-branch, guarded by the serialize list)
        # and it is NOT a chart card
        create_calls = _create_calls(mock_subprocess.run)
        self.assertEqual(len(create_calls), 1)
        cmd = create_calls[0].args[0]
        title = cmd[cmd.index("create") + 1]
        self.assertIn("[grill-loop]", title)
        self.assertNotIn("[chart]", title)
        # the chart card carries BOTH wayfinding skills; the next-branch card
        # carries decision-tree-grill — so the skill set distinguishes them
        self.assertNotEqual(_skill_values(cmd), ["wayfinding-auto", "wayfinder"])

    # ── no chart card when the session was NOT a grill session ────────────────
    def test_no_chart_card_when_session_did_not_touch_graph(self):
        """Open root + empty backlog exist, but the session never touched the
        graph (a chart session / unrelated PO work) -> NOT a grill session ->
        no chart card."""
        self._empty_backlog_grill(session_id="s-chart")
        # NOTE: no post_tool_call for s-other -> is_grill_session is False

        with mock.patch.object(cgplugin, "subprocess") as mock_subprocess:
            cgplugin._on_session_end(session_id="s-other", completed=True)
        mock_subprocess.run.assert_not_called()

    def test_no_chart_card_when_grill_already_complete(self):
        """Session touched the graph but the grill is already complete (root
        resolved) -> no open root -> not a mid-grill session -> no chart card."""
        root_id = cg.add_node("root", "venture: TestVenture", topics=["testventure"])
        resolved = cg.add_node("decision", "resolved decision")
        cg.resolve_node(resolved)
        cg.resolve_node(root_id)  # grill complete -> no open root
        cgplugin._on_post_tool_call(tool_name="graph_remaining", session_id="s-done")

        with mock.patch.object(cgplugin, "subprocess") as mock_subprocess:
            cgplugin._on_session_end(session_id="s-done", completed=True)
        mock_subprocess.run.assert_not_called()

    # ── fire-and-log: a card-creation failure does NOT crash the hook ────────
    def test_chart_card_creation_failure_does_not_raise(self):
        """The session-end hook must stay alive if the kanban CLI raises or
        exits non-zero (fire-and-log). The hook returns None either way and
        still drains the per-session tracker."""
        self._empty_backlog_grill(session_id="s-chart")

        with mock.patch.object(cgplugin, "subprocess") as mock_subprocess:
            mock_subprocess.run.side_effect = OSError("kanban CLI blew up")
            result = cgplugin._on_session_end(session_id="s-chart", completed=True)

        self.assertIsNone(result)
        self.assertNotIn("s-chart", cgplugin._GRAPH_TOUCHED_SESSIONS)

    # ── the card-creation helper directly (cmd shape) ────────────────────────
    def test_create_chart_card_helper_invokes_kanban_cli(self):
        """The helper builds the kanban-create cmd from a slug and runs it with
        the pinned env + both wayfinding skills."""
        with mock.patch.object(cgplugin, "subprocess") as mock_subprocess:
            mock_subprocess.run.return_value = mock.MagicMock(
                returncode=0, stdout="t_chart99", stderr=""
            )
            cgplugin._create_chart_card("acme")

        # guard lists first (no running card), then exactly one create
        create_calls = _create_calls(mock_subprocess.run)
        self.assertEqual(len(create_calls), 1)
        cmd = create_calls[0].args[0]
        env = create_calls[0].kwargs["env"]
        title = cmd[cmd.index("create") + 1]
        self.assertIn("[chart]", title)
        self.assertIn("acme", title)
        self.assertIn("chart the wayfinding map", title)
        self.assertEqual(_skill_values(cmd), ["wayfinding-auto", "wayfinder"])
        self.assertEqual(env["HERMES_KANBAN_BOARD"], "hermes-hq")
        self.assertTrue(env["HERMES_HOME"].endswith("startup"))

    # ── SERIALIZE GUARD (B3/B4 follow-up): one chart card per venture ────────
    #
    # Sibling of the grill-loop guard. Without it, concurrent grill session-ends
    # that each exhaust the backlog would each spawn a [chart] card → parallel
    # wayfinding-map sessions collide on the same venture. Fix: SERIALIZE —
    # before creating a [chart] card, check hermes-hq for a RUNNING one for the
    # same venture; if one exists, SKIP.

    def test_chart_card_skipped_when_chart_already_running(self):
        """SERIALIZE: when a RUNNING [chart] card for the same venture already
        exists on hermes-hq, _create_chart_card SKIPS — guard list fires, NO
        create call."""
        running_line = (
            "● t_chart1  running   product-owner        "
            "[chart] acme: chart the wayfinding map"
        )
        with mock.patch.object(cgplugin, "subprocess") as mock_subprocess:
            mock_subprocess.run.return_value = mock.MagicMock(
                returncode=0, stdout=running_line, stderr=""
            )
            result = cgplugin._create_chart_card("acme")

        self.assertIsNone(result)  # skipped → no card created
        self.assertEqual(
            len(_create_calls(mock_subprocess.run)), 0,
            "must not create a duplicate [chart] card when one is running",
        )

    def test_chart_card_created_when_no_running_duplicate(self):
        """SERIALIZE happy path: no running [chart] for the venture → the
        guard's list fires, THEN exactly one create fires (the card is made)."""
        with mock.patch.object(cgplugin, "subprocess") as mock_subprocess:
            mock_subprocess.run.return_value = mock.MagicMock(
                returncode=0, stdout="", stderr=""
            )
            cgplugin._create_chart_card("acme")

        self.assertEqual(len(_create_calls(mock_subprocess.run)), 1)

    def test_no_duplicate_chart_card_via_session_end(self):
        """The full on_session_end chart transition respects the guard: an empty
        backlog with a running [chart] card for the venture → no create."""
        self._empty_backlog_grill(session_id="s-chart")
        running_line = (
            "● t_chart1  running   product-owner        "
            "[chart] testventure: chart the wayfinding map"
        )
        with mock.patch.object(cgplugin, "subprocess") as mock_subprocess:
            mock_subprocess.run.return_value = mock.MagicMock(
                returncode=0, stdout=running_line, stderr=""
            )
            cgplugin._on_session_end(session_id="s-chart", completed=True)

        self.assertEqual(
            len(_create_calls(mock_subprocess.run)), 0,
            "session-end must not spawn a duplicate chart card",
        )


if __name__ == "__main__":
    unittest.main()
