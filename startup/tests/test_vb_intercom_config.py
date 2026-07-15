#!/usr/bin/env python3
"""Config-validation test: venture-builder cleanly enables intercom.

WHAT: venture-builder must enable the intercom plugin cleanly, matching
product-owner's enablement. Concretely:
  1. ``plugins.enabled`` lists ``intercom``.
  2. The malformed ``toolsets`` entry ``"kanban - intercom"`` (one combined
     string) is split into the discrete entries ``kanban`` and ``intercom``.
  3. VB's pre-existing toolsets (``hermes-cli``, ``context_graph``) are
     preserved.
  4. The config still parses cleanly as YAML.

WHY THIS IS A SEAM TEST: the ``toolsets`` list feeds the agent's
``enabled_toolsets`` (see startup/hermes-agent/agent/agent_init.py) — a single
``"kanban - intercom"`` string is not a real toolset, so half the intended
tooling silently never loads. ``plugins.enabled`` is the plugin opt-in list;
without ``intercom`` there the plugin never activates even though the symlink
under startup/profiles/venture-builder/plugins/intercom exists. This test pins
the *decision* (intercom on, discrete toolsets) at the config boundary rather
than asserting on runtime behaviour.

Run:
    cd /home/lpaydat/.hermes-teams/startup/hermes-agent && \\
    PYTHONPATH=. ./venv/bin/python -m pytest \\
        /home/lpaydat/.hermes-teams/startup/tests/test_vb_intercom_config.py -q
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

# The committed VB config. Resolved relative to this test file so the test is
# location-independent (no hardcoded absolute repo path).
VB_CONFIG = (
    Path(__file__).resolve().parent.parent
    / "profiles"
    / "venture-builder"
    / "config.yaml"
)

# The malformed combined string that must NEVER appear as a toolset entry.
MALFORMED_TOOLSET = "kanban - intercom"


@pytest.fixture(scope="module")
def vb_config() -> dict:
    """Parse the VB config.yaml once; fail loudly if it does not parse."""
    assert VB_CONFIG.exists(), f"missing VB config at {VB_CONFIG}"
    with VB_CONFIG.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def test_config_parses_cleanly(vb_config: dict) -> None:
    """The config must parse as valid YAML into a non-empty mapping."""
    assert isinstance(vb_config, dict), "VB config did not parse to a mapping"
    assert vb_config, "VB config parsed to an empty document"


def test_intercom_in_plugins_enabled(vb_config: dict) -> None:
    """plugins.enabled must list intercom (plugin opt-in)."""
    plugins = vb_config.get("plugins", {})
    enabled = plugins.get("enabled")
    assert isinstance(enabled, list), "plugins.enabled is not a list"
    assert "intercom" in enabled, (
        f"intercom missing from plugins.enabled; have {enabled!r}"
    )


def test_no_malformed_combined_toolset(vb_config: dict) -> None:
    """No toolsets entry may equal the combined string 'kanban - intercom'."""
    toolsets = vb_config.get("toolsets")
    assert isinstance(toolsets, list), "toolsets is not a list"
    offenders = [t for t in toolsets if t == MALFORMED_TOOLSET]
    assert not offenders, (
        f"malformed combined toolset {MALFORMED_TOOLSET!r} still present in "
        f"toolsets; got {toolsets!r}"
    )


def test_kanban_and_intercom_are_discrete_toolsets(vb_config: dict) -> None:
    """kanban and intercom must each appear as discrete toolset entries."""
    toolsets = vb_config.get("toolsets")
    assert isinstance(toolsets, list), "toolsets is not a list"
    assert "kanban" in toolsets, f"kanban toolset missing; have {toolsets!r}"
    assert "intercom" in toolsets, (
        f"intercom toolset missing; have {toolsets!r}"
    )


def test_existing_toolsets_preserved(vb_config: dict) -> None:
    """VB's pre-existing hermes-cli and context_graph toolsets are preserved."""
    toolsets = vb_config.get("toolsets")
    assert isinstance(toolsets, list), "toolsets is not a list"
    assert "hermes-cli" in toolsets, "hermes-cli toolset was lost"
    assert "context_graph" in toolsets, "context_graph toolset was lost"
