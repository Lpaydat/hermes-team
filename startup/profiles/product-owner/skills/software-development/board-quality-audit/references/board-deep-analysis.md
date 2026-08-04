## 15. Planning-quality / decomposition audit (cross-board)

When the question is about **decomposition quality** — not whether the code
works, but whether the plan cards were any good — use this section. Typical
triggers: "score the plan cards", "compare decomposition across these 3 specs",
"did the template under-decompose?", "score Version B vs Version A", "did
loop_engine actually iterate?".

This is a **planning audit**, distinct from the execution audit in §1–14. The
six scoring dimensions below supersede the five execution dimensions when the
user is asking about the plan, not the product. You can run both (execution +
planning) on the same board — they grade different things.

### a. The six planning dimensions (score each 0–10 with cited evidence)

| # | Dimension | What to check | Floor / red flag |
|---|-----------|---------------|------------------|
| 1 | **Spec coverage** | Enumerate the spec's numbered requirements. Map each to a dev card. List gaps. | A requirement with **no task** tanks this score regardless of the other five. |
| 2 | **Task atomicity** | Is each card junior-dev-one-sitting sized (one coherent responsibility, 5–8 ACs)? Or are separable concerns crammed into one card? | A card bundling N subsystems (engine + IO + tests) is under-decomposed. |
| 3 | **AC quality** | Are ACs testable assertions with exact expected values / exit codes / output strings? Or vague goals? | "Handles escaping" = bad. "Pipe `\|` escapes to `\|`" = good. |
| 4 | **Dependency structure** | Read `task_links`. Are serial/parallel deps correct? Does the graph encode the claimed ordering? | A convergence loop can design a correct parallel DAG that the dispatch tool flattens to serial. |
| 5 | **Right-sizing** | Is dev-card count appropriate for spec complexity? Rule of thumb: 1 card per 2–4 spec requirements. | One card for a 9–10 requirement spec with distinct sub-domains is almost always under-decomposed. |
| 6 | **Convergence-loop impact** *(only for loop_engine / iterative-decomposition templates)* | Did the loop actually iterate? Did it change the output vs a one-shot? Check `decomposition_iterations`. | `decomposition_iterations: 0` = one-shot, no loop benefit. >0 with no plan change = rubber-stamp. |

### b. DB queries for a decomposition audit

```sql
-- 1. Card inventory by type prefix (spot root-blackboard, plan, dev, verify, probe cards):
SELECT substr(title,1,30) AS t, status, assignee, count(*)
FROM tasks GROUP BY t ORDER BY t;

-- 2. The dependency DAG (confirm claimed serial/parallel ordering):
SELECT parent_id || ' -> ' || child_id FROM task_links ORDER BY parent_id;

-- 3. Plan-card convergence log (the loop_engine output lives HERE, not in result):
SELECT body FROM task_comments c
JOIN tasks t ON t.id = c.task_id
WHERE t.title LIKE '%[tl%Plan%' OR t.title LIKE '%Plan:%'
ORDER BY c.created_at;

-- 4. Spec coverage cross-check: which spec requirements have NO matching dev card?
--    Pull the spec card body, enumerate its numbered requirements, then grep dev bodies:
SELECT id, title FROM tasks
WHERE body LIKE '%<requirement-keyword>%' AND title LIKE '%[task]%';
```

### c. Convergence-loop impact analysis (dimension 6)

For templates that use a convergence loop (loop_engine, iterative refinement),
dimension 6 asks: **did the loop earn its cost?** Three checks:

1. **Did it iterate?** Find `decomposition_iterations: N` (or equivalent) in the
   plan card's comments. `N=0` means no loop ran — score the dimension as N/A
   (one-shot template, no convergence to evaluate).
2. **Did it change anything?** The convergence log records the initial coarse
   cut and each iteration's decisions (merge X, split Y, dissolve Z). Compare
   the initial task list to the final converged tree. A loop that ran 2
   iterations but produced the same tree as the initial cut is a rubber-stamp —
   low value.
3. **Did the changes improve quality?** A genuine convergence loop makes
   *substantive* decisions: merging a separate-tests ticket into vertical
   slices (to-tickets principle), collapsing an over-fragmented single-file
   tool into one card, folding a trivial function into its parent. Quote the
   specific decisions in the report.

