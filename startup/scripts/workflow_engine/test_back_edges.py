"""
Back-edge detection + template validation tests (T3).

Tests:
  1. Tarjan SCC correctly identifies back-edges in a cyclic template.
  2. All 11 existing DAG templates have zero back-edges.
  3. Template with a cycle but no iteration cap is rejected at load.
  4. Template with unreachable nodes is rejected at load.
  5. Template with _ in workflow ID is rejected at load (existing T2 gate).
  6. Template with explicit entry_nodes bypasses the reachability check.
  7. Template with no exit node but an explicit exit_condition is accepted.
  8. Self-loop edge is detected as a back-edge and requires an iteration cap.
  9. Back-edge with an iteration-referencing condition clause is accepted.

Run: python3 -m pytest test_back_edges.py -v
Or:  python3 test_back_edges.py
"""
import os
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPTS))

from workflow_engine.model import (
    Workflow, Edge, tarjan_scc, annotate_back_edges, Node,
)


def _node(nid: str) -> Node:
    """Minimal Node for graph-analysis tests (skill/body_template required)."""
    return Node(id=nid, profile="qa", skill="", body_template="")


# ═══════════════════════════════════════════════════════════════════════════
# 1. Tarjan SCC — unit tests on the standalone function
# ═══════════════════════════════════════════════════════════════════════════

def test_tarjan_scc_dag_all_singletons():
    """A pure DAG (no cycles) yields one singleton SCC per node."""
    nodes = ["a", "b", "c"]
    edges = [("a", "b"), ("b", "c")]
    sccs = tarjan_scc(nodes, edges)
    # Every SCC is a singleton, no two nodes share a component.
    flat = [c for comp in sccs for c in comp]
    assert sorted(flat) == ["a", "b", "c"]
    assert all(len(comp) == 1 for comp in sccs)


def test_tarjan_scc_two_node_cycle():
    """A two-node cycle forms a single SCC of size 2."""
    nodes = ["build", "review"]
    edges = [("build", "review"), ("review", "build")]
    sccs = tarjan_scc(nodes, edges)
    # Exactly one non-trivial component containing both nodes.
    big = [c for comp in sccs if len(comp) > 1 for c in comp]
    assert sorted(big) == ["build", "review"]


def test_tarjan_scc_self_loop():
    """A self-loop (a→a) is a cycle of one node."""
    sccs = tarjan_scc(["a"], [("a", "a")])
    assert sccs == [{"a"}]


def test_tarjan_scc_disconnected_components():
    """Two independent cycles yield two separate SCCs."""
    nodes = ["a", "b", "c", "d"]
    edges = [("a", "b"), ("b", "a"), ("c", "d"), ("d", "c")]
    sccs = tarjan_scc(nodes, edges)
    nontrivial = {frozenset(comp) for comp in sccs if len(comp) > 1}
    assert nontrivial == {frozenset({"a", "b"}), frozenset({"c", "d"})}


# ═══════════════════════════════════════════════════════════════════════════
# 2. annotate_back_edges — marks is_back_edge correctly
# ═══════════════════════════════════════════════════════════════════════════

def test_annotate_back_edges_cycle_marked():
    """A cyclic edge within an SCC is marked is_back_edge=True."""
    nodes = [_node("build"), _node("review")]
    edges = [
        Edge(from_node="build", to_node="review"),
        Edge(from_node="review", to_node="build"),
    ]
    annotate_back_edges(edges, nodes)
    assert edges[0].is_back_edge is True   # build→review (in cycle)
    assert edges[1].is_back_edge is True   # review→build (in cycle)


def test_annotate_back_edges_dag_none_marked():
    """Acyclic edges are never marked."""
    nodes = [_node("a"), _node("b"), _node("c")]
    edges = [Edge(from_node="a", to_node="b"), Edge(from_node="b", to_node="c")]
    annotate_back_edges(edges, nodes)
    assert all(not e.is_back_edge for e in edges)


def test_annotate_back_edges_exit_edge_not_marked():
    """An edge leaving the SCC (review→ship) is NOT a back-edge."""
    nodes = [_node("build"), _node("review"), _node("ship")]
    edges = [
        Edge(from_node="build", to_node="review"),
        Edge(from_node="review", to_node="build"),
        Edge(from_node="review", to_node="ship"),
    ]
    annotate_back_edges(edges, nodes)
    assert edges[0].is_back_edge is True   # build→review
    assert edges[1].is_back_edge is True   # review→build
    assert edges[2].is_back_edge is False  # review→ship (exits cycle)


