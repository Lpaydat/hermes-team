# ngin Spec/ADR Validation + Repo Management

Reference for: (1) the result of validating ngin's spec + 8 ADRs against the
evolved Hermes workflow engine, and (2) repo management techniques for repos
with multi-GB worktrees and build artifacts.

## Part 1: Spec/ADR Validation Result (2026-08-08)

The ngin spec (`docs/SPEC-harness-agnostic-platform.md`) and all 8 ADRs
(`docs/adr/0001` through `docs/adr/0008`) were checked against the current
state of the Hermes workflow engine and found to remain valid.

### What was checked

The Hermes workflow engine evolved significantly since the ngin spec was written:
- `loop_engine` plugin — convergence tool (runner executes, verifier checks, advance/replan/escalate). Used in dev-dispatch's route-decompose node and tech-lead-execute's plan node.
- `card_mode` dispatch strategies — delegate and chain modes for subagent spawning
- `foreach` + `subworkflow` combined dispatch — `dispatch_foreach_subworkflow`
- Milestone auto-refactor — decompose→milestone-plan creates `[milestone-NN]` cards with parent deps
- Verifier lint enforcement (Phase 3.5) — make lint + make format-check on every dev card
- Board isolation — active-projects.json allowlist for trigger scanning

### Why these don't affect ngin's design

The ngin design documents reference two external sources with different roles:
1. **Hermes engine** = "proven patterns to port" — the WHAT: triggers, back-edges, dead-branch, completion fence, conditional edges, foreach, subworkflows. These are concepts, not implementation details.
2. **nginbot-api** = "the format to adopt" — the HOW: IGraphSchema, source directives, composite edges, expr-eval.

The Hermes-side changes are all **implementation details of the Hermes engine**:
- loop_engine is a Hermes tool, not an ngin spec concept
- card_mode is a dispatch strategy detail, not a new node type
- foreach+subworkflow combined dispatch is an impl detail of node types the spec already covers (stories 27+28)
- Milestone auto-refactor is a Hermes-specific workflow template, not an ngin design concern
- Verifier lint enforcement is a template detail

None of these change the concepts ngin ports or the format ngin adopts.

### The format divergence is intentional

The ngin daemon's graph module (`daemon/src/graph/`) follows the nginbot-api
IGraphSchema format: nodes as dict, NodeType enum (SYSTEM/FUNCTION/TASK/GRAPH/
COMMAND/WAIT), dataSchemaVersion, source directives. This is intentionally
different from the Hermes engine's simpler list-based format (flat node array +
flat edge array, `${var}` data flow). No drift — the divergence is by design
per ADR-0003.

### Conclusion

No spec or ADR updates needed. If a future session questions whether the
spec/ADRs are still valid, this is the verification: they are.

---

## Part 2: Repo Management for Large Worktree Repos

ngin has 7.8GB of git worktrees + 1.3GB of build artifacts. A plain `cp -r`
backup is impractical. Use git to capture the full working tree.

### Backup pattern (git branch + tag)

```bash
cd ~/workspace/ngin
git add -A
git commit -m "backup: <description of what's being captured>"
git tag backup-<purpose>-<date>        # immutable reference point
git branch backup/<purpose>-<date>     # easy checkout name
```

This captures: committed work + uncommitted modifications + untracked files.
Restore with `git reset --hard backup/<purpose>-<date>`.

### Worktree safety check before deletion

Worktrees can contain substantial code that exists ONLY there (not in the main
tree). Before deleting any worktree, check:

```bash
cd <worktree>
git diff --stat                    # uncommitted modifications
git status --short --untracked-files=all   # untracked files (code, not .pi/)
```

Then verify whether the work exists in the main tree:
```bash
diff <main-tree-file> <worktree-file>   # compare line counts + content
```

Known ngin worktrees with unique work (as of 2026-08-08):
- `.worktrees/t_48b6cf41` (ticket-18): migrations 014-018 (workflow_instances, node_states, trigger_keys, trigger_watermark, block_semantics, workspace_kind). Main tree only has migration 013.
- `.worktrees/ticket-30-gc` (ticket-30): retention.rs is 996 lines vs 459 in main — 537 lines of workflow GC code (`prune_workflow_data`).
- `.worktrees/t_ticket19_walker` (ticket-19): expr.rs — 1179 lines, the expression engine. Completely absent from main tree.

### target/ cleanup

`target/` (Rust build artifacts, 1.3GB) is fully regenerable. Safe to delete
at any time with `cargo clean` or `rm -rf target/`.
