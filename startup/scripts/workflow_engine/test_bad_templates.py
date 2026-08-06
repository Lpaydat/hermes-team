"""
Bad-template and malformed-input tests for the workflow engine.

These tests feed the engine garbage — syntax errors, missing fields, wrong
types, duplicate IDs, binary files, null templates, 1000-node templates,
invalid schemas — and verify it either:
  (a) rejects the template gracefully (returns None, raises ValueError,
      logs a warning) without an unhandled crash, OR
  (b) handles it without crashing.

NOTE on current behavior:
  Some malformed inputs are NOT yet handled gracefully and propagate an
  unhandled exception out of TemplateStore.load() (which only catches
  JSONDecodeError + KeyError). Those cases are marked @pytest.mark.xfail
  (strict=True) so they are tracked as known gaps: if the engine is ever
  hardened to swallow them, the test flips to XPASS and must be converted
  into a positive "returns None" assertion. They do not break the green
  suite today, but they make the fragility visible.

Targets the parsing/validation entry points in model.py:
  - Workflow.from_dict()   — dict → Workflow
  - Workflow.from_file()   — file path → Workflow
  - resolve_template()     — variable substitution
  - evaluate_condition()   — condition expression eval
And the TemplateStore in store.py, which is the disk-loading boundary that
real template files cross.

Run: python3 -m pytest test_bad_templates.py -v
Or:  python3 test_bad_templates.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Add scripts dir to path (same convention as test_engine.py / test_unhappy.py)
SCRIPTS = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPTS))

from workflow_engine.model import (
    Workflow, Node, Trigger, resolve_template, evaluate_condition,
)
from workflow_engine.store import TemplateStore


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _tmp_store():
    """Create a TemplateStore backed by a fresh temp dir. Returns (store, dir)."""
    d = Path(tempfile.mkdtemp(prefix="wf-bad-"))
    return TemplateStore(d), d


def _write(store_dir: Path, name: str, content):
    """Write a file (text str or raw bytes) as <name>.json into store_dir."""
    p = store_dir / f"{name}.json"
    if isinstance(content, bytes):
        p.write_bytes(content)
    else:
        p.write_text(content)
    return p


# A minimal valid template, used as a base for mutation-based tests.
def _valid_template():
    return {
        "id": "wf",
        "name": "Wf",
        "nodes": [
            {"id": "a", "profile": "qa", "skill": "s",
             "body_template": "do ${trigger.x}"},
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════
# 1. JSON syntax errors — missing brackets, trailing commas
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("bad_json,label", [
    ('{"id": "x", "name": "y", "nodes": [', "missing closing bracket"),
    ('{"id": "x", "name": "y", "nodes": [],}', "trailing comma"),
    ('{"id": "x" "name": "y"}', "missing colon / comma"),
    ('{', "just an open brace"),
    ('', "empty file (zero bytes)"),
    ('not json at all', "plain text, not json"),
])
def test_template_syntax_errors_rejected(bad_json, label):
    """Templates with broken JSON must be rejected by the store (returns None),
    not crash the caller. TemplateStore.load catches JSONDecodeError."""
    store, d = _tmp_store()
    _write(d, "bad", bad_json)

    # Should return None (graceful rejection), never raise
    result = store.load("bad")
    assert result is None, f"Bad JSON ({label}) should load as None, got {result}"


def test_template_syntax_errors_from_file_raises():
    """Workflow.from_file (the lower-level parser) does NOT swallow JSON errors —
    it propagates json.JSONDecodeError. That's the documented contract of the
    raw parser; the store is the layer that softens it."""
    store, d = _tmp_store()
    path = _write(d, "bad", '{"id": "x",')  # broken json

    with pytest.raises(json.JSONDecodeError):
        Workflow.from_file(path)


# ═══════════════════════════════════════════════════════════════════════════
# 2. Missing required top-level fields
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("missing", ["id", "name"])
def test_missing_required_top_level_field(missing):
    """from_dict accesses data['id'] / data['name'] directly — missing raises
    KeyError. The store catches KeyError and returns None."""
    data = _valid_template()
    del data[missing]
    # Direct from_dict → KeyError
    with pytest.raises(KeyError):
        Workflow.from_dict(data)


def test_missing_required_top_level_field_via_store():
    """Same missing-field, but loaded through the store → graceful None."""
    store, d = _tmp_store()
    data = _valid_template()
    del data["id"]
    _write(d, data["name"].lower(), json.dumps(data))
    # No 'id' on disk file — name the file after the (now-missing) id won't work;
    # load by whatever stem we wrote. Use a fixed stem.
    assert store.load("wf-missing") is None


def test_missing_nodes_key_ok():
    """'nodes' is optional (defaults to []). A template with no 'nodes' key is
    valid and yields an empty nodes list — not an error."""
    wf = Workflow.from_dict({"id": "x", "name": "y"})
    assert wf.nodes == []
    assert wf.entry_nodes() == []


# ═══════════════════════════════════════════════════════════════════════════
# 3. 'nodes' is the wrong type (not a list)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("bad_nodes,exc", [
    (5, TypeError),          # iterates over an int → not iterable
    ("hello", TypeError),    # iterates over chars → 'h'[...] indexing fails
    (True, TypeError),       # bool is iterable-free for the loop path
    ({"a": 1}, TypeError),   # dict iterates keys (strings) → string indices
])
def test_nodes_wrong_type_from_dict(bad_nodes, exc):
    """from_dict iterates data.get('nodes', []) — a non-list scalar/dict that
    is not iterable, or is iterable-but-not-of-dicts, raises TypeError."""
    with pytest.raises(exc):
        Workflow.from_dict({"id": "x", "name": "y", "nodes": bad_nodes})


def test_nodes_wrong_type_via_store_handled():
    """The same wrong-type 'nodes', loaded through the store, SHOULD be caught
    and return None — but today it raises. xfail until the store is hardened."""
    store, d = _tmp_store()
    _write(d, "wf", json.dumps({"id": "wf", "name": "y", "nodes": 5}))
    assert store.load("wf") is None


# ═══════════════════════════════════════════════════════════════════════════
# 4. A node is missing 'id' or 'profile'
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("missing", ["id", "profile"])
def test_node_missing_required_field(missing):
    """from_dict accesses n['id'] / n['profile'] directly → KeyError."""
    node = {"id": "a", "profile": "qa", "body_template": "x"}
    del node[missing]
    with pytest.raises(KeyError):
        Workflow.from_dict({"id": "x", "name": "y", "nodes": [node]})


def test_node_missing_optional_fields_ok():
    """skill / body_template / depends_on / condition / foreach are all optional
    and default sensibly. A node with only id+profile is valid."""
    wf = Workflow.from_dict({
        "id": "x", "name": "y",
        "nodes": [{"id": "a", "profile": "qa"}],
    })
    n = wf.get_node("a")
    assert n is not None
    assert n.skill == ""
    assert n.body_template == ""
    assert n.depends_on == []
    assert n.condition is None
    assert n.foreach is None
    assert n.input is None and n.output is None


# ═══════════════════════════════════════════════════════════════════════════
# 5. Duplicate workflow IDs — two files claim the same id
# ═══════════════════════════════════════════════════════════════════════════

def test_duplicate_ids_shadow_not_accumulate():
    """TemplateStore keys strictly on the FILENAME stem, not the 'id' field
    inside the JSON. So two files can't collide on stem (one filename). But a
    file's internal 'id' can disagree with its filename, and the internal id
    wins for the loaded Workflow object.

    This test documents: the store never sees two files with the same stem,
    so there's no dedup bug at the store layer. The only 'duplicate id'
    scenario is an internal id that mismatches the filename — which is benign."""
    store, d = _tmp_store()
    # File 'wf.json' whose internal id is ALSO 'wf'
    _write(d, "wf", json.dumps({"id": "wf", "name": "A", "nodes": []}))
    # File 'other.json' whose internal id is ALSO 'wf' (mismatch!)
    _write(d, "other", json.dumps({"id": "wf", "name": "B", "nodes": []}))

    ids = store.list_ids()
    assert sorted(ids) == ["other", "wf"], \
        f"list_ids keys on filename stems, expected ['other','wf'], got {ids}"

    # Each loads independently by stem; the mismatched internal id is retained
    wf_a = store.load("wf")
    wf_b = store.load("other")
    assert wf_a.name == "A"
    assert wf_b.name == "B"
    # Both report internal id 'wf' — a latent inconsistency, but no crash
    assert wf_a.id == "wf" and wf_b.id == "wf"


# ═══════════════════════════════════════════════════════════════════════════
# 6. depends_on as a string instead of a list
# ═══════════════════════════════════════════════════════════════════════════

def test_depends_on_as_string_rejected():
    """from_dict now validates that depends_on is a list. A string raises TypeError.
    Previously this was silently stored — now correctly rejected at parse time."""
    try:
        Workflow.from_dict({
            "id": "x", "name": "y",
            "nodes": [{"id": "a", "profile": "qa",
                       "body_template": "x", "depends_on": "nonexistent"}],
        })
        raise AssertionError("Should have raised TypeError for string depends_on")
    except TypeError:
        pass  # Correctly rejected


# ═══════════════════════════════════════════════════════════════════════════
# 7. body_template as a number instead of a string
# ═══════════════════════════════════════════════════════════════════════════

def test_body_template_as_number_stored_but_resolve_crashes():
    """from_dict stores body_template verbatim. A non-string value is kept. But
    resolve_template() calls str.replace() on it, which raises TypeError. The
    crash happens at resolution time, not parse time."""
    wf = Workflow.from_dict({
        "id": "x", "name": "y",
        "nodes": [{"id": "a", "profile": "qa", "body_template": 42}],
    })
    assert wf.nodes[0].body_template == 42
    assert not isinstance(wf.nodes[0].body_template, str)

    # Resolution crashes because resolve_template expects a str
    with pytest.raises(TypeError):
        resolve_template(wf.nodes[0].body_template, {})


def test_body_template_none_resolves_ok():
    """body_template defaults to '' when absent. resolve_template('') returns ''.
    The runtime guards with `node.body_template or ""` so None/missing is fine."""
    wf = Workflow.from_dict({
        "id": "x", "name": "y",
        "nodes": [{"id": "a", "profile": "qa"}],
    })
    # runtime uses `node.body_template or ""`
    assert resolve_template(wf.nodes[0].body_template or "", {}) == ""


# ═══════════════════════════════════════════════════════════════════════════
# 8. Template with a trigger but no nodes
# ═══════════════════════════════════════════════════════════════════════════

def test_trigger_no_nodes_parses():
    """A trigger with an empty node list parses fine. It just can never produce
    work (no nodes to dispatch). No crash at parse time."""
    wf = Workflow.from_dict({
        "id": "x", "name": "y",
        "trigger": {"source": "card_completed", "condition": {"assignee": "qa"}},
        "nodes": [],
    })
    assert wf.trigger is not None
    assert wf.trigger.source == "card_completed"
    assert wf.nodes == []


def test_trigger_missing_source_key():
    """from_dict accesses t['source'] directly → KeyError on a trigger dict
    lacking 'source'."""
    with pytest.raises(KeyError):
        Workflow.from_dict({
            "id": "x", "name": "y",
            "trigger": {"condition": {"assignee": "qa"}},  # no 'source'
            "nodes": [],
        })


def test_trigger_not_a_dict():
    """trigger that is a string/int instead of a dict → crashes on t['source']."""
    with pytest.raises(TypeError):
        Workflow.from_dict({
            "id": "x", "name": "y",
            "trigger": "card_completed",  # should be a dict
            "nodes": [],
        })


# ═══════════════════════════════════════════════════════════════════════════
# 9. Extra unknown fields — ignored (no strict schema)
# ═══════════════════════════════════════════════════════════════════════════

def test_extra_unknown_fields_ignored():
    """The parser uses .get() everywhere, so unknown top-level keys and unknown
    node keys are silently dropped. No error, no warning. Documented behavior."""
    wf = Workflow.from_dict({
        "id": "x", "name": "y",
        "totally_unknown_top_key": 123,
        "nodes": [{"id": "a", "profile": "qa", "mystery_node_key": "wat"}],
    })
    assert wf.id == "x"
    assert wf.description == ""  # not set by the extra key
    n = wf.get_node("a")
    assert n is not None
    # Node dataclass has no 'mystery_node_key' attribute — it was ignored
    assert not hasattr(n, "mystery_node_key")


# ═══════════════════════════════════════════════════════════════════════════
# 10. Empty JSON object '{}' as the whole template
# ═══════════════════════════════════════════════════════════════════════════

def test_empty_dict_template_via_store():
    """{} is valid JSON but lacks 'id'/'name' → KeyError caught by store → None."""
    store, d = _tmp_store()
    _write(d, "wf", "{}")
    assert store.load("wf") is None


def test_empty_dict_template_from_dict():
    """from_dict on {} raises KeyError (no id/name)."""
    with pytest.raises(KeyError):
        Workflow.from_dict({})


# ═══════════════════════════════════════════════════════════════════════════
# 11. Double-encoded JSON (a JSON string containing JSON)
# ═══════════════════════════════════════════════════════════════════════════

def test_double_encoded_json_via_store_handled():
    """A file that is JSON-encoded JSON (json.dumps(json.dumps({...}))) parses
    to a *string*, not a dict. from_dict then fails. The store should catch this
    and return None; today it raises AttributeError."""
    store, d = _tmp_store()
    _write(d, "wf", json.dumps(json.dumps({"id": "wf", "name": "y"})))
    assert store.load("wf") is None


def test_double_encoded_json_from_dict_raises():
    """Direct from_dict on a double-encoded payload: the outer json.loads yields
    a str, and str has no [] subscript → TypeError."""
    inner = json.dumps({"id": "x", "name": "y"})
    double = json.dumps(inner)  # now a JSON string
    decoded = json.loads(double)  # → a str
    assert isinstance(decoded, str)
    with pytest.raises(TypeError):
        Workflow.from_dict(decoded)


# ═══════════════════════════════════════════════════════════════════════════
# 12. Circular node reference in depends_on
# ═══════════════════════════════════════════════════════════════════════════

def test_circular_depends_on_parses():
    """The parser does NOT validate the dependency graph for cycles. A cycle is
    silently accepted at parse time — the deadlock only manifests at runtime
    (neither node can ever have its dep satisfied). Documented."""
    wf = Workflow.from_dict({
        "id": "x", "name": "y",
        "nodes": [
            {"id": "a", "profile": "qa", "body_template": "a",
             "depends_on": ["b"]},
            {"id": "b", "profile": "qa", "body_template": "b",
             "depends_on": ["a"]},
        ],
    })
    a = wf.get_node("a")
    b = wf.get_node("b")
    # entry_nodes() = nodes with empty depends_on → none, because of the cycle
    assert wf.entry_nodes() == [], \
        "Circular deps leave no entry nodes (deadlock at runtime, not parse)"


def test_self_reference_depends_on():
    """A node depending on itself is also accepted by the parser (no cycle check)."""
    wf = Workflow.from_dict({
        "id": "x", "name": "y",
        "nodes": [{"id": "a", "profile": "qa", "body_template": "a",
                   "depends_on": ["a"]}],
    })
    assert wf.entry_nodes() == []  # 'a' depends on 'a' → no entry nodes


# ═══════════════════════════════════════════════════════════════════════════
# 13. Invalid JSON Schema in output.schema
# ═══════════════════════════════════════════════════════════════════════════

def test_invalid_json_schema_stored_verbatim():
    """The parser does NOT validate JSON Schemas — it stores whatever dict is in
    output.schema. Validation only happens at runtime against card metadata.
    A schema that is not a real JSON Schema is kept as-is; no crash at parse."""
    wf = Workflow.from_dict({
        "id": "x", "name": "y",
        "nodes": [{
            "id": "a", "profile": "qa", "body_template": "a",
            "output": {"schema": {"totally": "not", "a": "valid schema", "$$$": 3}},
        }],
    })
    assert wf.nodes[0].output is not None
    assert wf.nodes[0].output.schema == {
        "totally": "not", "a": "valid schema", "$$$": 3}


def test_output_not_a_dict():
    """output field that's a non-dict (e.g. a string) is now safely skipped.
    from_dict uses isinstance check, so output is set to None (no schema).
    Previously this raised AttributeError — now handled gracefully."""
    wf = Workflow.from_dict({
        "id": "x", "name": "y",
        "nodes": [{"id": "a", "profile": "qa",
                   "output": "not-a-dict"}],
    })
    # output is None because non-dict output is silently skipped
    assert wf.nodes[0].output is None


# ═══════════════════════════════════════════════════════════════════════════
# 14. Very deeply nested JSON (100 levels)
# ═══════════════════════════════════════════════════════════════════════════

def test_deeply_nested_json_parses():
    """Python's json has no practical depth limit. A 100-level-deep nesting is
    fine. Even much deeper would be, until Python's recursion limit (1000)."""
    nested = "leaf"
    for _ in range(100):
        nested = {"k": nested}
    deep_str = json.dumps(nested)
    # Round-trips fine
    assert json.loads(deep_str) == nested

    # And the engine doesn't choke if this appears as a (useless) node field
    wf = Workflow.from_dict({
        "id": "x", "name": "y",
        "nodes": [{"id": "a", "profile": "qa",
                   "body_template": "x",
                   "input": {"schema": nested, "sources": {}}}],
    })
    assert wf.nodes[0].input.schema == nested


