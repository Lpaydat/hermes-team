"""
Tests for the upgraded condition engine: AND/OR precedence, numeric
comparison operators (<, <=, >, >=), and numeric type coercion.

These pin the grammar defined in DESIGN-stateless-graph.md §Condition engine
upgrade:
    condition := clause (OR clause)*
    clause    := atom (AND atom)*
    atom      := ${var} <op> <value>
where AND binds tighter than OR and numeric operators coerce both sides via
float() (never stringify-then-compare, which would make "10" < "3" True).

Run: python3 -m pytest test_condition_engine.py -v
Or:  python3 test_condition_engine.py
"""
import sys
from pathlib import Path

SCRIPTS = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPTS))

from workflow_engine.model import evaluate_condition


# ═══════════════════════════════════════════════════════════════════════════
# §1  Acceptance criteria (verbatim from the ticket)
# ═══════════════════════════════════════════════════════════════════════════

def test_ac_compound_and_true():
    """AC: compound AND with numeric clause returns True when both hold."""
    assert evaluate_condition(
        "${x} == 'PASS' AND ${y} < 3", {"x": "PASS", "y": 2}
    ) is True


def test_ac_compound_and_short_circuits_on_false():
    """AC: compound AND returns False when the first atom is False.

    This is the short-circuit case: ${x} == 'PASS' is False, so ${y} < 3 is
    never required to be the deciding factor.
    """
    assert evaluate_condition(
        "${x} == 'PASS' AND ${y} < 3", {"x": "FAIL", "y": 1}
    ) is False


def test_ac_numeric_int_not_lexicographic():
    """AC: ${x} < 10 with x=5 is True (numeric, not lexicographic)."""
    assert evaluate_condition("${x} < 10", {"x": 5}) is True


def test_ac_numeric_string_coerced():
    """AC: ${x} < 10 with x='5' (string) is True via float() coercion."""
    assert evaluate_condition("${x} < 10", {"x": "5"}) is True


# ═══════════════════════════════════════════════════════════════════════════
# §2  Precedence: AND binds tighter than OR
# ═══════════════════════════════════════════════════════════════════════════

def test_precedence_and_before_or_true_via_left_group():
    """A AND B OR C AND D — first group (A AND B) true → whole true."""
    assert evaluate_condition(
        "${a} == '1' AND ${b} == '2' OR ${c} == '3' AND ${d} == '4'",
        {"a": "1", "b": "2", "c": "x", "d": "x"},
    ) is True


def test_precedence_and_before_or_true_via_right_group():
    """A AND B OR C AND D — left group false, right group true → whole true."""
    assert evaluate_condition(
        "${a} == '1' AND ${b} == '2' OR ${c} == '3' AND ${d} == '4'",
        {"a": "1", "b": "WRONG", "c": "3", "d": "4"},
    ) is True


def test_precedence_and_before_or_false_when_both_groups_false():
    """A AND B OR C AND D — both groups have a false atom → whole false."""
    assert evaluate_condition(
        "${a} == '1' AND ${b} == '2' OR ${c} == '3' AND ${d} == '4'",
        {"a": "1", "b": "WRONG", "c": "3", "d": "WRONG"},
    ) is False


def test_precedence_single_or():
    """A OR B — second atom true even though first false."""
    assert evaluate_condition(
        "${a} == 'no' OR ${b} == 'yes'", {"a": "x", "b": "yes"}
    ) is True


def test_precedence_single_and():
    """A AND B — both atoms true."""
    assert evaluate_condition(
        "${a} == 'x' AND ${b} == 'y'", {"a": "x", "b": "y"}
    ) is True


def test_or_short_circuits_on_first_true():
    """A OR B — first group true; the second group references a missing var,
    which would error if evaluated (it won't be, due to short-circuit)."""
    assert evaluate_condition(
        "${a} == '1' OR ${b} == '2'", {"a": "1"}
    ) is True


# ═══════════════════════════════════════════════════════════════════════════
# §3  Numeric operators and type coercion
# ═══════════════════════════════════════════════════════════════════════════

def test_numeric_less_than_true():
    assert evaluate_condition("${x} < 10", {"x": 5}) is True


def test_numeric_less_than_false_at_boundary():
    assert evaluate_condition("${x} < 10", {"x": 10}) is False


def test_numeric_greater_than_true():
    assert evaluate_condition("${x} > 5", {"x": 10}) is True


def test_numeric_greater_than_false():
    assert evaluate_condition("${x} > 5", {"x": 5}) is False


def test_numeric_ge_equal():
    assert evaluate_condition("${x} >= 5", {"x": 5}) is True


def test_numeric_le_equal():
    assert evaluate_condition("${x} <= 5", {"x": 5}) is True


def test_numeric_float_values():
    assert evaluate_condition("${x} >= 3.5", {"x": 3.5}) is True
    assert evaluate_condition("${x} < 3.5", {"x": 3.4}) is True
    assert evaluate_condition("${x} <= 3.5", {"x": 3.6}) is False


def test_numeric_rhs_quoted_string_still_coerces():
    """A quoted numeric RHS ('3') is eligible for numeric coercion."""
    assert evaluate_condition("${x} <= '3'", {"x": "2"}) is True
    assert evaluate_condition("${x} > '3'", {"x": 4}) is True


