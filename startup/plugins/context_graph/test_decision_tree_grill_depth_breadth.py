#!/usr/bin/env python3
"""
TDD structural contract for hermes-teams-ykqt — Grill depth/breadth discipline.

``decision-tree-grill`` (the 3a7q substrate) WRAPS the official grilling skill
for HOW to ask. This ticket (ykqt) adds the discipline for WHAT to cover and
WHEN to stop — three WRAPPER disciplines layered on top, reinventing none of
grilling's interview mechanics:

  (1) Multi-lens coverage — every venture is grilled across seven lenses:
      desirability/demand, viability/monetization, feasibility/tech,
      usability, differentiation/defensibility, distribution/GTM,
      risk/kill-switches. This is the breadth guard (grilling walks each
      branch; the lenses make sure no whole category is silently skipped).
  (2) Per-resolved-node decomposition template — each ANSWERED decision is
      forked via four fixed prompts — (a) makes possible, (b) makes necessary,
      (c) makes risky, (d) assumes — yielding up to 4 child nodes. This is the
      depth guard (one resolved decision spawns the decisions it implies).
  (3) Loop-until-dry exhaustion gate — BEFORE ``GRILL COMPLETE`` fires, a
      fork-pass over EVERY resolved node must yield ZERO new nodes. This is the
      stop guard (no early convergence; the tree is provably exhaustive).

No numeric node/depth caps are baked into the skill — any bound (turn budget,
monitor, max nodes) is imposed EXTERNALLY by the test harness. The
decomposition template's "up to 4" is the per-node generation SHAPE (four
prompts), NOT a global cap on the tree.

Seam (per the bead):
  (1) skill YAML frontmatter parses;
  (2) structural assertions on the skill body — names all 7 lenses, contains
      the decomposition template (makes possible / necessary / risky / assumes
      -> up to 4 children), contains the loop-until-dry exhaustion gate, and
      contains NO baked-in numeric node/depth caps.

The bead's live-run acceptance criteria (N>20 nodes spanning multiple lenses;
GRILL COMPLETE only after an exhaustion-verified fork-pass) are verified by a
LIVE grill run, not by this unit seam — this file guards the CONTRACT that makes
those outcomes possible.
"""

import sys
import unittest
from pathlib import Path

# ── path setup: same dir conventions as test_decision_tree_grill.py ──────────
PLUGIN_DIR = Path(__file__).resolve().parent          # .../plugins/context_graph

