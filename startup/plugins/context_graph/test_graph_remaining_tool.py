#!/usr/bin/env python3
"""
TDD for hermes-teams-8y86 (A2) — graph_remaining TOOL exposure.

A1 (commit 59f7df7) added the ``cg.graph_remaining()`` backlog query. A2 exposes
it as an agent-callable tool:
  - schemas.py:   GRAPH_REMAINING envelope {name, description, parameters:{}}.
  - tools.py:     graph_remaining(args, **kw) -> json.dumps({count, remaining}).
  - __init__.py:  registered in tools_to_register.

Two regressions guarded here:
  1. SCHEMA-ENVELOPE: graph_remaining must reach the model via
     get_tool_definitions WITH the envelope ``parameters`` wrapper key. A raw
     JSON-schema (type/properties at top level, no ``parameters`` key) leaves
     the model-facing parameters empty -> the model sends empty tool args (the
     R24/R28 empty-args bug). graph_remaining is a no-arg tool, so
     ``properties`` is legitimately ``{}`` — the load-bearing assertion is that
     the ``parameters`` WRAPPER key exists, and that graph_remaining is present
     in the model-facing tool set at all.
  2. DISPATCH: ``tools.graph_remaining({})`` must return JSON the agent can
     consume (``{count, remaining}``) and reflect seeded open nodes (the grill
     backlog), tolerating the ``**kw`` the registry forwards at dispatch.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent          # .../plugins/context_graph
PLUGINS_DIR = PLUGIN_DIR.parent                        # .../plugins
sys.path.insert(0, str(PLUGINS_DIR))

# model-facing defs need the agent on the path + a HERMES_HOME profile
AGENT = os.path.normpath(os.path.join(PLUGINS_DIR, "..", "hermes-agent"))
sys.path.insert(0, AGENT)
os.environ.setdefault(
    "HERMES_HOME",
    os.path.normpath(os.path.join(PLUGINS_DIR, "..", "profiles", "product-owner")),
)

import logging  # noqa: E402
logging.disable(logging.CRITICAL)

from context_graph import context_graph as cg  # noqa: E402
from context_graph import tools, schemas  # noqa: E402


def _model_facing_defs():
    """Drive the REAL model-facing path — the same get_tool_definitions the
    agent runtime calls to build the tool list the model sees."""
    from hermes_cli.plugins import PluginManager
    PluginManager().discover_and_load(force=True)
    from model_tools import get_tool_definitions
    return get_tool_definitions(enabled_toolsets=["context_graph"], quiet_mode=True)


# ── 1. SCHEMA-ENVELOPE regression ────────────────────────────────────────────
class GraphRemainingSchemaEnvelopeTest(unittest.TestCase):
    """graph_remaining's model-facing def must carry the envelope ``parameters``
    wrapper (not a raw JSON-schema with empty params)."""

    def test_graph_remaining_present_in_model_facing_defs(self):
        names = {
            d.get("function", {}).get("name") or d.get("name")
            for d in _model_facing_defs()
        }
        self.assertIn(
            "graph_remaining", names,
            "graph_remaining must be registered + reach the model-facing defs",
        )

    def test_graph_remaining_has_envelope_parameters_key(self):
        defs = {
            d.get("function", {}).get("name") or d.get("name"): d
            for d in _model_facing_defs()
        }
        d = defs["graph_remaining"].get("function", defs["graph_remaining"])
        # the envelope `parameters` wrapper must exist (the empty-args bug is
        # its ABSENCE: a raw JSON-schema puts type/properties at top level).
        self.assertIn(
            "parameters", d,
            "graph_remaining def missing envelope `parameters` key",
        )
        params = d["parameters"]
        self.assertEqual(params.get("type"), "object")
        # no-arg tool: properties is legitimately {} — but the wrapper exists
        self.assertIsInstance(params.get("properties"), dict)

    def test_envelope_schema_constant_shape(self):
        """The schemas.GRAPH_REMAINING constant itself is envelope-shaped."""
        self.assertEqual(schemas.GRAPH_REMAINING["name"], "graph_remaining")
        self.assertIn("description", schemas.GRAPH_REMAINING)
        self.assertIn("parameters", schemas.GRAPH_REMAINING)
        self.assertEqual(
            schemas.GRAPH_REMAINING["parameters"],
            {"type": "object", "properties": {}, "additionalProperties": False},
        )


# ── 2. DISPATCH regression ───────────────────────────────────────────────────
class GraphRemainingDispatchTest(unittest.TestCase):
    """``tools.graph_remaining({})`` must dispatch and return ``{count,
    remaining}`` JSON reflecting the seeded backlog."""

    def setUp(self):
        # Point the plugin at a FRESH temp DB so this never touches the real
        # startup/context_graph.db. init_db(db_path) overrides cg.DB_PATH.
        self._prior_db_path = cg.DB_PATH
        self._tmpdir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self._tmpdir.name, "graph.db")
        cg.init_db(db_path)
        self.addCleanup(self._restore_db)

    def _restore_db(self):
        cg.DB_PATH = self._prior_db_path
        self._tmpdir.cleanup()

    def test_empty_graph_returns_zero_count(self):
        result = json.loads(tools.graph_remaining({}))
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["remaining"], [])

    def test_returns_seeded_open_backlog_as_json(self):
        cg.add_node("root", "venture: TestVenture")
        open_dec_id = cg.add_node("decision", "open decision")
        open_fact_id = cg.add_node("fact", "open fact")
        resolved_id = cg.add_node("decision", "resolved decision")
        cg.resolve_node(resolved_id)  # resolved -> not in the backlog

        result = json.loads(tools.graph_remaining({}))
        self.assertEqual(result["count"], 2)
        remaining_ids = {n["id"] for n in result["remaining"]}
        self.assertEqual(remaining_ids, {open_dec_id, open_fact_id})
        # every remaining node is an open decision/fact (the backlog shape)
        for n in result["remaining"]:
            self.assertEqual(n["status"], "open")
            self.assertIn(n["type"], ("decision", "fact"))

    def test_handler_accepts_extra_kwargs(self):
        """Registry dispatches handler(args, **kw) — must tolerate extra kwargs
        (session_id/profile_name/…) the runtime forwards."""
        result = json.loads(
            tools.graph_remaining({}, session_id="x", profile_name="y")
        )
        self.assertEqual(result["count"], 0)


if __name__ == "__main__":
    unittest.main()
