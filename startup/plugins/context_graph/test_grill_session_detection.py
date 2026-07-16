#!/usr/bin/env python3
"""
TDD for hermes-teams-xnkk (B2) — grill-session detection in on_session_end.

A grill session = BOTH:
  1. the session touched the graph (>=1 graph_* tool call), tracked via the
     post_tool_call hook over the session's lifetime, AND
  2. an open grill root exists (a node with type=root AND status=open) — a
        grill in progress. A grill that is GRILL COMPLETE has its root
        resolved → no open root → NOT a mid-grill session.

Non-grill sessions (a chart session, unrelated PO work, or a grill already
complete) must NOT be detected. This is DETECTION ONLY — B3/B4 act on a True
result; B2 decides grill-or-not and returns None.

WHY post_tool_call: Hermes fires on_session_end with kwargs {session_id,
completed, interrupted, model, platform, reason (and sometimes task_id /
turn_id / api_request_id)} — none of which carry the session's tool-call list.
So "touched the graph" is tracked by watching post_tool_call (which fires for
every tool call with tool_name + session_id) for graph_* tools. This mirrors
the shipped disk-cleanup plugin's track-in-post_tool_call / drain-in-
on_session_end pattern.
"""

import os
import sys
import tempfile
import unittest
import logging
from pathlib import Path

# ── path setup: import context_graph as a PACKAGE (mirrors grill tests) ──────
PLUGIN_DIR = Path(__file__).resolve().parent          # .../plugins/context_graph
PLUGINS_DIR = PLUGIN_DIR.parent                        # .../plugins
sys.path.insert(0, str(PLUGINS_DIR))

import context_graph as cgplugin  # noqa: E402  (package: hook + detection)
from context_graph import context_graph as cg  # noqa: E402  (core graph module)


class GrillSessionDetectionTest(unittest.TestCase):
    """B2: the on_session_end hook detects mid-grill sessions."""

    def setUp(self):
        # Point the plugin at a FRESH temp DB so this never touches the real
        # startup/context_graph.db. init_db(db_path) overrides cg.DB_PATH.
        self._prior_db_path = cg.DB_PATH
        self._tmpdir = tempfile.TemporaryDirectory()
        cg.init_db(os.path.join(self._tmpdir.name, "graph.db"))
        # reset the module-level session tracker between tests
        cgplugin._GRAPH_TOUCHED_SESSIONS.clear()
        self.addCleanup(self._restore)

    def _restore(self):
        cgplugin._GRAPH_TOUCHED_SESSIONS.clear()
        cg.DB_PATH = self._prior_db_path
        self._tmpdir.cleanup()

    # ── the post_tool_call tracker (the "touched the graph" signal) ──────────
    def test_post_tool_call_records_graph_tool_sessions(self):
        """A graph_* tool call marks the session as having touched the graph."""
        cgplugin._on_post_tool_call(tool_name="graph_add_node", session_id="s1")
        self.assertIn("s1", cgplugin._GRAPH_TOUCHED_SESSIONS)

    def test_post_tool_call_records_all_graph_tools(self):
        """Every registered graph_* tool counts as touching the graph."""
        for name in (
            "graph_frontier", "graph_pull", "graph_context", "graph_add_edge",
            "graph_resolve_node", "graph_tree", "graph_stats", "graph_remaining",
        ):
            cgplugin._on_post_tool_call(tool_name=name, session_id="s-all")
        self.assertIn("s-all", cgplugin._GRAPH_TOUCHED_SESSIONS)

    def test_post_tool_call_ignores_non_graph_tools(self):
        """A non-graph tool call does NOT mark the session as graph-touched."""
        cgplugin._on_post_tool_call(tool_name="write_file", session_id="s1")
        cgplugin._on_post_tool_call(tool_name="bash", session_id="s1")
        cgplugin._on_post_tool_call(tool_name="graph_frontier", session_id="other")
        self.assertNotIn("s1", cgplugin._GRAPH_TOUCHED_SESSIONS)
        self.assertIn("other", cgplugin._GRAPH_TOUCHED_SESSIONS)

    # ── B2 acceptance (a): grill session DETECTED (touched + open root) ──────
    def test_grill_session_detected_when_graph_touched_and_open_root(self):
        """A session that touched the graph AND has an open root → grill."""
        cg.add_node("root", "venture: TestVenture")  # open root → grill in progress
        cgplugin._on_post_tool_call(tool_name="graph_frontier", session_id="s-grill")
        self.assertTrue(cgplugin.is_grill_session("s-grill"))

    # ── B2 acceptance (b): non-grill sessions NOT detected ───────────────────
    def test_not_grill_when_session_did_not_touch_graph(self):
        """Open root exists but the session never touched the graph → not grill.

        (A chart session or unrelated PO work — even with a grill open
        elsewhere — is not a grill session.)"""
        cg.add_node("root", "venture: TestVenture")
        # no post_tool_call for this session
        self.assertFalse(cgplugin.is_grill_session("s-chart"))

    def test_not_grill_when_no_open_root(self):
        """Session touched the graph but the grill is already complete (root
        resolved) → not a mid-grill session."""
        root_id = cg.add_node("root", "venture: TestVenture")
        cg.resolve_node(root_id)  # grill complete → no open root
        cgplugin._on_post_tool_call(tool_name="graph_remaining", session_id="s-done")
        self.assertFalse(cgplugin.is_grill_session("s-done"))

    def test_not_grill_when_no_root_at_all(self):
        """Session touched the graph but no grill root exists → not grill."""
        cgplugin._on_post_tool_call(tool_name="graph_frontier", session_id="s-noroot")
        self.assertFalse(cgplugin.is_grill_session("s-noroot"))

    def test_not_grill_when_empty_session_id(self):
        """No session_id → can't be a grill session."""
        cg.add_node("root", "venture: TestVenture")
        self.assertFalse(cgplugin.is_grill_session(""))

    # ── the hook itself: detection is observable + returns None ──────────────
    def test_hook_returns_none_and_drains_tracker(self):
        """on_session_end always returns None (B3/B4 act; B2 detects only).
        It drains the per-session tracker on the way out (mirrors disk-cleanup)."""
        cg.add_node("root", "venture: TestVenture")
        cgplugin._on_post_tool_call(tool_name="graph_frontier", session_id="s-x")
        result = cgplugin._on_session_end(session_id="s-x", completed=True)
        self.assertIsNone(result)
        # tracker drained after session end
        self.assertNotIn("s-x", cgplugin._GRAPH_TOUCHED_SESSIONS)

    def test_hook_logs_grill_detection_at_info(self):
        """When a mid-grill session is detected, the hook logs it at INFO.

        NOTE: a sibling test module calls ``logging.disable(CRITICAL)`` at
        import time, which globally suppresses records before they reach any
        handler. We locally lift that disable so ``assertLogs`` can observe the
        INFO line, then restore the prior level. The detection *decision* is
        verified directly via ``is_grill_session`` above; this test only proves
        the operational INFO signal fires."""
        cg.add_node("root", "venture: TestVenture")
        cgplugin._on_post_tool_call(tool_name="graph_frontier", session_id="s-log")
        prior_disable = logging.root.manager.disable
        logging.disable(0)  # re-enable so assertLogs can capture
        try:
            with self.assertLogs("context_graph", level="INFO") as cm:
                cgplugin._on_session_end(session_id="s-log")
            self.assertTrue(
                any("grill" in m.lower() for m in cm.output),
                f"expected a grill-detection log line, got: {cm.output}",
            )
        finally:
            logging.disable(prior_disable)


if __name__ == "__main__":
    unittest.main()
