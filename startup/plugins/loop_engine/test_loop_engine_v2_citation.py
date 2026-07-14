#!/usr/bin/env python3
"""
TDD tests for loop_engine v2 — the citation primitive (T1, bead hermes-teams-8w2).

This is the KEYSTONE of the fact-based-loop layer: ONE shared representation
for facts used by BOTH discover (input grounding) AND the evaluator (output
evidence). The engine enforces STRUCTURE only (the independent verifier card
re-opens citations; matching the existing trust model).

Scope under test (the public seams later beads B3/B4/B9 call):
  * schemas.SEED_ARTIFACT_TYPES / known_artifact_types() / register_artifact_type()
  * schemas.Citation / schemas.Claim          (importable, typed building blocks)
  * tools.validate_citation / tools.validate_claim
    (plain-dict structure-validators, matching _validate / _validate_dod_artifact)

The hard-fail primitive — a MATERIAL claim with zero citations is invalid — is
the "facts not self-claim" gate. Wiring it into replan is B3/B4's job; here we
prove the primitive raises a structured error.

These are pure unit tests (no kanban DB, no provider) — they validate the
structure of dicts off the wire (the real shape the board / run.metadata JSON
yields), mirroring the dict-seam the existing _validate* functions use.
"""

import json
import sys
import unittest
from dataclasses import asdict
from pathlib import Path

# -- Path setup (mirror test_loop_engine.py: import loop_engine as a PACKAGE) ----
PLUGIN_DIR = Path(__file__).resolve().parent
PLUGINS_DIR = PLUGIN_DIR.parent
sys.path.insert(0, str(PLUGINS_DIR))

import loop_engine  # noqa: E402  (package; register() callable)
from loop_engine import schemas as le_schemas  # noqa: E402
from loop_engine import tools as le_tools  # noqa: E402


# =============================================================================
# validate_citation — the Citation{artifact_type, locator, quote?} struct
# =============================================================================

class TestValidateCitation(unittest.TestCase):
    """validate_citation(data) -> error-string | None. None == valid struct."""

    def test_accepts_every_seed_artifact_type(self):
        """The full open-enum seed set is valid when paired with a locator."""
        for atype in sorted(le_schemas.SEED_ARTIFACT_TYPES):
            err = le_tools.validate_citation(
                {"artifact_type": atype, "locator": "calc.py:10"})
            self.assertIsNone(
                err, f"seed artifact_type {atype!r} rejected: {err}")

    def test_locator_empty_rejected(self):
        """locator is the machine address — it must be non-empty."""
        err = le_tools.validate_citation(
            {"artifact_type": "file_line", "locator": "  "})
        self.assertIsNotNone(err)
        self.assertIn("locator", err)

    def test_locator_missing_rejected(self):
        err = le_tools.validate_citation({"artifact_type": "file_line"})
        self.assertIsNotNone(err)
        self.assertIn("locator", err)

    def test_quote_optional(self):
        """quote may be omitted entirely (valid)."""
        err = le_tools.validate_citation(
            {"artifact_type": "commit_sha", "locator": "a78e25e"})
        self.assertIsNone(err)

    def test_quote_present_validates(self):
        err = le_tools.validate_citation(
            {"artifact_type": "file_line", "locator": "calc.py:10",
             "quote": "return a + b"})
        self.assertIsNone(err)

    def test_artifact_type_missing_rejected(self):
        err = le_tools.validate_citation({"locator": "calc.py:10"})
        self.assertIsNotNone(err)
        self.assertIn("artifact_type", err)

    def test_artifact_type_empty_rejected(self):
        err = le_tools.validate_citation(
            {"artifact_type": "  ", "locator": "calc.py:10"})
        self.assertIsNotNone(err)
        self.assertIn("artifact_type", err)

    def test_unknown_artifact_type_rejected(self):
        """An unregistered type must be rejected (closed until extended)."""
        err = le_tools.validate_citation(
            {"artifact_type": "totally_made_up_kind", "locator": "x"})
        self.assertIsNotNone(err)
        self.assertIn("artifact_type", err)

    def test_registered_extension_artifact_type_accepted(self):
        """The enum is OPEN: register_artifact_type() extends it."""
        le_schemas.register_artifact_type("design_token")
        err = le_tools.validate_citation(
            {"artifact_type": "design_token", "locator": "tokens.yml#color.bg"})
        self.assertIsNone(err)

    def test_non_object_rejected(self):
        for bad in (None, "file_line", 42, ["file_line"], object()):
            err = le_tools.validate_citation(bad)
            self.assertIsNotNone(err, f"non-object {bad!r} accepted")

    def test_non_string_locator_rejected(self):
        err = le_tools.validate_citation(
            {"artifact_type": "file_line", "locator": 10})
        self.assertIsNotNone(err)


# =============================================================================
# validate_claim — the Claim{text, citations[], material?} struct
# =============================================================================

