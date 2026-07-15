#!/usr/bin/env python3
"""
TDD contract + stateless-recovery test for hermes-teams-3a7q — Grill substrate.

``decision-tree-grill`` is a SUBSTRATE that WRAPS the official grilling skill
(``shared-skills/mattpocock/grilling/SKILL.md``). It must NOT reinvent the
interview mechanics — grilling owns seed-one-question / walk-each-branch /
fork-as-answers-reshape. The substrate adds exactly three things on top:

  (a) graph-as-storage (term nodes replace CONTEXT.md),
  (b) a MANDATORY stateless recovery protocol (the FIRST action of every
      activation), and
  (c) an objective done-check + anti-fake rules.

The bug this fixes (R26): a fresh history=0 PO session lost the root_id and
could not reconstruct the tree (``graph_tree``-without-root error). Recovery =
``graph_pull('<slug>')`` -> filter ``type=root`` -> ``graph_tree(root)`` ->
``graph_frontier()`` is now the FIRST action of every activation; rootless
``graph_tree`` / ``graph_stats`` are forbidden.

Seam (per the bead):
  (1) skill YAML frontmatter parses;
  (2) structural assertions on the skill body — NO reinvented Loop / seed-count /
      fork-cap, HAS the mandatory-recovery protocol, explicitly defers interview
      mechanics to grilling;
  (3) a python recovery test: seed a root + a decision via the context_graph
      plugin, then simulate a fresh session by calling ``graph_pull('<slug>')``
      -> find type=root -> ``graph_tree(root)`` succeeds.

The structural cases (2) FAIL on the pre-rewrite SKILL.md (it reinvents a
``## Loop (tool calls)`` walk) and PASS once the skill wraps grilling. The
recovery case (3) is the integration proof that the recovery the skill
mandates is actually possible with the plugin — and a regression guard for R26.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# ── path setup: import context_graph as a PACKAGE (mirrors loop_engine tests) ─
PLUGIN_DIR = Path(__file__).resolve().parent          # .../plugins/context_graph
PLUGINS_DIR = PLUGIN_DIR.parent                        # .../plugins
sys.path.insert(0, str(PLUGINS_DIR))

from context_graph import context_graph as cg       # noqa: E402  (core module)
from context_graph import tools as cg_tools          # noqa: E402  (agent handlers)

# ── the SKILL.md under contract ──────────────────────────────────────────────
# PLUGIN_DIR.parent.parent == .../startup
SKILL_PATH = (
    PLUGIN_DIR.parent.parent
    / "profiles" / "product-owner" / "skills" / "coordination"
    / "decision-tree-grill" / "SKILL.md"
).resolve()

# The official skill the substrate wraps (READ-ONLY reference — wrap, never edit).
OFFICIAL_GRILLING = (
    PLUGIN_DIR.parent.parent.parent
    / "shared-skills" / "mattpocock" / "grilling" / "SKILL.md"
).resolve()


def _split_frontmatter(text):
    """Split a SKILL.md into (frontmatter_str, body_str).

    Frontmatter is the YAML block between the first two ``---`` fences. Returns
    ("", text) if there is no frontmatter. Minimal parser — pyyaml is not
    installed in this env, so callers assert on the raw frontmatter string.
    """
    if not text.startswith("---"):
        return "", text
    parts = text.split("---", 2)
    # parts[0] == "" (before the opening ---), parts[1] == frontmatter,
    # parts[2] == body. Need at least 3 segments for a closed frontmatter block.
    if len(parts) < 3:
        return "", text
    return parts[1].strip(), parts[2].strip()


def _skill_text():
    return SKILL_PATH.read_text(encoding="utf-8")


# =============================================================================
# (1) FRONTMATTER CONTRACT
# =============================================================================

class FrontmatterContractTest(unittest.TestCase):
    """The skill's YAML frontmatter must parse and declare name + description."""

    def setUp(self):
        self.fm, self.body = _split_frontmatter(_skill_text())

    def test_frontmatter_present_and_closed(self):
        self.assertTrue(self.fm, "SKILL.md must start with a --- frontmatter block")

    def test_frontmatter_declares_name(self):
        self.assertIn("name:", self.fm)
        self.assertIn("decision-tree-grill", self.fm)

    def test_frontmatter_declares_description(self):
        self.assertIn("description:", self.fm)


# =============================================================================
# (2) STRUCTURAL CONTRACT — wraps grilling, no reinvented mechanics, recovery
# =============================================================================

