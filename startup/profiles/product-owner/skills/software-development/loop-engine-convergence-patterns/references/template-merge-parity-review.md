# Template Merge Parity Review — don't lose content when consolidating workflows

## When to use

When merging two or more trigger-chained workflow templates into a single
unified graph (e.g. qa-gate + refactor-cycle → milestone-gate). Trigger
suppression and prefix mismatches make separate trigger-chained workflows
fragile — unifying into one graph is structurally safer. But the merge itself
can silently drop body content and schema fields.

## The technique

After writing the merged template, run a programmatic parity review against
the originals:

### 1. Extract and compare

```python
import json, os

TEMPLATE_DIR = os.path.expanduser("~/.hermes-teams/startup/scripts/workflow_engine/templates")
old1 = json.load(open(f"{TEMPLATE_DIR}/old-template-1.json.disabled"))
old2 = json.load(open(f"{TEMPLATE_DIR}/old-template-2.json.disabled"))
new  = json.load(open(f"{TEMPLATE_DIR}/new-unified-template.json"))

def get_schema(d, nid):
    for n in d["nodes"]:
        if n["id"] == nid:
            return n.get("output", {}).get("schema", {})
    return {}

def get_body(d, nid):
    for n in d["nodes"]:
        if n["id"] == nid:
            return n.get("body_template", "")
    return ""
```

### 2. Schema field parity

For each old node mapped to a new node:
- Compare `required` arrays — any field in old but not in new is a regression.
- Compare `properties` keys — any property in old but not in new is a regression.

### 3. Body content parity

For each old node body vs new node body:
- Extract substantive lines (>20 chars, not headers, not JSON blocks).
- Diff: `old_phrases - new_phrases` = lost content.
- Check each lost phrase — is it intentional (e.g. `${nodes.check-merge.*}`
  removed because check-merge node was dropped) or accidental?

### 4. Edge parity (normalize renamed nodes)

If nodes were renamed (e.g. `scan` → `refactor-scan` to avoid collisions),
normalize the names before comparing edge sets. Check:
- `old_edges - new_edges` = lost routing (MUST be empty after normalization).
- `new_edges - old_edges` = new connections (expected — these are the
  cross-stage links, e.g. `qa-verdict → refactor-scan`).

## Regressions caught in practice (milestone-gate merge, 2026-08-08)

Three regressions were found during the parity review of qa-gate +
refactor-cycle → milestone-gate:

| Node | What was lost | Impact |
|------|--------------|--------|
| qa-quick | Entire MANDATORY completion metadata contract (verdicts/checks/exploration arrays) — body shrunk 2649→939 chars | Engine validates these required schema fields; missing body instructions → agent doesn't produce them → card fails and retries |
| qa-verdict | "cite ONE key piece of evidence inline" instruction + `commit_tested` required field | Verdict becomes less self-contained; schema rejects metadata without commit_tested |
| route-bug | "bug-handoff skill (loaded automatically)" reference | Agent doesn't know to use the skill for routing decisions |
| refactor-scan | "Do NOT open a browser" + metadata field documentation | Agent might write HTML reports; doesn't document what each metadata field means |
| refactor-review | "Stop condition" section + metadata field documentation | Agent doesn't know what verdict=stop means |

All 5 were restored by patching the new template's body_template and schema
fields to match the originals (adapting `${nodes.check-merge.*}` references
to `${trigger.*}` since check-merge was intentionally dropped).

## Why this matters

Body templates encode months of polish — adversarial test phases, evidence
requirements, security check enumerations, completion metadata contracts.
These are the difference between a QA card that runs 31 behavior tests with
edge-case probes and one that just says "test it." Losing them during a merge
silently degrades quality. The structural validation (parses, loads, edges
valid) won't catch content loss — only a diff will.

## Run the review TWICE minimum

The first parity pass finds the BIG regressions (qa-quick lost its entire
2649-char schema, qa-verdict lost commit_tested). But a SECOND pass — running
the same diff after fixing the first batch — finds DIFFERENT, subtler losses:

- refactor-review: lost "drop Speculative unless reviewer upgraded it" +
  "Order by severity (Strong first)" (the filtering + ordering rules)
- refactor-scan: lost "(interface nearly as complex as implementation)" —
  the parenthetical definition of what "shallow module" means
- route-bug: lost "bug-handoff skill (loaded automatically)" reference

Each review pass focuses on the largest diffs first and misses smaller ones.
After patching the first batch, re-run the same parity script — the
previously-masked smaller losses become visible. Two passes caught everything;
one pass would have shipped 3 regressions.

This is the user's "review again" correction — they instinctively knew one
pass wasn't enough. Encode it: **merge parity review requires at least two
passes, each finding different-sized regressions.**

## Reference

See `references/milestone-gate-unification.md` for the design rationale of
merging qa-gate + refactor-cycle into milestone-gate.