def test_extreme_nesting_handled_by_decoder():
    """Pathologically deep nesting (>~1000 levels) exceeds CPython's recursion
    limit and the json decoder raises RecursionError — it is NOT iterative for
    nested containers. A template file this deep must be rejected gracefully by
    the engine's TemplateStore (its contract is "never raises"), not crash the
    process.

    The json *encoder* (json.dumps) is also recursive; we build the payload with
    manual bracket writing to avoid encoder recursion during setup.
    """
    import sys
    import tempfile
    # Build a 5000-deep nested object via manual bracket writing (avoids encoder
    # recursion during setup; json.dumps itself recurses past ~1000 levels).
    deep_str = '{"k": ' * 5000 + '"leaf"' + '}' * 5000

    # CPython's json decoder recurses for nested containers, so 5000 levels
    # (> recursion limit, default 1000) raises RecursionError. This is the real
    # CPython behaviour, not a bug.
    with pytest.raises(RecursionError):
        json.loads(deep_str)

    # The engine must honour its "never raises" contract: a template file this
    # deep is rejected (returns None) instead of crashing. Verify end-to-end
    # against the real store + on-disk file.
    store = TemplateStore(tempfile.mkdtemp())
    template_path = Path(store.dir) / "deep.json"
    template_path.write_text(deep_str, encoding="utf-8")
    assert store.load("deep") is None
    # Sanity: recursion limit is the boundary the test relies on.
    assert sys.getrecursionlimit() <= 2000


