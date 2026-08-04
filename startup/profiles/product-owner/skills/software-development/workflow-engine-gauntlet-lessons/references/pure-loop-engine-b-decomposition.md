# Pure loop_engine B Decomposition Results (A/B/C Gauntlet)

## The experiment

3 decomposition approaches tested on 3 identical specs (9 boards, parallel via trigger-prefix isolation):

- **Version A** (one-shot): to-tickets → kanban_chains dispatch. No feedback loop.
- **Version B** (loop_engine): to-tickets → loop_engine with phases (execution=developer, verifier=verifier). loop_engine handles ALL card creation, iteration, convergence.
- **Version C** (critic): to-tickets → delegate_task critic subagent → revise → kanban_chains.

## Final leaderboard (from subagent analysis)

| Approach | B1 (MdTable) | B2 (JsonDiff) | B3 (UnitConv) | Avg |
|----------|:---:|:---:|:---:|:---:|
| A (one-shot) | 7.6 | 8.8 | 6.2 | 7.53 |
| old-B (kanban_chains) | 9.0 | 9.4 | 6.0 | 8.13 |
| C (critic) | 8.5 | 8.5 | 6.0 | 7.67 |
| **loop-B (pure loop_engine)** | **9.3** | **9.0** | **9.6** | **9.30** |

## Why old-B3 failed (kanban_chains dispatch bug)

loop_engine converged on 3 tasks (core+list_units, format, convert_batch). But kanban_chains only dispatched the FIRST chain. format() and convert_batch() had no dev card. Coverage 4/10 — 2 of 10 spec requirements literally have no task.

Root cause: loop_engine's converged output wasn't fully translated to kanban_chains chains. The handoff between two orchestration systems lost tasks.

## Why pure loop_engine B fixed it

loop_engine handles BOTH convergence AND dispatch. No kanban_chains handoff. The plan node calls loop_engine with:
```json
{
  "goal": "<spec title>",
  "runner": "tech-lead",
  "phases": [
    {
      "execution": {"title": "[task] ...", "body": "...", "assignee": "developer"},
      "verifier": {"title": "[verify] ...", "body": "...", "assignee": "verifier"},
      "max_iterations": 5
    }
  ]
}
```

loop_engine creates ALL phase cards internally, iterates each phase (advance/replan/escalate), and dependency-parks the caller until all phases converge. No external dispatch step that can drop tasks.

## Decomposition quality (pure loop_engine B)

| Spec | Phases | Structure |
|------|--------|-----------|
| Markdown Table | 4 | core CLI → alignment → escaping → error handling |
| JSON Diff | 3 | diff engine+CLI → output+types → array-by-id+ignore+errors |
| Unit Converter | 4 | registry+linear+list_units → temperature → convert_batch → format |

Key improvements:
- **B3 dispatch bug FIXED**: format() is Phase 4, convert_batch() is Phase 3. Both present with full ACs.
- **Split-by-concern works**: temperature correctly separated from linear (non-linear vs linear math).
- **Wide-spec handling**: 4 API functions got 4 separate phases (was 1 crammed card in version A).

## B2 slight regression (9.4 → 9.0)

Phase 3 crams 3 concerns (id-alignment + --ignore + error handling) into one phase. Not a coverage gap — all 9 requirements covered. Just denser atomicity than ideal. Could be 4 phases with error handling split out.

## Per-dimension scores

| Board | Coverage | Atomicity | AC Quality | Deps | Right-sizing |
|-------|:--------:|:---------:|:----------:|:----:|:------------:|
| B1 | 9 | 9 | 10 | 9 | 10 |
| B2 | 10 | 8 | 10 | 9 | 8 |
| B3 | 10 | 10 | 9 | 9 | 10 |

## Lesson reinforced: do NOT mix orchestration systems

Previous B mixed loop_engine (convergence) with kanban_chains (dispatch) — the handoff lost tasks. Pure loop_engine B uses ONE system end-to-end. No handoff, no lost tasks.

User quote: "why use kanban_chains when I told you to use loop_engine?" — when the user says one system, use that one system throughout.

## Pinned template

`tech-lead-execute.json` now uses pure loop_engine for the plan phase. Trigger: `[spec]`. Old A and C disabled (`.disabled` suffix).
