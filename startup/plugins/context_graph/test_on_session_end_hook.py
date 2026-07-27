"""B1 scaffolding: the context_graph plugin must register an ``on_session_end``
lifecycle hook that is (a) wired through the real PluginManager discover path
and (b) safe to fire on session-end.

This is a SCAFFOLDING test — it only proves the hook exists and doesn't crash.
The actual grill-detection + transition logic is tickets B2/B3/B4, not this one.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.normpath(os.path.join(HERE, "..", "..", "hermes-agent"))
sys.path.insert(0, AGENT)
os.environ.setdefault(
    "HERMES_HOME",
    os.path.normpath(os.path.join(HERE, "..", "..", "profiles", "product-owner")),
)

import logging  # noqa: E402

logging.disable(logging.CRITICAL)


def _load_plugins():
    """Drive the REAL plugin discovery path (mirrors test_schema_envelope)."""
    from hermes_cli.plugins import PluginManager

    pm = PluginManager()
    pm.discover_and_load(force=True)
    return pm


def _context_graph_session_end_cb(pm):
    """Return the context_graph plugin's on_session_end callback, if registered."""
    for cb in pm._hooks.get("on_session_end", []):
        mod = getattr(cb, "__module__", "") or ""
        if "context_graph" in mod and cb.__name__ == "_on_session_end":
            return cb
    return None


def test_on_session_end_hook_registered():
    """The hook is wired through PluginManager discover_and_load."""
    pm = _load_plugins()
    assert pm.has_hook("on_session_end"), "on_session_end hook was not registered"
    cb = _context_graph_session_end_cb(pm)
    assert cb is not None, (
        "context_graph._on_session_end not found among on_session_end callbacks"
    )


def test_on_session_end_hook_fires_without_raising():
    """Calling the hook (simulating a session-end) must not raise.

    invoke_hook swallows callback exceptions, so we call the callback directly
    to truly verify it is crash-proof. The scaffold returns None.
    """
    pm = _load_plugins()
    cb = _context_graph_session_end_cb(pm)
    assert cb is not None

    # Simulate the kwargs Hermes passes at session-end. The scaffold must
    # tolerate arbitrary kwargs (accepts **kw) and return None.
    result = cb(
        session_id="test-session-123",
        profile_name="product-owner",
        reason="end",
    )
    assert result is None

    # Also drive the manager-level fire path — runs cleanly, no non-None values.
    invoke_result = pm.invoke_hook(
        "on_session_end",
        session_id="test-session-123",
        profile_name="product-owner",
    )
    assert invoke_result == []
