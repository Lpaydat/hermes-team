"""Pytest path bootstrap for loop_engine tests.

The install-smoke tests drive the REAL PluginManager.discover_and_load() — they
import ``hermes_cli.plugins`` + ``utils`` from the external hermes-agent runtime
(startup/hermes-agent/), which is not on sys.path when pytest runs from the
plugin directory. Add it so those tests resolve + actually exercise the install
gates (T7). (They still need the runtime's deps, e.g. PyYAML — see the
importorskip in test_loop_engine_install_smoke.py.)
"""
import sys
from pathlib import Path

_HERMES_AGENT = Path(__file__).resolve().parents[2] / "hermes-agent"
if (_HERMES_AGENT / "hermes_cli").is_dir():
    sys.path.insert(0, str(_HERMES_AGENT))