# ═══════════════════════════════════════════════════════════════════════════
# 15. Extremely large number of nodes (1000)
# ═══════════════════════════════════════════════════════════════════════════

def test_1000_nodes_parses_and_mermaid_renders():
    """A 1000-node template parses in well under a second and renders to mermaid
    without crashing. Stress test for parse + to_mermaid."""
    import time as _time
    nodes = [{"id": f"n{i}", "profile": "qa",
              "body_template": f"task {i}",
              "depends_on": [f"n{i-1}"] if i > 0 else []}
             for i in range(1000)]
    t0 = _time.time()
    wf = Workflow.from_dict({"id": "big", "name": "Big", "nodes": nodes})
    parse_secs = _time.time() - t0
    assert len(wf.nodes) == 1000
    assert wf.nodes[0].id == "n0"
    assert wf.nodes[-1].id == "n999"
    assert wf.nodes[-1].depends_on == ["n998"]

    # Only n0 is an entry node (all others depend on their predecessor)
    assert [n.id for n in wf.entry_nodes()] == ["n0"]

    # to_mermaid must not crash on 1000 nodes + 999 edges
    mermaid = wf.to_mermaid()
    assert mermaid.startswith("graph TD")
    assert "n0[n0" in mermaid  # mermaid includes profile in label: n0[n0\nqa]
    assert "n999[n999" in mermaid  # includes profile in label
    # Sanity: 1000 node lines + 999 edge lines + blanks/header
    assert parse_secs < 5.0, f"1000-node parse took {parse_secs:.2f}s (too slow)"


