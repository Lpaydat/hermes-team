#!/usr/bin/env python3
"""TDD test for hermes-teams-d8h — schema-completeness INVARIANT (supersedes m63).

THE GAP CLASS
=============
The loop_engine tool declares a JSON-schema (``LOOP_ENGINE``) that an agent
inspects to discover what it may pass. But the engine implementation
(``tools.py``) reads+validates fields off the call args that the schema never
declares. They survive at runtime only because ``additionalProperties`` defaults
true — but an agent reading the schema cannot discover them.

This bit us twice in the same way:
  * hermes-teams-1h5 — top-level v2 fields (strict_fact_basis / loop_id /
    budget / ...) were read off ``args`` but invisible in
    ``parameters.properties``. 1h5 patched it with a per-field allowlist test.
  * hermes-teams-d8h (this bead) — the SAME gap class recurred ONE LEVEL DOWN:
    ``metric_type`` / ``battery`` / ``dod_signals`` / per-verifier
    ``strict_fact_basis`` / ``strict_dod`` / ``artifact_required`` are read,
    validated, and drive control flow off the verifier object, but the verifier
    ``properties`` blocks declared only ``{assignee, title, body, skill}``.

1h5's test was a HARDCODED field allowlist — it could not catch the nested
recurrence because it didn't know to look for those names. The load-bearing
test in this file replaces that allowlist with a DERIVED invariant: it greps
``tools.py`` for *every* field the engine actually reads and asserts each is
surfaced in the schema. A future field read off the verifier but not declared
will fail this test regardless of whether anyone remembered to add its name to
an allowlist — that is what "kills the gap class" means.

WHAT THE INVARIANT ASSERTS
==========================
  * TOP-LEVEL — every field read off ``args`` (``args.get("X")`` /
    ``args["X"]``) is discoverable in ``parameters.properties``: either it is a
    property key, or it is named in a property description (a documented alias,
    e.g. ``root_id`` is an alias of ``loop_id``).
  * VERIFIER (the new guard) — every field read off a verifier-shaped object
    (any variable named ``*verifier*`` / ``*pver*``: ``verifier``,
    ``verifier_spec``, ``pver``, ``_cur_verifier``, …) via ``.get("X")`` or
    ``["X"]`` is a key in BOTH verifier ``properties`` blocks: the top-level
    ``verifier`` AND ``phases[].items.verifier``.

The field SET is derived from source at collection time — adding a read without
surfacing it makes the test RED. That is the whole point.

Bead: ``bd show hermes-teams-d8h``. TDD: RED first (6 nested fields missing),
then schemas.py surfaces them → GREEN.
"""

import json
import re
from pathlib import Path

import pytest

from loop_engine import schemas
from loop_engine import tools as le_tools


# ─── source of truth for "what the engine reads" ─────────────────────────────
# tools.py is the implementation; its reads define the contract the schema must
# declare. We parse the source (not import) so a field used only inside a string
# or comment is not silently treated as a real read — we match actual call sites.
TOOLS_SRC = Path(le_tools.__file__).read_text()

SCHEMA_PROPS = schemas.LOOP_ENGINE["parameters"]["properties"]

TOPLEVEL_VERIFIER = SCHEMA_PROPS["verifier"]["properties"]
PHASES_ITEMS_VERIFIER = SCHEMA_PROPS["phases"]["items"]["properties"]["verifier"]["properties"]


# ─── derivation: which fields does the engine READ? ──────────────────────────

def _top_level_fields():
    """Every field read off the loop_engine ``args`` object.

    Matches ``args.get("X")`` and ``args["X"]`` literal call sites in tools.py.
    ``args`` is the house-wide name for the loop_engine tool's call arguments
    (the ``_validate(args, …)`` seam and the handler both bind the same dict).
    """
    fields = set()
    for m in re.finditer(r'\bargs\b\s*(?:\.\s*get\s*\(\s*["\']([\w_]+)["\']'
                         r'|\[\s*["\']([\w_]+)["\']\s*\])', TOOLS_SRC):
        fields.add(m.group(1) or m.group(2))
    assert fields, "derived zero top-level fields — derivation regex is broken"
    return frozenset(fields)


