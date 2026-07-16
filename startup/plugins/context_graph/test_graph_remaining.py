#!/usr/bin/env python3
"""
TDD for hermes-teams-8uc7 (A1) — graph_remaining(): the grill backlog query.

``graph_remaining()`` returns ALL open decision/fact nodes — the full set of
nodes still left to resolve (the grill backlog). It is the mechanical
done-check (empty == grill complete) and the branch-selection source.

Distinction from frontier():
  - frontier()         = open decision/fact with NO open blockers (the work
                         queue — what is actionable right now).
  - graph_remaining()  = ALL open decision/fact (the full backlog, INCLUDING
                         blocked ones). Empty == nothing left to grill.

Both are needed: a blocked node is NOT in the frontier (can't act on it yet)
but IS in graph_remaining (it is still unresolved — the grill is not done).
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

# ── path setup: import context_graph as a PACKAGE (mirrors grill tests) ──────
PLUGIN_DIR = Path(__file__).resolve().parent          # .../plugins/context_graph
PLUGINS_DIR = PLUGIN_DIR.parent                        # .../plugins
sys.path.insert(0, str(PLUGINS_DIR))

from context_graph import context_graph as cg  # noqa: E402  (core module)


class GraphRemainingTest(unittest.TestCase):
    """Unit tests for cg.graph_remaining() — the open-node backlog query."""

    def setUp(self):
        # Point the plugin at a FRESH temp DB so this never touches the real
        # startup/context_graph.db. init_db(db_path) overrides cg.DB_PATH.
        self._prior_db_path = cg.DB_PATH
        self._tmpdir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self._tmpdir.name, "graph.db")
        cg.init_db(db_path)
        self.addCleanup(self._restore_db)

    def _restore_db(self):
        # Restore the module-global DB_PATH so a later test in the same process
        # is not left pointing at the (now-deleted) temp DB.
        cg.DB_PATH = self._prior_db_path
        self._tmpdir.cleanup()

    # ── done-check semantics ────────────────────────────────────────────────
    def test_empty_graph_returns_empty_list(self):
        """An empty graph has nothing left to grill → graph_remaining() == []."""
        self.assertEqual(cg.graph_remaining(), [])

    # ── backlog membership ──────────────────────────────────────────────────
    def test_returns_open_decision_and_fact_excludes_resolved_root_term(self):
        """The backlog is exactly the open decision/fact nodes: the resolved
        decision, the root container, and term nodes are all excluded."""
        cg.add_node("root", "venture: TestVenture")
        open_dec_id = cg.add_node("decision", "open decision")
        open_fact_id = cg.add_node("fact", "open fact")
        resolved_dec_id = cg.add_node("decision", "resolved decision")
        cg.resolve_node(resolved_dec_id)  # resolved → not in the backlog
        cg.add_node("term", "a term")     # terms are definitions, not backlog

        remaining = cg.graph_remaining()
        remaining_ids = {n["id"] for n in remaining}

        # the backlog is exactly the two open decision/fact nodes
        self.assertEqual(remaining_ids, {open_dec_id, open_fact_id})
        # excludes the resolved decision, the root, and the term
        self.assertNotIn(resolved_dec_id, remaining_ids)
        # every returned node is open + decision/fact
        for n in remaining:
            self.assertEqual(n["status"], "open")
            self.assertIn(n["type"], ("decision", "fact"))
        # shape: dicts carrying id/type/title/status (like frontier/pull)
        for n in remaining:
            for key in ("id", "type", "title", "status"):
                self.assertIn(key, n)

    # ── the load-bearing distinction from frontier() ───────────────────────
    def test_includes_blocked_nodes_unlike_frontier(self):
        """graph_remaining is the FULL backlog: a node blocked by an open
        blocker is NOT in frontier() (not actionable) but IS in
        graph_remaining() (still unresolved). Blocked != done."""
        root_id = cg.add_node("root", "venture: TestVenture")
        blocked_dec_id = cg.add_node("decision", "blocked decision")
        # an open decision blocks blocked_dec → blocked_dec is not actionable
        blocker_id = cg.add_node("decision", "the blocker")
        cg.add_edge(blocker_id, blocked_dec_id, "blocks")

        remaining_ids = {n["id"] for n in cg.graph_remaining()}
        frontier_ids = {n["id"] for n in cg.frontier()}

        # blocked_dec is still unresolved → in the backlog
        self.assertIn(
            blocked_dec_id, remaining_ids,
            "blocked-but-open node is in graph_remaining (the backlog)",
        )
        self.assertIn(blocker_id, remaining_ids)
        # …but it is NOT in the frontier (not actionable while blocker is open)
        self.assertNotIn(
            blocked_dec_id, frontier_ids,
            "blocked node is excluded from frontier (not actionable)",
        )
        self.assertIn(
            blocker_id, frontier_ids,
            "the open blocker itself is actionable → in frontier",
        )
        # root is in neither
        self.assertNotIn(root_id, remaining_ids)
        self.assertNotIn(root_id, frontier_ids)


if __name__ == "__main__":
    unittest.main()