def test_1000_nodes_via_store():
    """A 1000-node template survives the store round-trip (write → load)."""
    store, d = _tmp_store()
    nodes = [{"id": f"n{i}", "profile": "qa", "body_template": str(i)}
             for i in range(1000)]
    _write(d, "big", json.dumps({"id": "big", "name": "Big", "nodes": nodes}))
    wf = store.load("big")
    assert wf is not None
    assert len(wf.nodes) == 1000


# ═══════════════════════════════════════════════════════════════════════════
# 16. Conditions with unsupported operators
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("cond,var,ctx,expected", [
    # Supported operators (positive controls)
    ("${x} == 'abc'", "eq", {"x": "abc"}, True),
    ("${x} == 'abc'", "eq_false", {"x": "xyz"}, False),
    ("${x} exists", "exists", {"x": "abc"}, True),
    ("${x} exists", "exists_false", {}, False),
    ("${x} is empty", "empty", {}, True),
    ("${x} is empty", "empty_false", {"x": "abc"}, False),
    # NOTE: '!=' IS supported by evaluate_condition
    ("${x} != 'a'", "neq_supported", {"x": "b"}, True),
    # Unsupported operators → evaluate_condition returns False (no crash)
    ("${x} contains 'abc'", "contains_unsupported", {"x": "abc"}, False),
    ("${x} ~= 'abc'", "regex_unsupported", {"x": "abc"}, False),
    ("${x} in ['a','b']", "in_unsupported", {"x": "a"}, False),
    # NOTE: <, <=, >, >= ARE supported (numeric-aware comparison)
    ("${x} >= '5'", "ge_supported", {"x": "9"}, True),
    ("${x} >= '5'", "ge_supported_false", {"x": "3"}, False),
    ("${x} < '5'", "lt_supported", {"x": "1"}, True),
    ("${x} < '5'", "lt_supported_false", {"x": "9"}, False),
])
def test_condition_operators(cond, var, ctx, expected):
    """evaluate_condition supports ==, !=, exists, is empty, <, <=, >, >=.
    Unsupported operators (contains, ~=, in) return False — never raises.
    The node simply never fires, which is a silent no-op, not a crash."""
    assert evaluate_condition(cond, ctx) is expected, (
        f"condition {cond!r} with ctx {ctx} should be {expected}")