def _verifier_fields():
    """Every field read off a VERIFIER-SHAPED object in tools.py.

    A verifier-shaped object is any variable whose name contains ``verifier`` or
    ``pver`` (the codebase convention: ``verifier``, ``verifier_spec``, ``pver``
    = phase-verifier, ``_cur_verifier`` = resolved current-phase verifier). We
    collect ``VAR.get("X")`` and ``VAR["X"]`` literal call sites on any such
    variable, tolerating a defensive-coalescing wrapper
    (``(VAR or {}).get("X")``) — the read shape used for ``_cur_verifier``.
    Field names are derived from source — nothing is hardcoded.
    """
    fields = set()
    # var name must contain verifier/pver; tolerate `(VAR or {})` then .get/[
    pattern = (r'(\w*(?:verifier|pver)\w*)'
               r'(?:\s+or\s*\{\})?'      # `(VAR or {})` defensive coalesce
               r'\s*\)?\s*'              # optional closing paren of (VAR ...)
               r'(?:\.\s*get\s*\(\s*["\']([\w_]+)["\']'
               r'|\[\s*["\']([\w_]+)["\']\s*\])')
    for m in re.finditer(pattern, TOOLS_SRC):
        var = m.group(1)
        field = m.group(2) or m.group(3)
        if field:
            fields.add(field)
    assert fields, "derived zero verifier fields — derivation regex is broken"
    return frozenset(fields)


def _top_level_discoverable(field, props):
    """A top-level field is discoverable if it is a property key OR is named
    (word-bounded) in a property description — the latter is the documented-alias
    escape (``root_id`` is an alias of ``loop_id``, surfaced via description)."""
    if field in props:
        return True
    for prop in props.values():
        desc = prop.get("description", "") or ""
        if re.search(rf'\b{re.escape(field)}\b', desc):
            return True
    return False


# ─── THE INVARIANT (load-bearing — kills the gap class) ───────────────────────

class TestSchemaCompletenessInvariant:
    """The schema must surface every field the engine reads. Field sets are
    DERIVED from tools.py, never hardcoded."""

    def test_top_level_reads_are_surfaceable(self):
        """Every ``args`` read is discoverable in parameters.properties.

        Regression guard for hermes-teams-1h5 (the top-level gap). ``root_id``
        passes because it is a documented alias of ``loop_id``.
        """
        missing = [f for f in sorted(_top_level_fields())
                   if not _top_level_discoverable(f, SCHEMA_PROPS)]
        assert not missing, (
            "top-level fields read off `args` in tools.py but not discoverable "
            f"in LOOP_ENGINE.parameters.properties: {missing}")

    def test_verifier_reads_surface_in_top_level_verifier_block(self):
        """Every field read off a verifier object is a key in the top-level
        ``verifier`` property block — the guard that would have caught d8h."""
        missing = sorted(_verifier_fields() - set(TOPLEVEL_VERIFIER))
        assert not missing, (
            "fields read off a verifier object in tools.py but missing from "
            f"LOOP_ENGINE.parameters.properties.verifier.properties: {missing}")

    def test_verifier_reads_surface_in_phases_items_verifier_block(self):
        """Same invariant, one level down: ``phases[].items.verifier`` must
        declare every verifier read too (the engine reads both single + multi
        phase verifier specs through the same fields)."""
        missing = sorted(_verifier_fields() - set(PHASES_ITEMS_VERIFIER))
        assert not missing, (
            "fields read off a verifier object in tools.py but missing from "
            "LOOP_ENGINE.parameters.properties.phases.items.verifier."
            f"properties: {missing}")

    def test_both_verifier_blocks_declare_the_same_field_set(self):
        """The two verifier blocks must stay in sync — a field on one but not the
        other is a latent gap for whichever path the agent takes."""
        only_top = sorted(set(TOPLEVEL_VERIFIER) - set(PHASES_ITEMS_VERIFIER))
        only_phase = sorted(set(PHASES_ITEMS_VERIFIER) - set(TOPLEVEL_VERIFIER))
        assert not (only_top or only_phase), (
            f"verifier blocks disagree — only top-level: {only_top}; "
            f"only phases[].items: {only_phase}")


# ─── per-field shapes (the surfaced fields have correct JSON-schema types) ────
# Both verifier blocks must declare each nested v2 field with the right shape.
# Parametrized over the two blocks so a drift in either is caught independently.

_VERIFIER_BLOCKS = [
    pytest.param("verifier", TOPLEVEL_VERIFIER, id="top-level-verifier"),
    pytest.param("phases[].items.verifier", PHASES_ITEMS_VERIFIER,
                 id="phases-items-verifier"),
]


