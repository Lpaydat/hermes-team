# Stale Commit SHA Propagation Through Refactor Tickets

Forensic trace from the hashtree e2e test (milestone-gate workflow,
2026-08-09). Board DB: `startup/kanban/boards/hashtree/kanban.db`.

## Summary

The refactor-decompose node pins a stale commit SHA into refactor tickets.
The SHA is captured by the refactor-review verifier, persisted into
`REFACTOR.md`, then propagated and amplified by two more agents until it
becomes a binding baseline instruction for the developer. By the time the
developer picks up the task, main has advanced — the refactor lands on an
old git baseline.

This is an **agent-behavior** issue, not a template issue. No template
instructs SHA pinning.

## Propagation chain (4 hops, 3 agents)

| Hop | Node / Agent | Action | Evidence |
|-----|-------------|--------|----------|
| 1 (origin) | refactor-review / verifier | Runs deletion test against codebase at time T. Writes HEAD SHA into `REFACTOR.md` as free-text evidence. | `REFACTOR.md` line 3: "Validated against the real codebase at `f4ee98d` (main)." |
| 2 | refactor-decompose / PO | Reads `REFACTOR.md`, copies SHA into ticket body's `**Evidence:**` field. | `t_d9178964` body: "Deletion test against codebase at commit `f4ee98d` (main)." |
| 3 (amplification) | tech-lead-execute → plan / tech-lead | Reads spec ticket, sees SHA in Evidence, promotes it to binding baseline instruction in task card. | `t_816bab5d` body: "Work from `main` branch at commit f4ee98d... Create a NEW branch `refactor/c1-dep-cleanup` off main" |
| 4 | developer | Follows pinned SHA literally — branches off stale commit. | Developer branches from `f4ee98d` instead of current main. |

## Verification: templates contain no SHA-pinning instruction

Grepped all `body_template` fields in `milestone-gate.json` for keywords:
`commit`, `HEAD`, `baseline`, `sha`, `branch`, `main`, `scanned_at`.

| Node | Keyword matches | Verdict |
|------|----------------|---------|
| refactor-scan | "sha" → false positive ("sha**llow**") | No SHA instruction |
| refactor-review | "main" → false positive ("**main**tains") | No SHA instruction |
| refactor-decompose | (none) | No SHA instruction |

The refactor-scan output schema has no `scanned_at_commit` field. Its
schema is: `candidates`, `codebase_clean`, `total_strong`,
`total_worth_exploring`, `scan_summary`. No commit SHA is captured
structurally.

The `tech-lead-execute.json` plan node body_template also does not instruct
SHA pinning — it mentions `git checkout -- <file>` (safety) and
`git add/commit/merge` but never tells the agent to resolve or pin a
specific commit.

**Conclusion: the SHA enters as agent-authored prose, not template text.**

## Git evidence: staleness confirmed

```
f4ee98d  Merge feat/us1-ac-coverage: [ticket-01]  (milestone-01 tip, 09:30)
7bc5c1e  fix: error on non-UTF8 paths
d502cad  Merge feat/ticket-02-json-output
a9ed514  Merge feat/ticket-04-error-handling
a67db32  feat: core tree-hash CLI + --exclude + --json
b80d47d  Merge feat/exclude-filter: [ticket-03]  (milestone-02 tip, 11:51)
4b4fbec  refactor: delete redundant tests/cli.rs  (M-02 refactor merged)
ee81b8b  refactor: remove unused deps + hex crate (M-01 refactor merged, 13:00)
```

The M-01 refactor (`ee81b8b`) merged at 13:00, but was told to branch off
`f4ee98d` — a baseline that was 9 commits and ~3.5 hours stale by merge
time. Between scan time and dev start, tickets 02/03/04 merged and the M-02
refactor landed.

## Reproducibility

- **Systematic precondition:** scan/review always runs at
  milestone-completion time T, capturing commit C. By the time the
  developer starts work (after review → decompose → tech-lead plan → dev
  dispatch), main has always advanced. So **whenever a SHA is pinned, it is
  guaranteed stale.**
- **Non-deterministic pinning:** the milestone-02 refactor task
  (`t_aafbb69d`) did NOT pin a SHA — it said "work on the current branch."
  The M-02 trigger card (`t_8ab4bca4`) still carried `b80d47d` in its
  Evidence field (copied from REFACTOR.md), but the M-02 tech-lead chose not
  to promote it to a baseline constraint.
- **Verdict:** 1 of 2 milestones exhibited the bug. The root cause (SHA in
  REFACTOR.md) is always present; whether it becomes a binding constraint
  depends on the tech-lead agent's judgment.

## Comparison to gauntlet lesson #16

Lesson #16 ("Close-card hardcoded verdict literal") covers template-authored
literals at design time — a value written into the body_template by a human
that goes stale. This finding is the **agent-authored prose variant**: the
value is injected by an LLM at runtime, not present in the template at all.
Same root (volatile value frozen as a literal), different injection vector.

## Key cards in the hashtree board

| Card ID | Title | Role in chain |
|---------|-------|---------------|
| `t_0005eeea` | [refactor-scan] milestone-01 | Scanned codebase at milestone-01 tip |
| `t_ccd5ebcd` | [refactor-review] milestone-01 | Validated candidates, wrote REFACTOR.md with SHA |
| `t_589ea9ed` | [refactor-decompose] milestone-01 | Created refactor ticket with SHA in Evidence |
| `t_d9178964` | [ticket-refactor-01] C1 | Trigger card — SHA in Evidence field |
| `t_816bab5d` | [task] Remove 4 unused deps | **THE BUG** — SHA promoted to binding Baseline |
| `t_125a64eb` | [refactor-scan] milestone-02 | M-02 scan (did not exhibit the bug) |
| `t_aafbb69d` | [task] Refactor: delete tests/cli.rs | M-02 task — said "current branch", no SHA pin |

## REFACTOR.md content (the SHA origin point)

```
# Refactor — Milestone 01: Core tree-hash CLI spine

Validated against the real codebase at `f4ee98d` (main).
```

That single line of prose is the root cause. It was written by the
refactor-review verifier as documentation of when it validated the
candidates. It then propagated through two more agents and became a
binding instruction.

## Detection recipe

To check whether a refactor ticket has a stale SHA:

```sql
-- Find all refactor task cards and extract commit SHAs from their bodies
SELECT id, title, body FROM tasks
WHERE title LIKE '[task]%refactor%' OR title LIKE '[task]%Refactor%'
ORDER BY created_at;
-- Then grep each body for 7-char hex SHAs and check against git rev-parse main
```

```bash
# Verify staleness
cd <repo>
git rev-parse main    # current HEAD
# Compare against any SHA found in ticket bodies — if different, the SHA is stale
```
