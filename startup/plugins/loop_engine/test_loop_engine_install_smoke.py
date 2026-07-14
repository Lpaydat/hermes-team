#!/usr/bin/env python3
"""
Install-smoke test for loop_engine — closes the 4-gate install-defect class.

The existing ``test_loop_engine*.py`` suites do ``sys.path.insert`` +
``import loop_engine``. That bypasses every enable gate, so they stayed
green through the entire 4-layer install-defect chain that blocked the
debugger smoke. This test closes that false-confidence gap.

It drives the REAL plugin-manager discovery path —
``get_plugin_manager().discover_and_load(force=True)`` — against a
throwaway profile (HERMES_HOME = temp dir), and asserts the loop_engine
tool is *resolvable the way a worker session resolves it*: present in the
PluginManager, in the tool registry, AND exposed to the active platform
via ``platform_toolsets``. NOT ``import loop_engine``.

If discovery can't find loop_engine OR any enable gate drops it, this test
FAILS LOUD. It is the only test shape that catches gate 4 (the plugin
symlink discovery failure) — the root cause of the original install-defect
chain.

The 4 gates exercised (all set up in the throwaway profile so the real
path resolves):
  1. ``plugins.enabled`` in profile config      — ``_get_enabled_plugins``
  2. global enable (``hermes plugins enable <name>``) — persists exactly
     the ``plugins.enabled`` key read by gate 1; this test writes that
     state directly (the sanctioned fallback per design ticket
     ``hermes-teams-76n``).
  3. ``platform_toolsets[cli]`` lists loop_engine — ``_toggle_plugin_toolset``
  4. plugin symlink ``<profile>/plugins/loop_engine`` — the user-plugins
     discovery scan. ``get_bundled_plugins_dir()`` has no loop_engine, so
     the symlink is the ONLY way discovery finds it. ROOT CAUSE of the
     original install defect.

See ``SPEC.md`` §Fact-Based Loop Enhancement T7, and design ticket
``hermes-teams-76n`` (its comment holds the full resolution).
"""
import os
from pathlib import Path

import pytest

# These tests drive the REAL PluginManager.discover_and_load() — they need the
# full hermes-agent runtime env (hermes_cli + its deps, e.g. PyYAML). Skip
# gracefully when PyYAML is absent (e.g. bare system python3) so the suite stays
# green; run with `startup/hermes-agent/venv/bin/python3 -m pytest` to exercise.
# (Checking the leaf dep `yaml` — no module-level hermes_cli import, which would
# have import side effects that pollute other tests' isolation.)
pytest.importorskip("yaml")

# Absolute path to the REAL loop_engine source — the gate-4 symlink target.
# Resolved from this file's location so the test is cwd-independent.
REPO_PLUGINS_DIR = Path(__file__).resolve().parent.parent  # .../startup/plugins
LOOP_ENGINE_SOURCE = REPO_PLUGINS_DIR / "loop_engine"
TOOL_NAME = "loop_engine"
TOOLSET_KEY = "loop_engine"  # loop_engine registers its tool under this toolset


# --------------------------------------------------------------------------- #
# Throwaway-profile setup — each gate is set up explicitly so the real path
# passes, and so the negative test can omit gate 4 to prove it is load-bearing.
# --------------------------------------------------------------------------- #
def _build_throwaway_profile(profile_dir: Path) -> None:
    """Write a minimal throwaway profile that ENABLES loop_engine (gates 1-3).

    Gate 4 (the symlink) is installed separately by ``_install_symlink_gate``.
    """
    profile_dir.mkdir(parents=True, exist_ok=True)
    # Gates 1 + 2: ``plugins.enabled``. Gate 2 (``hermes plugins enable
    # <name>``) persists exactly this key; writing it directly is the
    # sanctioned fallback (design ticket hermes-teams-76n) and exercises the
    # same read path (``_get_enabled_plugins``) at discovery time.
    # Gate 3: ``platform_toolsets.cli`` lists the loop_engine toolset.
    config_yaml = (
        "model:\n"
        "  default: glm-5.2\n"
        "plugins:\n"
        "  enabled:\n"
        f"    - {TOOL_NAME}\n"
        "platform_toolsets:\n"
        "  cli:\n"
        f"    - {TOOLSET_KEY}\n"
    )
    (profile_dir / "config.yaml").write_text(config_yaml, encoding="utf-8")


def _install_symlink_gate(profile_dir: Path) -> Path:
    """Gate 4: symlink ``<profile>/plugins/loop_engine`` -> real source."""
    plugins_dir = profile_dir / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    link = plugins_dir / TOOL_NAME
    # resolve() so the symlink points at the canonical absolute source dir.
    link.symlink_to(LOOP_ENGINE_SOURCE.resolve(), target_is_directory=True)
    return link


def _drive_real_discovery():
    """Drive the REAL PluginManager.discover_and_load() — the path under test.

    ``force=True`` clears cached manager state first, so the scan (and the
    resulting ``_plugins`` / ``_plugin_tool_names``) reflects ONLY this
    throwaway profile — not whatever a prior test loaded into the global
    singleton.
    """
    from hermes_cli.plugins import get_plugin_manager

    mgr = get_plugin_manager()
    mgr.discover_and_load(force=True)
    return mgr