**A/B comparison method:** when comparing a convergence template (Version B)
against a one-shot template (Version A) on identical specs, map the spec
requirements to dev cards on **both** sides. The convergence template wins if
it produces tighter per-task boundaries, explicit scope fences ("Do NOT
implement X yet"), or better atomicity. The one-shot wins if the convergence
template's dispatch was incomplete (see pitfall below).

### d. Pitfalls specific to decomposition / convergence audits

- **Partial dispatch trap.** A convergence loop can converge on an N-task plan
  but only dispatch M < N of them. The convergence log will say "3 leaf tasks:
  T1, T2, T3" but only T1 has a dev card. **Cross-check the converged task
  count against actual dispatched dev cards.** A plan card stuck in `running`
  (not `done`) is a signal that Phase-3 dispatch (kanban_chains) may be
  incomplete. Query: compare the task list named in the convergence comment
  against `SELECT id FROM tasks WHERE title LIKE '[task]%'`. The gap = dropped
  requirements.
- **Convergence metadata lives in comments, not the formal metadata field.**
  `decomposition_iterations`, `sizing_summary`, and `task_ids` are logged in
  the plan card's `task_comments` — NOT in the plan card's `result` column or
  kanban_complete `metadata` (because the plan card may never reach `done`).
  Always mine comments; do not trust an empty `result` to mean "no convergence
  happened."
- **Dispatch flattens parallel DAGs to serial.** A convergence loop can design
  a correct parallel DAG (e.g. L1 → L2 → {L3, L4, L5 in parallel}) but the
  dispatch tool (kanban_chains single-chain) serializes them (L3 → L4 → L5).
  This is a **dependency-structure** scoring penalty (efficiency loss), not a
  correctness error. Check the `task_links` graph against the DAG the
  convergence log claims.
- **Version comparison baseline.** When comparing template versions on
  identical specs, both sides must be scored on the same six dimensions. The
  one-shot side (Version A) will always score N/A on dimension 6 (no loop) —
  compare the other five, then note whether the convergence loop's gains on
  dimensions 1–5 outweigh its dispatch-reliability risk.

### e. Worked example — Version B (loop_engine) vs Version A, 3 specs

Three identical specs run through two templates: A (one-shot to-tickets) and
B (loop_engine convergence). Scored on the six planning dimensions:

| Board | Spec | Coverage | Atomicity | AC Quality | Deps | Right-size | Loop Impact | Avg |
|-------|------|----------|-----------|------------|------|------------|-------------|-----|
| B1 | Markdown Table | 9 | 9 | 9 | 9 | 9 | 8 | 8.8 |
| B2 | JSON Diff | 10 | 10 | 10 | 8 | 9 | 9 | 9.3 |
| B3 | Unit Converter | **4** | 8 | 8 | 5 | 5 | 5 | 5.8 |

**B1 (9.3 avg):** loop_engine ran 2 iterations. Initial cut = 5 tasks (by
layer: CLI / CSV / escaping / alignment / tests). Iter-1 merged because all
tasks edit the same single file → collapsed to 1 leaf. The loop *prevented*
over-fragmentation — a genuine improvement over a naive one-shot that would
keep the 5-task split.

**B2 (9.3 avg):** loop_engine ran 2 iterations. Initial cut = 8 tasks.
Iter-1 merged type-change into the diff engine and dissolved a standalone
tests ticket (to-tickets vertical-slice rule). Converged to 5 leaf tasks with
explicit scope fences ("Do NOT implement by-id / --format / --ignore yet").
vs Version A: A2 produced 3 coarser cards; B2's 5-card split is more atomic
with tighter per-task boundaries. **B2 clearly outperforms A2.**

**B3 (5.8 avg):** loop_engine converged on a 3-task plan (core+categories+
list_units / format() / convert_batch()) in 2 iterations — but **only 1 of 3
tasks was dispatched.** `format()` and `convert_batch()` (spec requirements
#5 and #6) have **zero dev cards.** The plan card is stuck in `running`.
The convergence was correct; the dispatch broke. **Version A (1 card covering
all requirements) has strictly better spec coverage than Version B3** — the
loop_engine's theoretical improvement regressed in outcome due to incomplete
dispatch.

**Net finding:** loop_engine genuinely iterated on all 3 boards (2 iterations
each) and made substantive decomposition decisions. On the 2 boards where
dispatch completed, Version B outperformed Version A in atomicity and AC
specificity. The failure mode (B3) is a **dispatch-reliability bug**, not a
convergence-loop failure. The loop works; the execution of its output is the
weak link.