def test_numeric_lhs_string_coerced():
    """String context value coerced to number for comparison."""
    assert evaluate_condition("${x} < 10", {"x": "5"}) is True
    assert evaluate_condition("${x} < 10", {"x": "50"}) is False


def test_numeric_lexicographic_guard_int():
    """REGRESSION GUARD: 10 < 3 must be False (would be True if stringified)."""
    assert evaluate_condition("${x} < 3", {"x": 10}) is False


def test_numeric_lexicographic_guard_string():
    """REGRESSION GUARD: '10' < '3' must be False (string-coerced to numbers)."""
    assert evaluate_condition("${x} < 3", {"x": "10"}) is False


def test_numeric_coercion_falls_back_to_string_when_non_numeric():
    """When float() fails on either side, fall back to string comparison."""
    # 'a' < 'b' lexicographically
    assert evaluate_condition("${x} < 'b'", {"x": "a"}) is True
    assert evaluate_condition("${x} < 'b'", {"x": "z"}) is False


def test_numeric_coercion_negative_numbers():
    assert evaluate_condition("${x} < 0", {"x": -5}) is True
    assert evaluate_condition("${x} >= -1", {"x": -1}) is True


# ═══════════════════════════════════════════════════════════════════════════
# §4  Design's loop example (back-edge iteration cap)
# ═══════════════════════════════════════════════════════════════════════════

def test_loop_iteration_below_cap():
    """The design's loop-guard condition: iteration < cap → continue looping."""
    assert evaluate_condition(
        "${nodes.repair.iteration} < 3", {"nodes.repair.iteration": 2}
    ) is True


def test_loop_iteration_at_cap_exits():
    """When iteration reaches the cap, the back-edge condition is False."""
    assert evaluate_condition(
        "${nodes.repair.iteration} < 3", {"nodes.repair.iteration": 3}
    ) is False


def test_loop_iteration_string_value():
    """Iteration value arriving as a string (from resolved templates) coerces."""
    assert evaluate_condition(
        "${nodes.repair.iteration} < 3", {"nodes.repair.iteration": "1"}
    ) is True


def test_loop_condition_compound_with_verdict():
    """A realistic compound loop guard: keep looping while verdict is FAIL
    AND iterations remain."""
    assert evaluate_condition(
        "${v} == 'FAIL' AND ${i} < 3", {"v": "FAIL", "i": 1}
    ) is True
    assert evaluate_condition(
        "${v} == 'FAIL' AND ${i} < 3", {"v": "PASS", "i": 1}
    ) is False


# ═══════════════════════════════════════════════════════════════════════════
# §5  Existing 4 operators still work unchanged (no regression)
# ═══════════════════════════════════════════════════════════════════════════

def test_existing_exists():
    assert evaluate_condition("${v} exists", {"v": "x"}) is True
    assert evaluate_condition("${v} exists", {"v": ""}) is False
    assert evaluate_condition("${v} exists", {}) is False


def test_existing_is_empty():
    assert evaluate_condition("${v} is empty", {"v": ""}) is True
    assert evaluate_condition("${v} is empty", {"v": 0}) is True
    assert evaluate_condition("${v} is empty", {"v": "x"}) is False
    assert evaluate_condition("${v} is empty", {}) is True


def test_existing_equality():
    assert evaluate_condition("${v} == 'PASS'", {"v": "PASS"}) is True
    assert evaluate_condition("${v} == 'PASS'", {"v": "FAIL"}) is False


def test_existing_inequality():
    assert evaluate_condition("${v} != 'FAIL'", {"v": "PASS"}) is True
    assert evaluate_condition("${v} != 'FAIL'", {"v": "FAIL"}) is False


def test_existing_dot_path_resolution():
    """Dot-path keys (nodes.x.output.y) work as before."""
    ctx = {"nodes.check.output.verdict": "PASS"}
    assert evaluate_condition(
        "${nodes.check.output.verdict} == 'PASS'", ctx
    ) is True


def test_existing_bool_and_none_values():
    """str(True) == 'True', str(None) == 'None' — preserved semantics."""
    assert evaluate_condition("${v} == 'True'", {"v": True}) is True
    assert evaluate_condition("${v} == 'None'", {"v": None}) is True
    assert evaluate_condition("${v} exists", {"v": None}) is False


def test_existing_malformed_returns_false():
    """Unrecognized forms return False (safe default)."""
    assert evaluate_condition("this is not valid", {}) is False
    assert evaluate_condition("", {}) is False


def test_existing_regex_special_chars_literal():
    """Values with regex special chars compare literally (str ==, not regex)."""
    ctx = {"v": "/tmp/[test]/"}
    assert evaluate_condition("${v} == '/tmp/[test]/'", ctx) is True


# ═══════════════════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════════════════

def _run_all():
    tests = [
        (name, fn)
        for name, fn in sorted(globals().items())
        if name.startswith("test_") and callable(fn)
    ]
    failures = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK: {name}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL: {name} — {e}")
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"ERROR: {name} — {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return failures == 0


if __name__ == "__main__":
    import sys
    sys.exit(0 if _run_all() else 1)
