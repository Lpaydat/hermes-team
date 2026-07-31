# Workflow Node I/O Contracts — Schema Design Pattern

The data-shape complement to `engine-read-write-contract.md` (which covers the
engine's *access* model). This covers the engine's *validation* model: how each
pipeline node declares what it consumes (input) and produces (output), and how
the engine validates output structurally rather than lexically.

Grounded in the design session that produced `docs/workflow-node-io-schema.md` +
`docs/schemas/` (crr-pos-v2, Jul 2026).

## The core insight: structural schemas replace regex-based trigger detection

The workflow engine's QA-trigger (phase 5, `workflow-engine.py` L499-639)
detected "a merge happened" by regex-scanning verifier/debugger card **summaries**
for "merged to master/main" patterns. It took 7 approaches and 15 gaps to
stabilize (documented in the main skill's Known Quirks). **Root cause:** the
engine parses natural language to detect structural events.

**The fix:** each node type declares an output schema (JSON Schema Draft
2020-12). The engine validates `run.metadata` against it. Downstream nodes bind
to upstream outputs via typed variable substitution. Triggers become structural,
not lexical.

The critical invariant — "a verifier that merges MUST carry the commit SHA" —
becomes a conditional schema that *cannot* be bypassed:

```json
"allOf": [
  {
    "if": { "properties": { "verdict": { "const": "PASS" } } },
    "then": { "required": ["merged_commit_sha"] }
  }
]
```

This eliminates the entire regex/title-filter/lookback-window apparatus. The
trigger becomes a typed query:

```sql
-- OLD: fragile natural-language scan (workflow-engine.py L577-597)
SELECT ... WHERE t.assignee IN ('verifier','debugger') ...
-- then filter: "merged" in r["summary"].lower()

-- NEW: structural
SELECT metadata->>'merged_commit_sha' FROM task_runs
WHERE metadata->>'verdict' = 'PASS'
  AND metadata->>'merged_commit_sha' IS NOT NULL
```

## Every node has BOTH input and output schemas

| | Input schema | Output schema |
|---|---|---|
| Purpose | Declare needs; bind upstream outputs | Declare produces; engine-validation contract |
| Validates at | Dispatch time (pre-flight) + body templating | Completion time (post-flight) |
| Failure mode | Missing/binding-fails → node never dispatches | Validation fail → flag + optional retry |

- **Output-only is insufficient** — can't pre-flight that required upstream values
  exist before dispatching (wasted dispatch on a card that immediately blocks),
  and can't template the card body (today they're string-concatenated f-strings,
  the fragility we're replacing).
- **Input-only is insufficient** — can't structurally validate completion and
  trigger downstream nodes (back to regex on summaries).

## The grounding method — formalize what already exists

The system already has a de facto schema — it's just not enforced. Before
writing new schemas, read the **actual `kanban_complete(metadata={...})` shapes**
each profile's SKILL.md already documents:

| Stage | Real metadata keys today | Source skill |
|---|---|---|
| Architect | `dod_verdict: {behaviors, defect_traces, dod_met, score, ...}`, `design_doc`, `adr` | design-council/dod-contract.md |
| Developer | `branch_name, worktree_path, changed_files, harness_session_id, chain_root` | developer-loop §5 |
| Verifier | `verdict, findings_count, acs_verified, iteration, adr_conformance` | adversarial-review §Stamp the verdict |
| QA build | `image_tag: "qa-test:<id>", container_port, build_success` | live-testing §Phase 2 |
| QA verdict | `verdicts: [...], findings: [...], claims_tested, claims_proven` | live-testing §Phase 7 |
| Debugger | `branch_name, worktree_path, bug_id, fix_commit_sha` | debug-loop |

Search for these patterns across the profile tree to discover existing shapes:

```
kanban_complete\(metadata=\{|metadata=\{.*verdict|metadata=\{.*branch_name
```

The DoD-contract skill already documents the validation loop: *"A completion
without the structured key → verdict=None → re-evaluate, bounded by
MAX_REEVAL_ATTEMPTS=3, then escalates."* The schema model formalizes what
already works — it does not invent a parallel contract.

## What goes in input vs output

**Input bindings** (resolved from `${nodes.<id>.output.<key>}`,
`${trigger.<key>}`, `${env.<key>}` before dispatch):

- File paths (spec_path, design_doc, worktree_path)
- Bead IDs (bead_id, bug_id, epic_id)
- Data from previous nodes (branch_name, image_tag, commit_sha, verdict)
- Trigger context (card_id, bead_type, board)
- Environment (project_dir, container_runtime)
- Optional `expected_schema` for pre-flight constraints (e.g. branch_name ≠ main)

**Output metadata** (validated against schema at completion):

- Files created (design_doc, adr.path, transcript_path)
- Beads created (bug_beads_created, bead_id)
- Verdicts (verdict PASS/FAIL/ESCALATE, dod_met)
- Metrics (score, claims_proven, findings_count, total_cost_usd)
- Commit SHAs (merged_commit_sha — the structural merge signal)
- Git refs (branch_name, worktree_path)
- Container artifacts (image_tag, container_port)

## Validation failure policy

| Action | Behavior | When |
|---|---|---|
| `flag` | Comment with errors; card still completes | Non-critical output |
| `block` | Move to blocked with error as reason | Required for downstream |
| `retry` | Re-dispatch up to max_retries with failure context | Transient (agent forgot a field) |
| `flag_and_block` (default) | Both — not "done" until output validates | All nodes with downstream consumers |

Retry carries the `[SCHEMA-VALIDATION-FAILED]` block listing which fields failed
+ the expected schema. This mirrors the existing DoD-contract re-evaluate pattern.

## Output → input flow (variable substitution)

```
${nodes.<id>.output.<key>}   # from a completed upstream node's validated output
${trigger.<key>}             # from the trigger event (bead_id, commit_sha, ...)
${env.<key>}                 # environment variable
${workflow.<key>}            # workflow-level metadata (board, project_dir)
```

The engine resolves bindings before dispatch and templates the card body. If an
upstream node didn't produce a required output (validation failed), the
downstream node never dispatches — no orphan cards.

## Verifying conditional schemas before claiming correctness

JSON Schema `allOf`/`if-then` conditionals are the load-bearing mechanism. Don't
just write them — **exercise them with real sample data** before signing off:

```python
from jsonschema import Draft202012Validator
v = Draft202012Validator(verifier_schema)

# Must REJECT: PASS without merged_commit_sha
errs = list(v.iter_errors({"verdict": "PASS", "findings_count": {}, "acs_verified": 3, "iteration": 1}))
assert errs  # the invariant that replaces regex

# Must ACCEPT: FAIL without merged_commit_sha (no merge on fail)
errs = list(v.iter_errors({"verdict": "FAIL", "findings_count": {"critical": 1}, "acs_verified": 3, "iteration": 1}))
assert not errs
```

Use `Draft202012Validator.check_schema(schema)` to validate the schema itself
against the Draft 2020-12 meta-schema at load time.

## Deliverable artifacts

The full design doc + standalone schema files from the grounding session (in the
crr-pos-v2 project repo):

- `docs/workflow-node-io-schema.md` — complete design proposal with envelope
  schema, per-node-type output schemas, worked examples, migration path
- `docs/schemas/workflow-node.json` — the node envelope schema
- `docs/schemas/outputs/*.json` — architect, developer, verifier, qa-build,
  qa-verdict, debugger output schemas