class GrillSkillStructuralContractTest(unittest.TestCase):
    """The skill body must wrap grilling (not reinvent it) and carry the
    mandatory stateless recovery protocol + objective done-check."""

    def setUp(self):
        _fm, self.text = _split_frontmatter(_skill_text())
        self.lower = self.text.lower()

    # ── NO reinvented interview mechanics ───────────────────────────────────
    def test_no_reinvented_loop_section(self):
        """The pre-rewrite skill had a ``## Loop (tool calls)`` section with a
        reinvented walk (``while graph_frontier().count > 0:``). Wrapping
        grilling means that section is GONE — grilling owns the walk."""
        # No heading line that introduces a reinvented walk loop.
        for line in self.text.splitlines():
            stripped = line.strip()
            self.assertFalse(
                stripped.startswith("## Loop"),
                "skill must not have a reinvented '## Loop' section "
                "(grilling owns the interview walk): %r" % stripped,
            )

    def test_no_reinvented_walk_pseudocode(self):
        """The reinvented ``while graph_frontier().count > 0:`` pseudocode must
        be gone — that is grilling's walk, reimplemented."""
        self.assertNotIn(
            "while graph_frontier", self.text,
            "skill must not reimplement the grill walk as a while-loop; "
            "grilling owns walk-the-frontier",
        )

    def test_no_baked_seed_count_or_node_cap(self):
        """No baked-in numeric seed count or node/turn cap in the skill. The
        grill is uncapped by design; any bound is imposed externally."""
        # A literal "seed N nodes" / "seed-count" style cap.
        self.assertNotIn(
            "seed-count", self.lower,
            "skill must not bake a seed count",
        )
        # A turn/pass/node budget cap baked into the skill text.
        for bad in ("5-pass", "5 pass", "turn cap", "node cap", "max_nodes"):
            self.assertNotIn(
                bad.lower(), self.lower,
                "skill must not bake a %r cap (impose externally for tests)" % bad,
            )

    # ── HAS the mandatory stateless recovery protocol ───────────────────────
    def test_has_mandatory_stateless_recovery_protocol(self):
        """Recovery (pull -> root -> tree -> frontier) is the FIRST action of
        every activation. The skill must spell out the sequence."""
        self.assertIn("graph_pull", self.text)
        self.assertIn("graph_tree", self.text)
        self.assertIn("graph_frontier", self.text)
        # Recovery is the first action of every activation.
        self.assertTrue(
            "first action" in self.lower or "first step" in self.lower,
            "skill must state recovery is the FIRST action of every activation",
        )
        self.assertIn(
            "recovery", self.lower,
            "skill must name the stateless recovery protocol",
        )

    def test_root_recovered_by_filtering_pull_to_type_root(self):
        """The R26 fix: the root is recovered deterministically by filtering
        graph_pull('<slug>') to type=root — not from in-session memory."""
        # The skill must instruct filtering graph_pull results by type=root.
        normalized = self.lower.replace(" ", "")
        self.assertIn(
            "type=root", normalized,
            "skill must instruct filtering graph_pull('<slug>') to type=root "
            "to recover the root deterministically",
        )

    def test_rootless_graph_tree_and_stats_are_forbidden(self):
        """A rootless graph_tree / graph_stats is the R26 error. The skill must
        forbid calling them without first recovering the root."""
        self.assertIn("rootless", self.lower)
        self.assertTrue(
            "forbidden" in self.lower or "must not" in self.lower
            or "never" in self.lower,
            "skill must forbid rootless graph_tree/graph_stats",
        )

    # ── explicitly defers interview mechanics to grilling ───────────────────
    def test_wraps_and_defers_to_official_grilling(self):
        """The skill must WRAP the official grilling skill and explicitly defer
        the interview mechanics to it (not reinvent them)."""
        self.assertIn("grilling", self.lower)
        # Explicit deferral language — grilling owns the interview.
        self.assertTrue(
            "defers" in self.lower or "defer " in self.lower
            or "owns the interview" in self.lower
            or "does not reinvent" in self.lower
            or "never reinvent" in self.lower
            or "wraps" in self.lower,
            "skill must explicitly defer interview mechanics to grilling",
        )

    def test_official_grilling_skill_exists(self):
        """Sanity: the official grilling skill the substrate wraps is present
        (READ-ONLY — wrap, never modify)."""
        self.assertTrue(OFFICIAL_GRILLING.exists(),
                        "official grilling skill not found at %s" % OFFICIAL_GRILLING)

    # ── term nodes replace CONTEXT.md + objective done-check ─────────────────
    def test_term_nodes_replace_context_md(self):
        """Terms live as graph term nodes; the skill must NOT produce CONTEXT.md."""
        self.assertIn("term", self.lower)
        self.assertIn(
            "context.md", self.lower,
            "skill must address CONTEXT.md (state it is NOT produced)",
        )

    def test_done_check_is_three_part_objective_gate(self):
        """GRILL COMPLETE fires only on frontier-empty + every decision
        VB-answered + >=1 term. All three, objective."""
        self.assertIn("graph_frontier", self.text)
        self.assertIn("VB:", self.text)
        self.assertIn("term", self.lower)


