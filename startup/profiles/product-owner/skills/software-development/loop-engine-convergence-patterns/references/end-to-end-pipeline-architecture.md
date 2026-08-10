# End-to-End Pipeline: spec → tickets → build → verify → close

## Architecture (committed state)

Two workflow templates form the production pipeline:

### dev-dispatch.json — spec decomposition

```
[spec] card completes (type=feature)
  → trigger fires
  → route-decompose node (product-owner)
    → PO calls loop_engine (decompose→review convergence loop)
    → metric_type=ground_truth, verifier returns minimal dict
    → on advance: PO creates [ticket-NN] cards assigned to tech-lead
    → ticket card bodies include trigger prefix: "Complete IMMEDIATELY. Do NOT implement."
```

### tech-lead-execute.json — ticket execution

```
[ticket-NN] card completes
  → trigger fires
  → plan node (tech-lead)
    → decomposes ticket into dev+verify phases via loop_engine
    → each phase: developer builds (COMPLETE not block) → verifier behavior-tests
    → fix loop on FAIL
    → close node MERGES branch to master + runs full tests (merge gap fix)
    → merge-verify node (CONDITIONAL: only when task_count > 1)
      → verifier mechanically checks: git log master..<branch>, git fsck, pytest
      → separation of duties: merger doesn't verify its own merge
```

## Full E2E Test (Todo CLI — 5 stories, JSON storage)

**Result:** ALL 60 cards completed. 4 tickets × (plan→dev→verify→fix→re-verify→verify-b→close). Zero blocked, zero failed.

**Timeline:** ~90 minutes end-to-end. 4 tickets ran in parallel after ticket-01 (foundation) completed.

**What worked:**
- Decomposition converged iteration 1 (loop_engine advance, no replan)
- 4 tickets created with correct dependency DAG
- Developer completed cards (not blocked) on 3/4 tickets
- Verifier found real bugs (TypeError from schema-corrupted store) and fix cards fired
- All tickets closed with verdicts

**What failed (merge gap — systemic):**
- 2 of 4 ticket branches never merged into master
- ticket-02's entire `list` command was still a stub in shipped master
- Fix cards wrote fixes on branches that were never reconciled
- Interactive rebase destroyed commits mid-flight (dangling, unrecoverable)
- close node wrote `verdict=merged` without actually merging

**Code quality:** Independent review rated the code "solid" — clean separation, atomic writes, spec-faithful. One real bug (wrong-shape JSON corruption → bare traceback) that the pipeline found AND fixed but the fix was lost in the merge gap. 48 tests pass on the project. Code at `/home/lpaydat/projects/todo-app/`.

## Commits (session chronology)

| Commit | Fix |
|--------|-----|
| `09bcdc9` | feat: spec-to-tickets workflow (decompose + parse paths) |
| `e87b9f6` | enable loop_engine plugin on product-owner |
| `0e9bc4b` | pin Version E: tree builder decompose→review convergence loop |
| `12b3799` | enforce loop_engine re-call on every promotion |
| `2f3b88f` | remove metric_type=proxy + battery schema mismatch |
| `6151a11` | set metric_type=ground_truth on decomposition verifier |
| `f5f046c` | cleanup A/B test variants and test boards |
| `e7a3f59` | rename route-tech-lead → route-decompose |
| `265abb2` | fix tech-lead-execute: dev blocks for review instead of completing |
| `9ae6668` | verifier returns minimal dict (no behaviors/defect_traces) |
| `1eb0f8d` | prepend trigger instruction to ticket card bodies |

Merge gap fixes (branch `fix-v1-merge-gap`):

| Commit | Fix |
|--------|-----|
| `843a323` | close node merges branch + run tests; plan node forbids rebase/reset |
| `9a7f07b` | merge-verify node (conditional, fires when task_count > 1) |

## Active branches

- `main` — production pipeline (all commits merged and pushed to origin/config)
- `tech-lead-graph-workflow` — v2 design with mermaid diagrams (static graph, foreach nodes, no loop_engine)
- `fix-v1-merge-gap` — v1 merge fix (close node merges, plan node forbids rebase)

