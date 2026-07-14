#!/usr/bin/env python3
"""TDD test for hermes-teams-drj — surface the v2 verifier fields in the
loop_engine tool input schema (the 1h5 sibling, one nesting level down).

ROOT CAUSE: the engine (tools.py) reads + validates these fields off the
verifier object (metric_type, battery, dod_signals, strict_fact_basis,
strict_dod, artifact_required), but they were NOT declared in the schema's
``verifier.properties`` — so a tool-calling driver validating against the
schema sees only {assignee, title, body, skill} and DROPS the v2 fields on
real runs (the README §2 contract gap). Today they pass through only because
``additionalProperties`` defaults true AND the skill template passes them
literally — fragile.

This test asserts the schema DECLARES each v2 verifier field on BOTH the
top-level ``verifier`` and the per-phase ``phases[].verifier`` so the agent
passes them reliably.

Bead: ``bd show hermes-teams-drj``.
"""

import pytest

from loop_engine import schemas


PROPS = schemas.LOOP_ENGINE["parameters"]["properties"]

# Both the top-level verifier and each phase's verifier must surface the fields.
TOPLEVEL_VERIFIER = PROPS["verifier"]["properties"]
PHASE_VERIFIER = PROPS["phases"]["items"]["properties"]["verifier"]["properties"]

VERIFIER_V2_FIELDS = [
    # (field, expected_type)
    ("metric_type", "string"),       # enum ground_truth|proxy (T4)
    ("battery", "object"),           # {path, runner} — required when proxy (T5/B6)
    ("dod_signals", "array"),        # [DoDSignal] (T8)
    ("strict_fact_basis", "boolean"),  # per-verifier override (T9)
    ("strict_dod", "boolean"),       # per-verifier override (T8)
    ("artifact_required", "boolean"),  # design-council defect-coverage gate
]


@pytest.mark.parametrize("field,expected_type", VERIFIER_V2_FIELDS)
@pytest.mark.parametrize("label,verifier_props", [
    ("top-level verifier", TOPLEVEL_VERIFIER),
    ("phase verifier", PHASE_VERIFIER),
])
def test_verifier_v2_field_present(field, expected_type, label, verifier_props):
    """Each v2 verifier field must be declared on the schema's verifier
    properties (both top-level and per-phase) so the agent passes it."""
    assert field in verifier_props, (
        f"v2 verifier field '{field}' missing from {label} schema properties "
        f"— the engine validates it but the agent can't pass it "
        f"(hermes-teams-drj, the 1h5 sibling)"
    )
    assert verifier_props[field]["type"] == expected_type, (
        f"v2 verifier field '{field}' on {label} has type "
        f"'{verifier_props[field]['type']}', expected '{expected_type}'"
    )


def test_metric_type_is_enum_ground_truth_proxy():
    """T4: metric_type must be the ground_truth|proxy enum so the agent knows
    the allowed values."""
    for label, vp in [("top-level", TOPLEVEL_VERIFIER),
                      ("phase", PHASE_VERIFIER)]:
        mt = vp["metric_type"]
        assert "enum" in mt, f"{label} metric_type must declare an enum"
        assert set(mt["enum"]) == {"ground_truth", "proxy"}, (
            f"{label} metric_type enum must be {{ground_truth, proxy}}, "
            f"got {mt['enum']}"
        )


def test_battery_has_path_and_runner():
    """T5/B6: battery must declare path + runner (both required — a proxy
    verifier needs a well-formed battery)."""
    for label, vp in [("top-level", TOPLEVEL_VERIFIER),
                      ("phase", PHASE_VERIFIER)]:
        b = vp["battery"]
        nested = b["properties"]
        assert nested["path"]["type"] == "string", f"{label} battery.path"
        assert nested["runner"]["type"] == "string", f"{label} battery.runner"
        assert set(b["required"]) == {"path", "runner"}, (
            f"{label} battery must require path + runner")


def test_artifact_required_defaults_false():
    """The design-council defect-coverage gate is opt-in (default false)."""
    for label, vp in [("top-level", TOPLEVEL_VERIFIER),
                      ("phase", PHASE_VERIFIER)]:
        assert vp["artifact_required"].get("default") is False, (
            f"{label} artifact_required must default false")


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