# ═══════════════════════════════════════════════════════════════════════════
# 3. End-to-end: known-cyclic template (build→review→FAIL→build back-edge)
# ═══════════════════════════════════════════════════════════════════════════

def _cyclic_template(entry_nodes=None, exit_condition=None,
                     give_iteration_cap=True, cap_via="max_iterations"):
    """Build a build↔review cycle + ship exit. Returns a template dict."""
    cycle_edge = {"from": "review", "to": "build"}
    fwd_edge = {"from": "build", "to": "review"}
    if cap_via == "max_iterations":
        fwd_edge["max_iterations"] = 3
        cycle_edge["max_iterations"] = 3
    elif cap_via == "condition":
        fwd_edge["condition"] = "${nodes.review.output.iteration} < 3"
        cycle_edge["condition"] = "${nodes.review.output.iteration} < 3"
    data = {
        "id": "cyclic-test",
        "name": "Cyclic",
        "nodes": [
            {"id": "build", "profile": "qa"},
            {"id": "review", "profile": "qa"},
            {"id": "ship", "profile": "qa"},
        ],
        "edges": [
            fwd_edge,
            cycle_edge,
            {"from": "review", "to": "ship",
             "condition": "${nodes.review.output.verdict} == 'PASS'"},
        ],
    }
    if entry_nodes is not None:
        data["entry_nodes"] = entry_nodes
    if exit_condition is not None:
        data["exit_condition"] = exit_condition
    return data


def test_cyclic_template_back_edges_detected():
    """A known-cyclic template: both cycle edges flagged, exit edge not."""
    wf = Workflow.from_dict(_cyclic_template(
        entry_nodes=["build"], exit_condition="done"))
    be = {e.from_node + "->" + e.to_node: e.is_back_edge for e in wf.edges}
    assert be["build->review"] is True
    assert be["review->build"] is True
    assert be["review->ship"] is False
    assert wf.declared_entry_nodes == ["build"]
    assert wf.exit_condition == "done"


def test_cyclic_template_with_iteration_condition_accepted():
    """A back-edge whose condition references 'iteration' satisfies the cap gate."""
    wf = Workflow.from_dict(_cyclic_template(
        entry_nodes=["build"], exit_condition="done", cap_via="condition"))
    for e in wf.edges:
        if e.from_node == "build" and e.to_node == "review":
            assert e.is_back_edge is True
            assert e.condition is not None


# ═══════════════════════════════════════════════════════════════════════════
# 4. All 11 existing DAG templates have zero back-edges
# ═══════════════════════════════════════════════════════════════════════════

TEMPLATES_DIR = Path(__file__).parent / "templates"


def test_all_existing_templates_are_dags():
    """Every shipped template must load and have zero back-edges."""
    templates = sorted(TEMPLATES_DIR.glob("*.json"))
    assert len(templates) >= 11, f"Expected >=11 templates, found {len(templates)}"
    for tpl_path in templates:
        wf = Workflow.from_file(tpl_path)
        back_edges = [e for e in wf.edges if e.is_back_edge]
        assert back_edges == [], (
            f"{tpl_path.name}: expected zero back-edges (DAG), "
            f"found {[ (e.from_node, e.to_node) for e in back_edges ]}")


# ═══════════════════════════════════════════════════════════════════════════
# 5. Validation gate: cycle without iteration cap → rejected
# ═══════════════════════════════════════════════════════════════════════════

def test_cycle_without_iteration_cap_rejected():
    """A back-edge with neither max_iterations nor an iteration condition
    must be rejected at load (prevents infinite loops)."""
    data = {
        "id": "uncapped-cycle",
        "name": "Uncapped",
        "entry_nodes": ["build"],
        "exit_condition": "done",
        "nodes": [
            {"id": "build", "profile": "qa"},
            {"id": "review", "profile": "qa"},
        ],
        "edges": [
            {"from": "build", "to": "review"},
            {"from": "review", "to": "build"},
        ],
    }
    with pytest.raises(ValueError, match="iteration cap"):
        Workflow.from_dict(data)