class TestValidateClaim(unittest.TestCase):
    """validate_claim(data) -> error-string | None. None == valid struct."""

    def _cite(self, **over):
        c = {"artifact_type": "file_line", "locator": "calc.py:10"}
        c.update(over)
        return c

    def test_claim_with_one_citation_validates(self):
        err = le_tools.validate_claim(
            {"text": "add() returns the sum", "citations": [self._cite()]})
        self.assertIsNone(err, err)

    def test_claim_with_many_citations_validates(self):
        err = le_tools.validate_claim(
            {"text": "add() returns the sum", "citations": [
                self._cite(locator="calc.py:10"),
                {"artifact_type": "test_output",
                 "locator": "pytest -q -> 1 passed"},
            ]})
        self.assertIsNone(err, err)

    # ── THE HARD-FAIL PRIMITIVE ───────────────────────────────────────────────
    def test_material_claim_with_zero_citations_fails(self):
        """A material assertion with no evidence is the hard-fail case — this is
        what makes it a fact rather than a self-claim."""
        err = le_tools.validate_claim(
            {"text": "the fix is correct", "citations": []})
        self.assertIsNotNone(err)
        self.assertIn("citation", err.lower())

    def test_material_defaults_true_so_empty_citations_fails(self):
        """material is omitted entirely — defaults to material=True, so the
        claim is treated as material and zero citations hard-fails."""
        err = le_tools.validate_claim(
            {"text": "the fix is correct", "citations": []})
        self.assertIsNotNone(err)
        # And an explicit material=True has the same effect:
        err2 = le_tools.validate_claim(
            {"text": "the fix is correct", "citations": [],
             "material": True})
        self.assertIsNotNone(err2)

    def test_non_material_claim_zero_citations_validates(self):
        """A claim explicitly marked non-material (e.g. a framing statement)
        MAY carry an empty citations list."""
        err = le_tools.validate_claim(
            {"text": "Phase 0 grounds the goal", "citations": [],
             "material": False})
        self.assertIsNone(err, err)

    def test_non_material_claim_with_citations_still_validates(self):
        err = le_tools.validate_claim(
            {"text": "context note", "citations": [self._cite()],
             "material": False})
        self.assertIsNone(err, err)

    def test_invalid_citation_inside_claim_propagates(self):
        """A bad citation makes the whole claim invalid, with the index named."""
        err = le_tools.validate_claim(
            {"text": "claim", "citations": [
                {"artifact_type": "file_line", "locator": ""}]})
        self.assertIsNotNone(err)
        self.assertIn("citations[0]", err)

    def test_citations_not_a_list_rejected(self):
        err = le_tools.validate_claim(
            {"text": "claim", "citations": {"locator": "x"}})
        self.assertIsNotNone(err)
        self.assertIn("citations", err)

    def test_citations_missing_rejected(self):
        err = le_tools.validate_claim({"text": "claim"})
        self.assertIsNotNone(err)
        self.assertIn("citations", err)

    def test_text_empty_rejected(self):
        err = le_tools.validate_claim({"text": "  ", "citations": [self._cite()]})
        self.assertIsNotNone(err)
        self.assertIn("text", err)

    def test_text_missing_rejected(self):
        err = le_tools.validate_claim({"citations": [self._cite()]})
        self.assertIsNotNone(err)
        self.assertIn("text", err)

    def test_non_object_claim_rejected(self):
        for bad in (None, "claim", 42, ["claim"]):
            err = le_tools.validate_claim(bad)
            self.assertIsNotNone(err, f"non-object {bad!r} accepted")

    def test_material_must_be_boolean(self):
        err = le_tools.validate_claim(
            {"text": "claim", "citations": [], "material": "yes"})
        self.assertIsNotNone(err)
        self.assertIn("material", err)

    def test_claim_is_json_serializable(self):
        """Claims live on the board / run.metadata — they must serialize."""
        claim = {"text": "add() returns the sum", "citations": [self._cite()]}
        # Round-trips through JSON without loss (the wire shape).
        self.assertEqual(json.loads(json.dumps(claim)), claim)


# =============================================================================
# schemas — the importable building blocks + the open enum
# =============================================================================

class TestPrimitiveBuildingBlocks(unittest.TestCase):
    """Citation / Claim dataclasses + the open-enum registry."""

    def test_citation_dataclass_constructs_with_required_fields(self):
        c = le_schemas.Citation(
            artifact_type="file_line", locator="calc.py:10")
        self.assertEqual(c.artifact_type, "file_line")
        self.assertEqual(c.locator, "calc.py:10")
        self.assertIsNone(c.quote)  # optional

    def test_claim_dataclass_defaults_material_true(self):
        """material defaults True (fail-safe: a claim is material unless marked)."""
        c = le_schemas.Citation(artifact_type="url", locator="https://x")
        claim = le_schemas.Claim(text="see ref", citations=[c])
        self.assertTrue(claim.material)

    def test_claim_dataclass_validates_via_asdict(self):
        """A well-formed Claim dataclass serializes to a valid claim dict."""
        c = le_schemas.Citation(
            artifact_type="file_line", locator="calc.py:10",
            quote="return a + b")
        claim = le_schemas.Claim(text="add() returns the sum", citations=[c])
        err = le_tools.validate_claim(asdict(claim))
        self.assertIsNone(err, err)

    def test_known_artifact_types_contains_seed_set(self):
        self.assertTrue(
            le_schemas.SEED_ARTIFACT_TYPES.issubset(
                le_schemas.known_artifact_types()))

    def test_known_artifact_types_has_all_eight_seed_values(self):
        expected = {
            "file_line", "test_output", "grep_result", "commit_sha",
            "url", "adr_doc", "probe_result", "error_string",
        }
        self.assertEqual(expected, set(le_schemas.SEED_ARTIFACT_TYPES))


if __name__ == "__main__":
    unittest.main()
