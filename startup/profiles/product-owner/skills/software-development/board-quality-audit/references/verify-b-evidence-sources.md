## 20. Evidence-source hierarchy for `[verify-b]` integration tasks

**Symptom:** you query the `[verify-b]` (integration verify) card and BOTH
`result` AND `task_comments` are empty. The older pitfall in the skill says
"findings live in task_comments, not result" — that guidance is correct for
`[task]` / `[verify]` per-phase cards but **fails for `[verify-b]`**, whose
verdict lands in neither. Do not conclude "verify-b left no evidence."

### a. Where the verify-b verdict actually lives (query in this order)

| Source | Table / column | Shape | What it gives you |
|--------|----------------|-------|-------------------|
| **1. task_runs.summary** | `task_runs.summary` (text) | Human-readable string | The headline verdict: `PASS — 207/207 tests in fresh venv: 142 dev + 40 behavior + 25 adversarial; mutation check 3/3 caught` |
| **2. task_events completed payload** | `task_events WHERE kind='completed'` | JSON: `{summary, result_len, artifacts:[...]}` | Structured verdict + absolute paths to artifacts (behavior-test files copied into `attachments/`) |
| **3. task_events attached payload** | `task_events WHERE kind='attached'` | JSON: `{filename, size, by}` | Confirms a behavior-test file was attached via `kanban_complete(artifacts=...)` — it now lives in `attachments/<task-id>/` |
| **4. task_runs.outcome** | `task_runs.outcome` | `completed` / `blocked` / `crashed` / `failed` / `timed_out` | Run-level disposition (the `status` column is just `done` for all finished cards; `outcome` carries the nuance) |

```sql
-- The two queries that resolve "empty result + empty comments" on verify-b:
SELECT summary, outcome FROM task_runs WHERE task_id = '<verify-b-id>';
SELECT payload FROM task_events
WHERE task_id = '<verify-b-id>' AND kind IN ('completed','attached')
ORDER BY id;
```

### b. Why result + comments are both empty on verify-b

The verify-b card is dispatched by the loop_engine / orchestrator and
completes via `kanban_complete(summary=..., metadata=...)`. The `summary`
arg populates **`task_runs.summary`** (not the tasks table `result` column),
and the completion event is written to **`task_events` (kind='completed')**
(not `task_comments`). The `result` column on the tasks table and the
`task_comments` thread are left untouched. This is a different write path
than per-phase `[verify]` cards, which DO write findings to comments. So the
evidence-source rule is: **`[task]`/`[verify]` → comments; `[verify-b]` →
task_runs + task_events.**

### c. Worked example — livetest-unbias-4 (Tic-Tac-Toe) + livetest-unbias-5 (String Validator)

Both boards' `[verify-b]` cards (`t_5cae79ff`, `t_2dcd5d1e`) had empty
`result` and zero `task_comments`. The verdicts were found exclusively in:

```
task_runs.summary:
  t_5cae79ff → "PASS — 154 tests green (93 dev + 61 behavior/attack), 3/3 mutations caught"
  t_2dcd5d1e → "PASS — 207/207 tests in fresh venv: 142 dev + 40 behavior + 25 adversarial"

task_events (kind='completed') payload:
  {"result_len": 0, "summary": "PASS — ...", "artifacts": [".../attachments/t_5cae79ff/test_behavior.py"]}
```

The `artifacts` array pointed to `attachments/<task-id>/test_behavior.py` —
the behavior-test file survived workspace cleanup there (the fourth
code-recovery path documented in §19c). So even on a board where the verify-b
**workspace** dir (`workspaces/t_<verify-b-id>/`) was never created or was
reaped, the behavior test is recoverable via the `attached` event's
`attachments/` pointer.

### d. Implication for the "never trust, always re-probe" imperative

The verify-b self-reported counts in `task_runs.summary` are still claims, not
proof. Apply the same independent-re-run rule: reproduce the test count by
running the dev suite + behavior/attack suites yourself, and reconcile the
numbers. On both worked-example boards, the summary claimed 154 and 207
respectively; independent re-runs produced exactly 154 and 207 — strong
corroborating evidence. The summary is the START of the audit, not the end.

### e. Phase-level crash/retry history (decomposition resilience signal)

Related: on loop_engine boards, the same `task_runs` table carries the
phase-level crash/retry history that feeds the decomposition "resilience vs
instability" judgement. A board where one phase's dev cards show 3 consecutive
`crashed` outcomes before `completed` on the 4th attempt (observed on
livetest-unbias-5's pytest-suite phase) demonstrates loop recovery — the
convergence metadata on the close card confirms the board still reached a
green terminal state. Query:

```sql
SELECT t.id, substr(t.title,1,45), r.outcome, substr(r.summary,1,80)
FROM task_runs r JOIN tasks t ON r.task_id = t.id
WHERE t.title LIKE '[task]%' AND r.outcome IN ('crashed','failed','timed_out','reclaimed')
ORDER BY r.id;
```

A cluster of same-phase crashes followed by a `completed` = resilience (score
decomposition down mildly for the instability, but not as a failed board).
A cluster of same-phase crashes with NO eventual `completed` = a phase that
never converged = a real decomposition/fix-effectiveness failure.