## Conditional merge-verify — skip when single-task

The merge-verify node is CONDITIONAL. It only fires when parallel dev happened (`task_count > 1`), because that's when merge complexity exists. Single-task tickets (one branch, close handles the merge) skip merge-verify entirely.

**Technique:** use a conditional edge on a node OUTPUT value:
```json
{
  "from": "close",
  "to": "merge-verify",
  "condition": "${nodes.plan.output.task_count} > 1"
}
```
The workflow engine's `evaluate_condition` (model.py:657) supports `${var} > <value>` with numeric coercion on both sides. This makes merge-verify an optional node driven by actual decomposition state, not a body-text instruction.

**Generalization:** conditional edges on node outputs let you skip expensive verification steps when they're not needed. `task_count <= 1 → skip integration verify`, `task_count <= 3 → skip load testing`, etc.

## Next: Static Graph Nodes for tech-lead-execute (v2)

**Problem:** tech-lead-execute's plan node uses loop_engine to dynamically decompose each ticket into dev+verify phases. This requires tech-lead to have delegation tools — which enables freelancing (Pattern 5). Body-text enforcement ("don't freelance") is the weakest layer. Forensically confirmed: tech-lead creates a PARALLEL kanban_chains pipeline 4 minutes before the workflow's loop_engine even fires.

**Solution:** Break tech-lead-execute into static graph nodes using the workflow engine's `foreach` card_mode. The workflow template IS the execution plan:

```
[ticket-NN] completes → tech-lead-execute fires
  ↓
  plan node: tech-lead decomposes ticket into tasks (NO loop_engine, pure JSON output)
  ↓
  dev node (foreach): one developer card per task (parallel, engine dispatches)
  ↓
  verify node (foreach): one verifier card per task (parallel, engine dispatches)
  ↓ conditional edge:
  ├── ALL PASS → integration-verify node
  └── ANY FAIL → fix node (foreach) → re-verify node (foreach) → loop (max_iterations=5)
  ↓
  integration-verify node: whole-ticket adversarial behavior tests
  ├── PASS → close
  └── FAIL → integration-fix → close
  ↓
  close node: tech-lead MERGES branch + writes verdict
```

**Design doc:** `startup/scripts/workflow_engine/templates/DESIGN-tech-lead-graph-v2.md` on branch `tech-lead-graph-workflow`.

**What stays the same (prompts preserved):**
- plan body: same decomposition instructions, same atomic task guidelines
- dev body: "Implement + test + COMPLETE this card"
- verify body: full adversarial methodology (5 principles + mutation testing)
- fix body: "Fix YOUR code so ALL tests pass"
- re-verify body: same adversarial self-review applied to the fix
- integration-verify body: same adversarial methodology, whole-ticket scope
- close body: merge + verdict logic

**Key difference:** The workflow engine handles ALL card creation and dispatch via foreach nodes. No loop_engine, no kanban_chains, no tech-lead freelancing possible.

**Open questions (must answer before building):**
1. Does the engine support foreach + conditional edges together? (foreach creates multiple cards; engine waits for all; then evaluates edge conditions)
2. How does foreach re-dispatch on loop iterations? (idempotency key includes iteration suffix — should create fresh cards each iteration)
3. How to filter fix to only failing tasks? (the foreach list for fix should be filtered to failing tasks only — may need a filter mechanism or the dev body handles it)
4. Parallel dev race condition — multiple dev cards committing to same branch simultaneously
5. Commit-preservation enforcement — body text "don't rebase" is weakest; need git hooks
6. Merge authority — which profile has git merge power?
7. Reconciliation gate placement — in tech-lead-execute (per ticket) or dev-dispatch (per project)?

**Card count impact:** Current loop_engine approach creates ~12 cards per ticket. Static nodes would create ~5-6 per ticket (dev+verify+fix+re-verify+close). 50%+ reduction.