# =============================================================================
# (3) STATELESS RECOVERY — the R26 regression guard + integration proof
# =============================================================================

class StatelessRecoveryTest(unittest.TestCase):
    """A fresh session (no in-memory root_id) recovers root + tree + frontier
    deterministically via the context_graph plugin. This is the R26 fix.

    Seeds a root + a decision (decision blocks root), then simulates a FRESH
    session by going ONLY through graph_pull('<slug>') -> filter type=root ->
    graph_tree(root) -> graph_frontier(). No in-memory root_id is carried over
    — the graph alone reconstructs the tree.
    """

    SLUG = "testventure-recovery-3a7q"

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

    def _add_node(self, node_type, title, **kw):
        return json.loads(
            cg_tools.graph_add_node({"node_type": node_type, "title": title, **kw})
        )

    def _add_edge(self, source_id, target_id, edge_type):
        return json.loads(cg_tools.graph_add_edge(
            {"source_id": source_id, "target_id": target_id, "edge_type": edge_type}))

    def _pull(self, topic):
        return json.loads(cg_tools.graph_pull({"topic": topic}))

    def _tree(self, root_id):
        return json.loads(cg_tools.graph_tree({"root_id": root_id}))

    def _frontier(self):
        return json.loads(cg_tools.graph_frontier({}))

    def test_fresh_session_recovers_root_tree_and_frontier(self):
        """The R26 scenario: seed a tree, drop all in-memory state, recover via
        graph_pull('<slug>') -> type=root -> graph_tree(root) -> graph_frontier()."""
        # ── session 1: seed a root + a decision that blocks it ───────────────
        root = self._add_node("root", "venture: TestVenture",
                              content="brief-id: b-1", topics=[self.SLUG])
        root_id = root["node_id"]
        dec = self._add_node("decision", "What is the pricing model?",
                             source="PO", topics=[self.SLUG])
        dec_id = dec["node_id"]
        self._add_edge(dec_id, root_id, "blocks")

        # ── session 2 (FRESH): no root_id in memory — recover from the graph ─
        # Step 1: graph_pull('<slug>') returns every node for the venture.
        pull = self._pull(self.SLUG)
        pulled_ids = {n["id"] for n in pull["nodes"]}
        self.assertIn(root_id, pulled_ids)
        self.assertIn(dec_id, pulled_ids)

        # Step 2: filter to type=root — the root is recovered DETERMINISTICALLY.
        roots = [n for n in pull["nodes"] if n["type"] == "root"]
        self.assertEqual(len(roots), 1, "exactly one root recoverable for the slug")
        self.assertEqual(roots[0]["id"], root_id)

        # Step 3: graph_tree(root) succeeds and contains both nodes — the tree
        # is reconstructed WITHOUT an in-memory root_id (the R26 fix).
        tree = self._tree(roots[0]["id"])["tree"]
        tree_ids = {n["id"] for n in tree}
        self.assertIn(root_id, tree_ids)
        self.assertIn(dec_id, tree_ids)

        # Step 4: graph_frontier() exposes the still-open decision as the work
        # queue — the fresh session continues exactly where it left off.
        frontier = self._frontier()["frontier"]
        frontier_ids = {n["id"] for n in frontier}
        self.assertIn(dec_id, frontier_ids, "open decision must be in the frontier")
        # The root is the container, never in the frontier.
        self.assertNotIn(root_id, frontier_ids)

    def test_root_recovered_when_multiple_nodes_tagged(self):
        """Recovery is robust to a busy graph: many nodes tagged with the slug,
        but filtering type=root still yields exactly the one root."""
        root = self._add_node("root", "venture: BusyVenture", topics=[self.SLUG])
        root_id = root["node_id"]
        # Several decisions + facts + a term, all tagged with the slug.
        for i in range(4):
            n = self._add_node("decision", f"q{i}", topics=[self.SLUG])
            self._add_edge(n["node_id"], root_id, "blocks")
        self._add_node("fact", "a looked-up fact", source="lookup", topics=[self.SLUG])
        self._add_node("term", "Widget", content="VB: a thingamajig",
                       source="VB", topics=[self.SLUG])

        pull = self._pull(self.SLUG)
        roots = [n for n in pull["nodes"] if n["type"] == "root"]
        self.assertEqual(len(roots), 1)
        self.assertEqual(roots[0]["id"], root_id)

    def test_rootless_slug_yields_no_root(self):
        """If graph_pull('<slug>') returns no type=root node, the grill has not
        been seeded yet — recovery correctly reports 'no root' (seed it). This
        is the non-error counterpart to R26: no silent root synthesis."""
        pull = self._pull("never-seeded-slug-3a7q")
        roots = [n for n in pull["nodes"] if n["type"] == "root"]
        self.assertEqual(roots, [], "an unseeded slug has no root to recover")


if __name__ == "__main__":
    unittest.main()