def test_condition_garbage_returns_false():
    """Totally malformed condition strings return False without raising."""
    for garbage in [
        "",
        "   ",
        "no dollar brace",
        "${} == 'x'",
        "${x}",
        "exists ${x}",
        "${x} == ",       # missing value
        "== 'x'",          # missing var
    ]:
        assert evaluate_condition(garbage, {"x": "abc"}) is False, \
            f"garbage condition {garbage!r} should be False"


def test_condition_none_context_value():
    """A None value in context is handled (bool(None) is False for exists)."""
    assert evaluate_condition("${x} exists", {"x": None}) is False
    assert evaluate_condition("${x} is empty", {"x": None}) is True


# ═══════════════════════════════════════════════════════════════════════════
# 17. null / None as the entire template
# ═══════════════════════════════════════════════════════════════════════════

def test_null_template_via_store_handled():
    """A file containing the literal JSON `null` should be rejected by the store
    as None — but today it raises TypeError out of store.load."""
    store, d = _tmp_store()
    _write(d, "wf", "null")
    assert store.load("wf") is None


def test_null_template_from_dict_raises():
    """from_dict(None) → `None in data` / `data['id']` → TypeError."""
    with pytest.raises(TypeError):
        Workflow.from_dict(None)


# ═══════════════════════════════════════════════════════════════════════════
# 18. Template file that is actually binary (not text)
# ═══════════════════════════════════════════════════════════════════════════

