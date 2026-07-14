#!/usr/bin/env python3
"""TDD test for hermes-teams-1h5 — surface the v2 fields in the loop_engine
tool input schema.

ROOT CAUSE: the engine (tools.py) reads these fields from ``args`` but they
were never declared in ``LOOP_ENGINE.parameters.properties``, so the agent had
no input surface and they defaulted off on every real agent-driven run (unit
tests bypassed the schema by building ``args`` directly).

This test asserts the schema DECLARES each v2 field with the correct JSON-schema
``type`` (and ``default`` where the engine has one), so the agent can actually
pass them on real runs.

Bead: ``bd show hermes-teams-1h5``.
Fields (cited by feature):
  * strict_fact_basis (T9) — bool, default false.
  * loop_id (B7) — string (root_id alias; drift-immune root pin).
  * discover (B3) — object {assignee, dod, max_iterations}.
  * strict_dod (B9) — bool, default false.
  * budget — int (loop budget cap).
  * max_iterations — int (per-loop iteration cap).
  * no_progress_threshold — int (no-progress exit threshold).
"""

import pytest

from loop_engine import schemas


PROPS = schemas.LOOP_ENGINE["parameters"]["properties"]


# ── the 7 v2 fields must be declared in the schema ────────────────────────────

@pytest.mark.parametrize("field,expected_type", [
    ("strict_fact_basis", "boolean"),
    ("loop_id", "string"),
    ("discover", "object"),
    ("strict_dod", "boolean"),
    ("budget", "integer"),
    ("max_iterations", "integer"),
    ("no_progress_threshold", "integer"),
])
def test_v2_field_present_with_correct_type(field, expected_type):
    """Each v2 field must be declared in the schema with the correct type."""
    assert field in PROPS, (
        f"v2 field '{field}' is missing from LOOP_ENGINE schema properties — "
        f"the engine reads args.get('{field}') but the agent has no input "
        f"surface to pass it (hermes-teams-1h5)"
    )
    assert PROPS[field]["type"] == expected_type, (
        f"v2 field '{field}' has type '{PROPS[field]['type']}', "
        f"expected '{expected_type}'"
    )


# ── defaults where the engine has one ─────────────────────────────────────────

def test_strict_fact_basis_defaults_false():
    """T9: strict_fact_basis defaults false (zero-regression additive)."""
    assert PROPS["strict_fact_basis"].get("default") is False


def test_strict_dod_defaults_false():
    """B9: strict_dod defaults false (today's prose-DoD compat)."""
    assert PROPS["strict_dod"].get("default") is False


# ── discover nested properties (B3) ───────────────────────────────────────────

def test_discover_has_nested_properties():
    """B3: discover must declare its nested properties (assignee/dod/
    max_iterations) so the agent knows the shape."""
    discover = PROPS["discover"]
    assert "properties" in discover, (
        "discover must declare nested 'properties' (assignee/dod/"
        "max_iterations) like the existing execution/phases nested objects"
    )
    nested = discover["properties"]
    # dod — REQUIRED, non-empty string (the grounding DoD)
    assert "dod" in nested, "discover.properties must include 'dod'"
    assert nested["dod"]["type"] == "string"
    # assignee — OPTIONAL string (grounding-worker profile)
    assert "assignee" in nested, "discover.properties must include 'assignee'"
    assert nested["assignee"]["type"] == "string"
    # max_iterations — OPTIONAL positive int (caps the discover loop)
    assert "max_iterations" in nested, (
        "discover.properties must include 'max_iterations'"
    )
    assert nested["max_iterations"]["type"] == "integer"


def test_discover_requires_dod():
    """B3: dod is the one required property of discover (the grounding DoD)."""
    discover = PROPS["discover"]
    assert "required" in discover, (
        "discover must declare a 'required' list (dod is required)"
    )
    assert "dod" in discover["required"]


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