def test_cycle_with_max_iterations_accepted():
    """max_iterations on both cycle edges satisfies the termination gate."""
    wf = Workflow.from_dict(_cyclic_template(
        entry_nodes=["build"], exit_condition="done", cap_via="max_iterations"))
    assert sum(1 for e in wf.edges if e.is_back_edge) == 2


# ═══════════════════════════════════════════════════════════════════════════
# 6. Validation gate: unreachable nodes → rejected
# ═══════════════════════════════════════════════════════════════════════════

def test_unreachable_node_rejected():
    """A node with no path from any entry node is rejected at load.

    Here 'orphan' has an incoming edge from 'ghost', but 'ghost' itself is
    not an entry node (it has an incoming edge from 'a') and there's no edge
    INTO the ghost→orphan chain from any root. So both ghost and orphan are
    unreachable.
    """
    data = {
        "id": "unreachable",
        "name": "Unreachable",
        "nodes": [
            {"id": "root", "profile": "qa"},
            {"id": "child", "profile": "qa"},
            {"id": "ghost", "profile": "qa"},   # incoming edge, but not from root
            {"id": "orphan", "profile": "qa"},  # only reachable via ghost
        ],
        "edges": [
            {"from": "root", "to": "child"},
            {"from": "ghost", "to": "orphan"},  # ghost has incoming? no → it's an entry.
        ],
    }
    # 'ghost' has no incoming edge, so it becomes a seed → reachable.
    # To make a truly unreachable node, it must have an incoming edge whose
    # source is ALSO unreachable. Build a chain: root→child, and x→orphan
    # where x has an incoming edge from orphan (a disconnected cycle with no
    # entry). Use explicit entry_nodes = ["root"] so the cycle isn't seeded.
    data2 = {
        "id": "unreachable2",
        "name": "Unreachable",
        "entry_nodes": ["root"],
        "exit_condition": "done",
        "nodes": [
            {"id": "root", "profile": "qa"},
            {"id": "child", "profile": "qa"},
            {"id": "island1", "profile": "qa"},
            {"id": "island2", "profile": "qa"},
        ],
        "edges": [
            {"from": "root", "to": "child"},
            {"from": "island1", "to": "island2", "max_iterations": 5},
            {"from": "island2", "to": "island1", "max_iterations": 5},
        ],
    }
    with pytest.raises(ValueError, match="unreachable"):
        Workflow.from_dict(data2)


def test_explicit_entry_nodes_bypasses_reachability():
    """Declaring entry_nodes allows a pure cycle (no zero-incoming node) to
    pass the reachability check — the declared entry seeds the BFS."""
    data = {
        "id": "declared-entry",
        "name": "Declared",
        "entry_nodes": ["start"],
        "exit_condition": "done",
        "nodes": [
            {"id": "start", "profile": "qa"},
            {"id": "loop", "profile": "qa"},
            {"id": "end", "profile": "qa"},
        ],
        "edges": [
            {"from": "start", "to": "loop", "max_iterations": 2},
            {"from": "loop", "to": "start", "max_iterations": 2},
            {"from": "start", "to": "end"},
        ],
    }
    wf = Workflow.from_dict(data)  # should NOT raise
    assert wf.declared_entry_nodes == ["start"]


# ═══════════════════════════════════════════════════════════════════════════
# 7. Validation gate: exit-node existence
# ═══════════════════════════════════════════════════════════════════════════

def test_no_exit_node_rejected():
    """A pure cycle with no exit node and no exit_condition is rejected."""
    data = {
        "id": "no-exit",
        "name": "NoExit",
        "entry_nodes": ["a"],
        "nodes": [
            {"id": "a", "profile": "qa"},
            {"id": "b", "profile": "qa"},
        ],
        "edges": [
            {"from": "a", "to": "b", "max_iterations": 3},
            {"from": "b", "to": "a", "max_iterations": 3},
        ],
    }
    with pytest.raises(ValueError, match="exit node"):
        Workflow.from_dict(data)


def test_exit_condition_suppresses_exit_node_gate():
    """Declaring exit_condition bypasses the 'must have exit node' gate."""
    data = {
        "id": "has-exit-cond",
        "name": "HasExitCond",
        "entry_nodes": ["a"],
        "exit_condition": "${iteration} >= 100",
        "nodes": [
            {"id": "a", "profile": "qa"},
            {"id": "b", "profile": "qa"},
        ],
        "edges": [
            {"from": "a", "to": "b", "max_iterations": 100},
            {"from": "b", "to": "a", "max_iterations": 100},
        ],
    }
    wf = Workflow.from_dict(data)  # should NOT raise
    assert wf.exit_condition is not None


