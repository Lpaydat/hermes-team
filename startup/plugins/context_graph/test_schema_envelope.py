"""Regression: context_graph tool schemas must reach the model with populated
`parameters.properties` (the envelope format register_tool/get_tool_definitions
expects — {name, description, parameters:{...}}). If schemas are raw JSON-Schema
(type/properties/required at top level, no `parameters` key), the model-facing
def has empty parameters.properties -> the model has no params to fill -> empty
tool args (the R24/R28 graph_context/graph_add_node empty-args bug).

This test drives the REAL model-facing path (get_tool_definitions) and asserts
every context_graph tool exposes its params to the model.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.normpath(os.path.join(HERE, "..", "..", "hermes-agent"))
sys.path.insert(0, AGENT)
os.environ.setdefault("HERMES_HOME", os.path.normpath(os.path.join(HERE, "..", "..", "profiles", "product-owner")))

import logging
logging.disable(logging.CRITICAL)


def _model_facing_defs():
    from hermes_cli.plugins import PluginManager
    PluginManager().discover_and_load(force=True)
    from model_tools import get_tool_definitions
    return get_tool_definitions(enabled_toolsets=["context_graph"], quiet_mode=True)


# expected params per tool (the load-bearing ones the model must fill)
EXPECTED = {
    "graph_add_node": ["node_type", "title"],
    "graph_add_edge": ["source_id", "target_id", "edge_type"],
    "graph_resolve_node": ["node_id"],
    "graph_pull": ["topic"],
    "graph_context": ["node_id"],
    "graph_tree": ["root_id"],
}


def test_every_tool_exposes_params_to_model():
    defs = {d.get("function", {}).get("name") or d.get("name"): d for d in _model_facing_defs()}
    missing_tools = [t for t in EXPECTED if t not in defs]
    assert not missing_tools, f"tools missing from model-facing set: {missing_tools}"

    failures = []
    for tool, required_params in EXPECTED.items():
        d = defs[tool].get("function", defs[tool])
        params_props = (d.get("parameters") or {}).get("properties") or {}
        present = list(params_props.keys())
        for p in required_params:
            if p not in present:
                failures.append(f"{tool}: missing param '{p}' in parameters.properties (have {present})")
    assert not failures, "schema-delivery bug:\n  " + "\n  ".join(failures)