def _fail_loud(mgr, reason: str) -> None:
    """Surface every gate + the discovery state so a failure is diagnosable."""
    loaded = {
        k: {"enabled": v.enabled, "error": v.error}
        for k, v in mgr._plugins.items()
    }
    scanned_user = Path(os.environ["HERMES_HOME"]) / "plugins"
    pytest.fail(
        f"\n[install-smoke] loop_engine NOT resolvable via real plugin path.\n"
        f"  reason: {reason}\n"
        f"  HERMES_HOME={os.environ.get('HERMES_HOME')}\n"
        f"  user-plugins scan dir: {scanned_user}\n"
        f"  gate-4 symlink present? {(scanned_user / TOOL_NAME).exists()}\n"
        f"  bundled-plugins dir (isolated): "
        f"{os.environ.get('HERMES_BUNDLED_PLUGINS')}\n"
        f"  loaded plugins: {loaded or '(none)'}\n"
        f"  plugin_tool_names: {sorted(mgr._plugin_tool_names)}\n"
        f"  4 gates: (1) plugins.enabled  (2) global-enable=persisted-enabled "
        f"(3) platform_toolsets[cli]  (4) plugin symlink\n"
        f"  re-run with HERMES_PLUGINS_DEBUG=1 for the full discovery log.",
        pytrace=False,
    )


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def test_loop_engine_resolves_via_real_plugin_path(tmp_path, monkeypatch):
    """POSITIVE smoke: all 4 gates set -> loop_engine resolvable at session level.

    Drives the SAME path a worker session uses (get_plugin_manager().
    discover_and_load), NOT a direct import. If any gate is wrong, this fails.
    """
    profile = tmp_path / "le-smoke"
    _build_throwaway_profile(profile)  # gates 1, 2, 3
    _install_symlink_gate(profile)     # gate 4

    # Redirect the REAL plugin manager at the throwaway profile. Isolate the
    # bundled scan to an empty dir so loop_engine can ONLY be found via gate 4
    # (the user-plugins symlink) — exactly the real-world shape (loop_engine is
    # not a bundled plugin; get_bundled_plugins_dir() has no loop_engine).
    monkeypatch.setenv("HERMES_HOME", str(profile))
    empty_bundled = tmp_path / "empty-bundled"
    empty_bundled.mkdir()
    monkeypatch.setenv("HERMES_BUNDLED_PLUGINS", str(empty_bundled))

    mgr = _drive_real_discovery()

    # --- A. plugin loaded + enabled (gates 1, 2, 4) ---
    loaded = mgr._plugins.get(TOOL_NAME)
    if loaded is None or not loaded.enabled:
        _fail_loud(mgr, "plugin not loaded/enabled (gate 1/2/4)")

    # --- B. tool registered with the manager IN THIS discover pass ---
    # _plugin_tool_names is cleared by force=True and rebuilt, so membership
    # here proves loop_engine loaded + registered its tool this scan.
    if TOOL_NAME not in mgr._plugin_tool_names:
        _fail_loud(mgr, "tool not in mgr._plugin_tool_names")

    # --- C. tool present in the global tool registry ---
    from tools.registry import registry

    if registry.get_entry(TOOL_NAME) is None:
        _fail_loud(mgr, "registry.get_entry(loop_engine) is None")

    # --- D. toolset exposed to the active platform (gate 3 — session-reach) ---
    # A session resolves available toolsets via platform_toolsets[<platform>];
    # registry.get_entry alone is NOT enough (defect 2/3 trap).
    from hermes_cli.config import load_config

    cli_toolsets = load_config().get("platform_toolsets", {}).get("cli", [])
    if TOOLSET_KEY not in cli_toolsets:
        _fail_loud(
            mgr,
            f"loop_engine toolset missing from platform_toolsets[cli]="
            f"{cli_toolsets}",
        )


def test_gate4_symlink_is_load_bearing(tmp_path, monkeypatch):
    """NEGATIVE smoke: omit gate 4 (symlink) -> discovery must NOT enable it.

    Proves the symlink is a real DISCOVERY gate — the root cause of the
    original install-defect chain. Asserts on PluginManager state (cleared
    and rebuilt by force=True), NOT the global tool registry: the registry
    is cumulative across the process and would mask a discovery failure
    (the exact false-confidence gap this suite exists to close).
    """
    profile = tmp_path / "le-smoke-nosymlink"
    _build_throwaway_profile(profile)  # gates 1, 2, 3 only
    # NOTE: gate 4 (the symlink) deliberately NOT installed.

    monkeypatch.setenv("HERMES_HOME", str(profile))
    empty_bundled = tmp_path / "empty-bundled-neg"
    empty_bundled.mkdir()
    monkeypatch.setenv("HERMES_BUNDLED_PLUGINS", str(empty_bundled))

    mgr = _drive_real_discovery()

    loaded = mgr._plugins.get(TOOL_NAME)
    # Without the symlink, discovery can't find loop_engine at all — it must be
    # absent, or at best recorded as a disabled manifest with an enable error.
    # Being ENABLED here would mean the symlink gate isn't actually exercised.
    if loaded is not None and loaded.enabled:
        pytest.fail(
            "[install-smoke negative] loop_engine was ENABLED without the "
            "gate-4 symlink — discovery is not actually exercising the "
            f"symlink gate. loaded={loaded}",
            pytrace=False,
        )