# ── the SKILL.md under contract ──────────────────────────────────────────────
# PLUGIN_DIR.parent.parent == .../startup
SKILL_PATH = (
    PLUGIN_DIR.parent.parent
    / "profiles" / "product-owner" / "skills" / "coordination"
    / "decision-tree-grill" / "SKILL.md"
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
    if len(parts) < 3:
        return "", text
    return parts[1].strip(), parts[2].strip()


def _skill_text():
    return SKILL_PATH.read_text(encoding="utf-8")


# The seven lenses the depth/breadth discipline must cover. Each entry is a
# tuple of acceptable distinctive tokens (case-insensitive) — at least one must
# appear in the body. This is flexible enough to survive rewording but strict
# enough that a skill which silently drops a whole category fails.
SEVEN_LENSES = [
    ("desirability", "demand"),              # 1. is it wanted?
    ("viability", "monetization"),           # 2. can it make money?
    ("feasibility",),                        # 3. can it be built? (tech)
    ("usability",),                          # 4. can humans use it?
    ("differentiation", "defensibility"),    # 5. can it be copied / defended?
    ("distribution", "gtm"),                 # 6. how does it reach users?
    ("risk", "kill-switch", "kill switch", "killswitch"),  # 7. what kills it?
]

# The four fixed decomposition prompts — each resolved decision is forked via
# these, yielding up to 4 child nodes.
DECOMPOSITION_PROMPTS = [
    "makes possible",
    "makes necessary",
    "makes risky",
    "assumes",
]


# =============================================================================
# (1) FRONTMATTER CONTRACT
# =============================================================================

class FrontmatterContractTest(unittest.TestCase):
    """The skill's YAML frontmatter must parse and still declare name + desc
    after the depth/breadth disciplines are layered in."""

    def setUp(self):
        self.fm, self.body = _split_frontmatter(_skill_text())

    def test_skill_file_exists(self):
        self.assertTrue(SKILL_PATH.exists(),
                        "SKILL.md not found at %s" % SKILL_PATH)

    def test_frontmatter_present_and_closed(self):
        self.assertTrue(self.fm, "SKILL.md must start with a --- frontmatter block")

    def test_frontmatter_declares_name(self):
        self.assertIn("name:", self.fm)
        self.assertIn("decision-tree-grill", self.fm)

    def test_frontmatter_declares_description(self):
        self.assertIn("description:", self.fm)


# =============================================================================
# (2a) DISCIPLINE 1 — multi-lens coverage (the breadth guard)
# =============================================================================

class MultiLensCoverageTest(unittest.TestCase):
    """The skill must name ALL seven lenses so no whole category is silently
    skipped. grilling decides HOW to walk each lens; this discipline defines
    WHAT must be covered."""

    def setUp(self):
        _fm, self.body = _split_frontmatter(_skill_text())
        self.lower = self.body.lower()

    def test_names_all_seven_lenses(self):
        missing = []
        for tokens in SEVEN_LENSES:
            if not any(t in self.lower for t in tokens):
                missing.append(tokens)
        self.assertEqual(
            missing, [],
            "skill body must name all 7 grill lenses; missing: %r" % missing,
        )

    def test_has_a_designated_lenses_section(self):
        """The lenses are not incidental mentions — the skill must designate a
        coverage section (a heading or named list of the lenses)."""
        # A heading that introduces the lenses as a named discipline.
        lines = self.body.splitlines()
        has_lens_heading = any(
            ("lens" in ln.lower() or "lenses" in ln.lower()
             or "coverage" in ln.lower())
            and ln.lstrip().startswith("#")
            for ln in lines
        )
        self.assertTrue(
            has_lens_heading,
            "skill must have a designated heading naming the lenses "
            "(e.g. '## Multi-lens coverage')",
        )


# =============================================================================
# (2b) DISCIPLINE 2 — per-resolved-node decomposition template (depth guard)
# =============================================================================

class DecompositionTemplateTest(unittest.TestCase):
    """Each ANSWERED decision is forked via four fixed prompts (makes possible
    / necessary / risky / assumes), yielding up to 4 child nodes."""

    def setUp(self):
        _fm, body = _split_frontmatter(_skill_text())
        self.lower = body.lower()

    def test_contains_all_four_decomposition_prompts(self):
        missing = [p for p in DECOMPOSITION_PROMPTS if p not in self.lower]
        self.assertEqual(
            missing, [],
            "skill must contain the 4 decomposition prompts "
            "(makes possible / necessary / risky / assumes); missing: %r" % missing,
        )

    def test_decomposition_applies_per_resolved_node(self):
        """The template fires on each ANSWERED/RESOLVED decision — not once,
        not on the root, but per resolved decision node."""
        self.assertTrue(
            ("resolved" in self.lower or "answered" in self.lower),
            "decomposition must be tied to resolved/answered decision nodes",
        )

    def test_decomposition_yields_up_to_four_child_nodes(self):
        """The four prompts yield up to 4 child nodes (the template SHAPE — not
        a global cap). The skill must state the up-to-4 bound."""
        normalized = self.lower.replace("-", " ")
        self.assertTrue(
            ("up to 4" in normalized or "up to four" in self.lower),
            "decomposition template must state it yields up to 4 child nodes",
        )


# =============================================================================
# (2c) DISCIPLINE 3 — loop-until-dry exhaustion gate (stop guard)
# =============================================================================

class ExhaustionGateTest(unittest.TestCase):
    """BEFORE ``GRILL COMPLETE`` fires, a fork-pass over every resolved node
    must yield ZERO new nodes. No early convergence."""

    def setUp(self):
        _fm, body = _split_frontmatter(_skill_text())
        self.lower = body.lower()

    def test_has_exhaustion_gate(self):
        """The skill must name an exhaustion / loop-until-dry gate."""
        self.assertTrue(
            "exhaustion" in self.lower or "until-dry" in self.lower
            or "until dry" in self.lower or "loop-until-dry" in self.lower,
            "skill must name a loop-until-dry / exhaustion gate",
        )

    def test_gate_runs_a_fork_pass_over_resolved_nodes(self):
        """The gate is a FORK-PASS over every resolved node — re-applying the
        decomposition to check whether anything new is still generated."""
        normalized = self.lower.replace("-", " ")
        self.assertTrue(
            ("fork pass" in normalized or "fork-pass" in self.lower
             or "forkpass" in normalized),
            "exhaustion gate must run a fork-pass over the resolved nodes",
        )

    def test_gate_requires_zero_new_nodes(self):
        """The fork-pass must yield ZERO new nodes before the grill is dry."""
        self.assertTrue(
            ("zero new nodes" in self.lower or "no new nodes" in self.lower
             or "yields nothing" in self.lower
             or "yields no new" in self.lower
             or "produces no new" in self.lower),
            "exhaustion gate must require the fork-pass to yield zero new nodes",
        )

    def test_gate_is_required_before_grill_complete(self):
        """The exhaustion gate is a PREREQUISITE for GRILL COMPLETE — it must
        run BEFORE completion is signalled, tied to the gate (not just any
        incidental 'before signalling' elsewhere in the skill)."""
        self.assertIn("grill complete", self.lower)
        # The gate must be tied specifically to the completion check.
        self.assertTrue(
            ("before grill complete" in self.lower
             or "prior to grill complete" in self.lower
             or "gate must pass before" in self.lower
             or "exhaustion gate passes" in self.lower
             or "grill complete must not fire until" in self.lower
             or "until the exhaustion gate" in self.lower),
            "exhaustion gate must be required BEFORE GRILL COMPLETE "
            "(tied to the gate, not an incidental 'before signalling')",
        )


# =============================================================================
# (2d) NO BAKED-IN CAPS — depth/breadth are uncapped
# =============================================================================

class NoBakedInCapsTest(unittest.TestCase):
    """No numeric node/depth/breadth cap baked into the skill. The grill aims
    for the FULL tree; any bound is imposed externally. The decomposition
    template's per-node 'up to 4' is generation SHAPE, not a global cap, and is
    explicitly allowed."""

    def setUp(self):
        _fm, body = _split_frontmatter(_skill_text())
        self.lower = body.lower()

    def test_no_baked_in_depth_or_breadth_cap(self):
        """No baked-in global depth/breadth/node cap that would terminate the
        grill early."""
        forbidden = [
            "depth cap", "max depth", "depth limit",
            "breadth cap", "max breadth", "breadth limit",
            "max nodes", "node cap", "nodes cap",
            "max children", "max branches",
            "5-pass", "5 pass", "n-pass limit",
        ]
        found = [bad for bad in forbidden if bad in self.lower]
        self.assertEqual(
            found, [],
            "skill must not bake a global depth/breadth/node cap (impose "
            "externally for tests); found forbidden phrases: %r" % found,
        )


if __name__ == "__main__":
    unittest.main()