# ═══════════════════════════════════════════════════════════════════════════
# 8. No-underscore invariant (existing T2 gate — still works)
# ═══════════════════════════════════════════════════════════════════════════

def test_underscore_in_workflow_id_rejected():
    """A workflow ID containing '_' is rejected (T2 invariant)."""
    data = {
        "id": "has_underscore",
        "name": "Bad",
        "nodes": [{"id": "a", "profile": "qa"}],
        "edges": [],
    }
    with pytest.raises(ValueError, match="underscore"):
        Workflow.from_dict(data)


def test_hyphen_in_workflow_id_accepted():
    """Hyphens are fine — only underscores are forbidden."""
    data = {
        "id": "hyphen-ok",
        "name": "Good",
        "nodes": [
            {"id": "a", "profile": "qa"},
            {"id": "b", "profile": "qa"},
        ],
        "edges": [{"from": "a", "to": "b"}],
    }
    wf = Workflow.from_dict(data)
    assert wf.id == "hyphen-ok"


# ═══════════════════════════════════════════════════════════════════════════
# 9. Self-loop edge
# ═══════════════════════════════════════════════════════════════════════════

def test_self_loop_detected_as_back_edge():
    """A self-loop (a→a) is a cycle of length 1 and is marked a back-edge."""
    edges = [Edge(from_node="a", to_node="a")]
    annotate_back_edges(edges, [_node("a")])
    assert edges[0].is_back_edge is True


def test_self_loop_without_cap_rejected():
    """A self-loop with no iteration cap is rejected (would loop forever)."""
    data = {
        "id": "self-loop-uncapped",
        "name": "SelfLoop",
        "entry_nodes": ["a"],
        "exit_condition": "done",
        "nodes": [{"id": "a", "profile": "qa"}],
        "edges": [{"from": "a", "to": "a"}],
    }
    with pytest.raises(ValueError, match="iteration cap"):
        Workflow.from_dict(data)


def test_self_loop_with_cap_accepted():
    """A self-loop with max_iterations is a valid (if unusual) back-edge."""
    data = {
        "id": "self-loop-capped",
        "name": "SelfLoop",
        "entry_nodes": ["a"],
        "exit_condition": "done",
        "nodes": [{"id": "a", "profile": "qa"}],
        "edges": [{"from": "a", "to": "a", "max_iterations": 10}],
    }
    wf = Workflow.from_dict(data)
    assert wf.edges[0].is_back_edge is True
    assert wf.edges[0].max_iterations == 10


# ═══════════════════════════════════════════════════════════════════════════
# 10. Backward compatibility — DAG with no cycle still loads fine
# ═══════════════════════════════════════════════════════════════════════════

def test_simple_dag_loads_cleanly():
    """A simple linear DAG a→b→c loads with zero back-edges."""
    data = {
        "id": "linear-dag",
        "name": "Linear",
        "nodes": [
            {"id": "a", "profile": "qa"},
            {"id": "b", "profile": "qa"},
            {"id": "c", "profile": "qa"},
        ],
        "edges": [
            {"from": "a", "to": "b"},
            {"from": "b", "to": "c"},
        ],
    }
    wf = Workflow.from_dict(data)
    assert all(not e.is_back_edge for e in wf.edges)
    assert wf.declared_entry_nodes == []
    assert wf.exit_condition is None


# ═══════════════════════════════════════════════════════════════════════════
# Runner (for `python3 test_back_edges.py` without pytest)
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import traceback

    collected = []
    for name, obj in list(globals().items()):
        if name.startswith("test_") and callable(obj):
            marks = getattr(obj, "pytestmark", [])
            if any(getattr(m, "name", "") == "xfail" for m in marks):
                continue
            collected.append((name, obj))

    passed = failed = 0
    for name, fn in collected:
        try:
            fn()
            passed += 1
            print(f"OK  {name}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {name}: {e}")
        except Exception:
            failed += 1
            print(f"ERROR {name}:")
            traceback.print_exc()

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed, {len(collected)} total")
    sys.exit(0 if failed == 0 else 1)