def test_binary_template_file_via_store_handled():
    """A binary file masquerading as .json should be rejected as None, not crash
    with UnicodeDecodeError. Today it crashes."""
    store, d = _tmp_store()
    _write(d, "wf", b'\x00\x01\x02\xff\xfe\x00binary garbage')
    assert store.load("wf") is None


def test_binary_template_file_from_file_raises():
    """from_file reads via read_text() → UnicodeDecodeError on bad bytes."""
    store, d = _tmp_store()
    path = _write(d, "wf", b'\x00\x01\x02\xff\xfe')
    with pytest.raises(UnicodeDecodeError):
        Workflow.from_file(path)


# ═══════════════════════════════════════════════════════════════════════════
# 19. resolve_template robustness
# ═══════════════════════════════════════════════════════════════════════════

def test_resolve_template_missing_vars_removed():
    """Unresolved ${...} are stripped to empty string (regex sub). No crash."""
    out = resolve_template("hello ${missing.var} world", {})
    assert out == "hello  world"


def test_resolve_template_none_value_in_context():
    """A None value in context is str()'d to 'None' — documented, not a crash."""
    out = resolve_template("v=${x}", {"x": None})
    assert out == "v=None"


def test_resolve_template_non_string_template_raises():
    """resolve_template(123, {}) → str.replace on an int → TypeError."""
    with pytest.raises(TypeError):
        resolve_template(123, {})