@pytest.mark.parametrize("label,block", _VERIFIER_BLOCKS)
def test_metric_type_shape(label, block):
    """metric_type is the metric-kind enum: ground_truth (mechanical) | proxy
    (judgment, gameable — battery mandatory). See _validate_metric_type."""
    assert "metric_type" in block, f"{label}.metric_type missing"
    f = block["metric_type"]
    assert f["type"] == "string", f"{label}.metric_type must be string"
    assert set(f["enum"]) == {"ground_truth", "proxy"}, (
        f"{label}.metric_type enum must be ground_truth|proxy")


@pytest.mark.parametrize("label,block", _VERIFIER_BLOCKS)
def test_battery_shape(label, block):
    """battery = {path: <test-path str>, runner: <profile str>}; required when
    metric_type=proxy. See _validate_metric_type (tools.py ~L486-498)."""
    assert "battery" in block, f"{label}.battery missing"
    f = block["battery"]
    assert f["type"] == "object", f"{label}.battery must be object"
    bprops = f["properties"]
    assert set(bprops) == {"path", "runner"}, (
        f"{label}.battery must declare exactly path+runner, got {sorted(bprops)}")
    assert bprops["path"]["type"] == "string"
    assert bprops["runner"]["type"] == "string"


@pytest.mark.parametrize("label,block", _VERIFIER_BLOCKS)
def test_dod_signals_shape(label, block):
    """dod_signals = array of DoDSignal{artifact_type, locator, expectation?}.
    See _validate_dod_signals (tools.py ~L567). expectation is optional."""
    assert "dod_signals" in block, f"{label}.dod_signals missing"
    f = block["dod_signals"]
    assert f["type"] == "array", f"{label}.dod_signals must be array"
    item = f["items"]
    assert item["type"] == "object", f"{label}.dod_signals[].items must be object"
    sprops = item["properties"]
    # artifact_type + locator required; expectation optional.
    assert {"artifact_type", "locator"} <= set(sprops), (
        f"{label}.dod_signals[] must declare artifact_type+locator")
    assert sprops["artifact_type"]["type"] == "string"
    assert sprops["locator"]["type"] == "string"
    assert "expectation" in sprops, (
        f"{label}.dod_signals[] must declare optional expectation")
    assert sprops["expectation"]["type"] == "string"
    assert "artifact_type" in item.get("required", [])
    assert "locator" in item.get("required", [])
    # expectation is intentionally NOT required.
    assert "expectation" not in item.get("required", [])


@pytest.mark.parametrize("label,block", _VERIFIER_BLOCKS)
def test_strict_fact_basis_shape(label, block):
    """Per-verifier strict_fact_basis override (true wins over workflow-wide)."""
    assert "strict_fact_basis" in block, f"{label}.strict_fact_basis missing"
    assert block["strict_fact_basis"]["type"] == "boolean"


@pytest.mark.parametrize("label,block", _VERIFIER_BLOCKS)
def test_strict_dod_shape(label, block):
    """Per-verifier strict_dod override (true wins over workflow-wide)."""
    assert "strict_dod" in block, f"{label}.strict_dod missing"
    assert block["strict_dod"]["type"] == "boolean"


@pytest.mark.parametrize("label,block", _VERIFIER_BLOCKS)
def test_artifact_required_shape(label, block):
    """DoD-artifact gate opt-in; read at decide-time to gate phase advance."""
    assert "artifact_required" in block, f"{label}.artifact_required missing"
    assert block["artifact_required"]["type"] == "boolean"


# ─── sanity: the derivation itself is honest (guards against a no-op regex) ───

def test_derivation_finds_the_known_verifier_reads():
    """If the derivation regex silently matched nothing new, the invariant would
    be vacuous. Pin it to the known reads so a regex regression is loud."""
    vf = _verifier_fields()
    for known in ("assignee", "title", "body", "skill", "metric_type",
                  "battery", "dod_signals", "strict_fact_basis", "strict_dod",
                  "artifact_required"):
        assert known in vf, (
            f"derivation lost known verifier read {known!r} — regex broken")


def test_derivation_finds_the_known_top_level_reads():
    tf = _top_level_fields()
    for known in ("goal", "execution", "verifier", "phases", "loop_id",
                  "strict_fact_basis", "strict_dod"):
        assert known in tf, (
            f"derivation lost known top-level read {known!r} — regex broken")