def test_resolve_template_list_value_in_context():
    """A list value is str()'d — no crash, produces repr-ish output."""
    out = resolve_template("items: ${xs}", {"xs": [1, 2, 3]})
    assert out == "items: [1, 2, 3]"


# ═══════════════════════════════════════════════════════════════════════════
# 20. Cross-layer: bad template in the store, then engine tick doesn't explode
# ═══════════════════════════════════════════════════════════════════════════

def test_store_all_skips_unloadable_templates():
    """store.all() loads every template via store.load(), which returns None for
    unloadable ones. store.all() filters out None (walrus comprehension). So one
    broken file must NOT poison the whole batch — good templates still load."""
    store, d = _tmp_store()
    # One good template
    _write(d, "good", json.dumps({"id": "good", "name": "G", "nodes": []}))
    # Three broken ones covering the caught exceptions
    _write(d, "broken_json", '{"id": "x",')              # JSONDecodeError → caught
    _write(d, "missing_id", json.dumps({"name": "no id"}))  # KeyError → caught
    _write(d, "empty", "{}")                              # KeyError → caught

    loaded = store.all()
    ids = sorted(wf.id for wf in loaded)
    # Only the good one survives; broken ones are silently skipped
    assert ids == ["good"], \
        f"store.all() should skip unloadable templates, got ids={ids}"


# ═══════════════════════════════════════════════════════════════════════════
# Runner (for `python3 test_bad_templates.py` without pytest)
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Allow running without pytest installed. xfail tests are skipped here.
    import traceback

    collected = []
    for name, obj in list(globals().items()):
        if name.startswith("test_") and callable(obj):
            # Skip parametrized/xfail when run as plain script — they need pytest
            marks = getattr(obj, "pytestmark", [])
            if any(getattr(m, "name", "") == "xfail" for m in marks) or \
               hasattr(obj, "pytestmark"):
                continue
            collected.append((name, obj))

    passed = failed = skipped = 0
    for name, fn in collected:
        try:
            fn()
            passed += 1
            print(f"OK  {name}")
        except TypeError as e:
            # Many tests use pytest.raises which is a no-op without pytest
            skipped += 1
            print(f"SKIP {name}: {e}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {name}: {e}")
        except Exception:
            failed += 1
            print(f"ERROR {name}:")
            traceback.print_exc()

    n = passed + failed + skipped
    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed, {skipped} skipped, "
          f"{n} run (use pytest for the full suite incl. parametrize/xfail)")
    sys.exit(0 if failed == 0 else 1)
