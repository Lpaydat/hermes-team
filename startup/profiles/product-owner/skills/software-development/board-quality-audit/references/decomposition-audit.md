# Decomposition (Planning-Quality) Audit Reference

When the audit target is the **plan itself** rather than shipped code — "does
this template under-decompose?", "score the decomposition across these 3
boards", "compare Version A vs Version B" — use this rubric. It scores the
plan cards and dev-card bodies against the spec, not execution evidence. It
does not re-run tests, git-diff fixes, or re-probe code. It is dimension-3-only
plus a cross-board comparison layer.

This is the planning-quality mirror of the execution-quality audit in
[`board-deep-analysis.md`](board-deep-analysis.md). Load that one when shipped
code exists to probe; load this one when the question is about the plan's
quality.

## 1. The five decomposition sub-dimensions (0-10 each)

| # | Sub-dimension | What good looks like | What bad looks like |
|---|---------------|----------------------|---------------------|
| 1 | **Spec coverage** | Every numbered spec requirement maps to ≥1 dev card; no gaps | A requirement silently dropped, or folded into a "constraint" with no AC |
| 2 | **Task atomicity** | 5-8 ACs per card; one coherent responsibility; junior-dev-sized | Multiple separable concerns crammed in (alignment+escaping+errors+tests) |
| 3 | **AC quality** | Testable assertions with exact expected values/exit codes/output strings | Vague goals ("handles escaping") with no pass/fail criterion |
| 4 | **Dependency structure** | `task_links` graph encodes correct serial/parallel ordering | `kanban_chains` topology bug, stale parallel edge, missing verifier→tl link |
| 5 | **Right-sizing** | 1 dev card per 2-4 spec requirements; more for many-sub-domain specs | 1 card for a 9-10 requirement spec with distinct subsystems |

### Spec-coverage floor

Enumerate the spec card's numbered requirements explicitly. For each, find the
dev card(s) that address it. Any requirement with no owning card is a gap and
caps the coverage score. The verifier card re-enumerating the spec's
requirements is good corroboration that coverage was complete (or reveals what
was missed).

### Atomicity rule: decompose by concern, not by artifact

A single output file/module does NOT justify a single card if the file contains
separable layers. `jsondiff.py` with an engine layer, an output-formatting
layer, and an exit-code/error layer is 3 cards, not 1. The tell that a card
bundles concerns: its AC checklist spans features that could be developed and
tested independently (an alignment engine, a pipe-escaping rule, five distinct
error paths, and the test suite).

### The under-decomposition tell (cross-check with verifier cards)

When a single dev card is too coarse, the verifier card often has to supply
edge cases the dev card omitted — reverse conversions, boundary counts,
fallback rules, type-change sub-cases. If the verifier's adversarial checklist
adds cases the spec implied but the dev AC didn't enumerate, the dev card was
under-specified. This is evidence, not just opinion.

## 2. DB queries for a decomposition audit

```sql
-- The spec card (source of truth for requirements):
SELECT body FROM tasks WHERE title LIKE '[spec%';

-- Dev cards ONLY (exclude the kanban_chains matrix-root blackboard card):
SELECT id, title, body FROM tasks
WHERE assignee='developer' AND title LIKE '[task]%' ORDER BY created_at;

-- The plan card's dispatch rationale + any confessed dispatch failures:
SELECT body FROM task_comments c
JOIN tasks t ON t.id=c.task_id
WHERE t.title LIKE '[tl] Plan%' ORDER BY c.id;

-- The full dependency graph (check for stale/wrong edges):
SELECT parent_id || ' -> ' || child_id FROM task_links ORDER BY parent_id;

-- Verifier cards (for the under-decomposition cross-check):
SELECT id, title, body FROM tasks
WHERE title LIKE '[verify%' ORDER BY created_at;
```

**Counting dev cards correctly:** `assignee='developer'` includes the
`kanban_chains` root blackboard card (body starts "Matrix root / shared
blackboard"). Filter on `title LIKE '[task]%'` for the true dev-task count.

**sqlite3 `-cmd` gotcha:** if the shell environment exports sqlite3 `-cmd`
flags (e.g. from a Hermes config), multi-statement queries and `||` string
concatenation can parse-error. Workaround: use a single `SELECT` per call, or
run `unset SQLITE3` / invoke `sqlite3` with no inherited `-cmd`.

## 3. Cross-board comparison methodology

When auditing a template across N boards (e.g. A/B testing decomposition
strategies):

1. Score all five sub-dimensions for each board, in a table.
2. Look for a **consistent pattern**: does the template under-decompose? On
   which spec types? A template that scores well on one spec but poorly on two
   others is bimodal — strong when a spec has obvious build-layers, weak when
   separable concerns are hidden inside one module.
3. Identify the **failure mode**: "one card per output artifact regardless of
   separable concerns" is the classic under-decomposition pattern. "Decompose
   by concern" is the fix.
4. Note what the template does **consistently well** (e.g. AC authorship) even
   when it under-decomposes — this is the leveraged strength to preserve.
5. Distinguish **planning defects** from **mechanical/tooling defects**: a
   `kanban_chains` state race requiring manual link recovery is a tooling
   failure, not a planning failure. Score them separately.
6. **Normalize dev-card counts across variants.** Exclude matrix-root
   blackboard cards and archived probe artifacts (see §6). Count only real
   dev cards (`title LIKE '[task]%'` or `[dev]%`, non-archived) for fair
   right-sizing comparison.

## 4. The critic-impact dimension (for self-grill / critic-decomposition templates)

When the template includes a "Phase 2: self-grill" or critic subagent step,
score a sixth decomposition dimension: **did the critic actually find real
issues, and did the revision improve the decomposition?** This measures the
*process improvement delta* and is distinct from the five generic
sub-dimensions. Score it only for critic variants — baseline templates have no
critic step.

### Evidence sources

1. **Plan-card comment** — the tech-lead records `critic_findings: N,
   critic_revisions: N` and lists each finding. Mine it with the query in §2.
2. **Card bodies** — look for `(Critic gap fix: ...)` annotations inline in AC
   lists. These mark ACs the critic caused to be added or tightened.
3. **`created_by` column** — cards with `created_by='tech-lead'` (the first
   dispatch) vs `created_by='user'` (a second/recovery dispatch) reveal whether
   the revision was re-dispatched from scratch.

### Scoring rubric (0-10)

| Score | Meaning |
|-------|---------|
| 9-10 | Critic found substantive structural issues (missing reqs, DAG bugs, untestable ACs); revision demonstrably fixed them; dispatch honored the revision. |
| 7-8  | Critic found real findings; revision improved testability or coverage; minor gap between revision and dispatch. |
| 5-6  | Critic ran but was lightweight (cosmetic AC tightening), OR the dispatch partially ignored the revision, OR the critic caused a control-flow bug. |
| 3-4  | Critic findings were shallow/wrong, or the revision made things worse, or the dispatch completely ignored the critic. |
| 0-2  | No critic ran, or critic findings were fabricated/irrelevant. |

### Critic failure modes to check for

- **Critic subagent premature completion.** A critic spawned with full agent
  tooling can call `kanban_complete` on the plan card, closing it before
  dispatch. Look for `premature_completion_bug: true` in the plan comment
  metadata, and a plan card stuck in `done` while child cards are still
  `running`/`todo`.
- **Critic revision not honored by dispatch.** The critic says "split task 3
  into A and B (5 tasks)" but the shipped chain has 4 tasks with the split
  collapsed back. Compare the critic's recommendation in the comment to the
  actual `task_links` topology. Divergence = critic-impact deduction.
- **delegate_task unavailable.** The template says "spawn a critic subagent via
  delegate_task" but the profile lacks the tool. The tech-lead falls back to
  structured self-critique. This is honest but weaker (no clean-context
  adversarial review) — note it, don't penalize heavily.
- **Probe leakage from the critic run.** See §6.

## 5. Dispatch-artifact detection (PROBE-ONLY-DELETE, duplicate chains)

`kanban_chains` is fiddly. A tech-lead under time pressure may **probe** the API
mid-run (test-invoking it with throwaway titles) before committing to the real
dispatch. These probes leave orphan cards in the DB. Detect them:

```sql
-- Probe / throwaway artifacts:
SELECT id, title, status, created_by FROM tasks
WHERE title LIKE '%PROBE%' OR title = 'probe' OR title LIKE '%probe%';

-- Duplicate chains: same logical task created twice (one archived, one active).
-- Group dev cards by normalized title stem:
SELECT REPLACE(REPLACE(title,'[dev] ',''),'[task] ','') AS stem,
       group_concat(id) AS ids, group_concat(status) AS statuses
FROM tasks WHERE assignee='developer'
GROUP BY stem HAVING count(*) > 1;

-- Execution timeline (reveals double-dispatches, reclaims, probe artifacts):
SELECT datetime(created_at,'unixepoch','localtime') AS t, task_id, kind,
       substr(payload,1,70) AS payload
FROM task_events ORDER BY created_at;

-- Run outcomes (reclaimed / completed / blocked — the dispatch story):
SELECT id, task_id, profile, status, outcome,
       datetime(started_at,'unixepoch','localtime') AS started
FROM task_runs ORDER BY started_at;
```

### Distinguishing legitimate probes from garbage

Not all "probe" cards are artifacts:

- **Legitimate verifier sub-probes** (e.g. `[probe] fresh-eyes AC verification`,
  `[probe] static review`) have meaningful titles, real review bodies, and
  `status='done'`. They are verification work, not garbage.
- **Garbage probe artifacts** (e.g. `PROBE-ONLY-DELETE`, bare `probe`) have
  empty/placeholder bodies (`"probe"`), were created and immediately archived
  within seconds, and sit as orphan roots in `task_links` with no real children.
  The title literally signals intent to delete.

### The double-dispatch pattern

When a first `kanban_chains` dispatch is abandoned mid-execution (a child task
`reclaimed` in `task_runs`), the tech-lead may re-dispatch from scratch. This
leaves **two complete decompositions** in the same DB:

1. **Archived chain** — the abandoned first attempt (cards `status='archived'`,
   `created_by='tech-lead'`). Often matches the critic's *revised* plan.
2. **Active chain** — the shipped second attempt (cards `status` in
   `running`/`todo`/`done`, `created_by='user'`). May differ from the revised
   plan.

Trace the sequence via `task_events`: `created` → `claimed` → `spawned` →
`reclaimed`/`archived` for the first chain, then a fresh `created` burst for the
second. The gap between the two dispatches is typically 2-5 minutes.

**Scoring impact:** a double-dispatch is a dependency-structure and
right-sizing yellow flag. The active chain may not match the critic's revision
(the first chain did). Note the divergence explicitly.

## 6. Worked example — Version A (one-shot decomposition) across 3 boards

Audited the `tech-lead-execute` template (single tech-lead card → `to-tickets`
one-shot → `kanban_chains` dispatch) on 3 spec boards (ab-decom-a1/a2/a3).

### Card-count reconciliation (the matrix-root pitfall in action)

The task brief cited "2/4/2 dev cards." Actual `[task]` dev cards: **1 / 3 / 1**.
The discrepancy is the `kanban_chains` root blackboard card (body "Matrix root
/ shared blackboard"), included in an `assignee='developer'` count but not a
real dev task.

### Scores

| Board | Spec | Spec reqs | Dev cards | Coverage | Atomicity | AC quality | Dep structure | Right-sizing | TOTAL |
|-------|------|-----------|-----------|----------|-----------|------------|---------------|--------------|-------|
| A1 | Markdown Table CLI | 9 | 1 | 9 | 5 | 9 | 9 | 6 | 7.6 |
| A2 | JSON Diff Tool | 9 | 3 | 10 | 9 | 9 | 7 | 9 | 8.8 |
| A3 | Unit Converter Lib | 10 | 1 | 9 | 4 | 8 | 5 | 5 | 6.2 |

### The pattern: Version A under-decomposes on 2 of 3 specs

- **A1 and A3 each collapsed a 9-10 requirement spec into a SINGLE dev card.**
  A1 (`t_782b53`) crammed 25 ACs across alignment + escaping + errors + tests.
  A3 (`t_5d5d68`) crammed 20 ACs across 4 mathematically distinct conversion
  domains (linear units + non-linear temperature) + 3 API functions.
- **A2 is the exception and the best decomposition.** 3 serial cards
  (`t_24e57b` core engine → `t_5ef2c3` arrays+output → `t_89d78a` exit
  codes+tests), each with an explicit "clean seam" instruction for the next.
  The tech-lead decomposed well here because the single file had obviously
  sequential build layers.
- **Failure mode:** "one card per output artifact regardless of separable
  concerns." The tech-lead treated single-file/single-module specs as one card
  and failed to split by concern (alignment vs escaping in A1; linear vs
  temperature math in A3).

### The under-decomposition tell (evidence)

A3's verifier card (`t_8947c8`) had to supply edge cases the dev card omitted:
reverse temperature conversions (kelvin↔fahrenheit), negative temps, the 21-unit
count check. These are cases the spec implied; the dev AC didn't enumerate
them; the single dev card was too coarse to specify tightly. This is direct
evidence that A3 was under-decomposed, not just an opinion.

### AC authorship is the consistent strength

All three boards scored 8-9 on AC quality: numbered, testable assertions with
exact expected values (convert(0,'celsius','fahrenheit')→32.0) and exact exit
codes. This partially compensates for under-decomposition — the fat cards are
at least precisely specified. The leveraged strength to preserve.

### Dependency-structure defects were mechanical, not planning

Both A2 and A3's plan-card comments confessed `kanban_chains` misuses:
- A2: "auto-block hit a state race (block_verified=false); manually established
  the parent-child link."
- A3: "Initial kanban_chains call created dev and verify as separate parallel
  chains (structurally wrong). Fixed by adding serial dependency links."

A3's final `task_links` table still showed the stale root→verify parallel edge
alongside the hand-added serial edges — the manual fix worked but left a dirty
graph. These are tooling/usage defects in the one-shot dispatch, not planning
defects. A1's single-card chain was too simple to break.

### Report format for cross-board audits

Lead with the scores table. Then 3-5 findings, each: (a) the pattern name,
(b) which boards exhibit it, (c) concrete card IDs and AC text as evidence,
(d) whether it's a planning defect or a tooling defect. End with the
leveraged strength to preserve and the failure mode to fix.

## 7. Worked example — Version C (critic decomposition) across 3 boards

Audited the `tech-lead-execute-c` template (tech-lead → self-grill critic →
revise → `kanban_chains` dispatch) on 3 spec boards (ab-decom-c1/c2/c3). Same
specs as Version A (above) and Version B (tagged-tier). This variant adds the
critic-impact dimension (§4).

### Scores (5 generic sub-dimensions + critic-impact)

| Board | Spec | Spec reqs | Dev cards | Coverage | Atomicity | AC quality | Dep struct | Right-size | Critic impact |
|-------|------|-----------|-----------|----------|-----------|------------|------------|------------|---------------|
| C1 | Markdown Table CLI | 9 | 3 | 9 | 9 | 9 | 10 | 8 | 6 |
| C2 | JSON Diff Tool | 9 | 6 | 9 | 9 | 9 | 8 | 8 | 8 |
| C3 | Unit Converter Lib | 10 | 4 | 8 | 7 | 8 | 6 | 7 | 5 |

### C1 — the clean board

Single serial chain (core → alignment → escaping/errors), each with a
dev→verify pair. Critic ran as structured self-critique (`delegate_task`
unavailable — honest fallback). Found 3 real gaps (non-existent column behavior,
header-only CSV, align-col format tolerance) + 1 AC ambiguity. All revisions
landed in the dispatch. The critic was real but lightweight — it tightened ACs
rather than restructuring. No dispatch artifacts.

### C2 — strongest critic value

Serial chain (engine → CLI shell → array-by-id → --format json → --ignore →
integration tests) with a fan-in tail. Critic verdict REWORK with 6 findings,
all substantive: (a) split engine from CLI, (b) split --format/--ignore/tests
into separate tasks, (c) added dedicated index-array AC, (d) pinned
removed-keys output, (e) defined the JSON Change-object schema in CONTRACT.md
(was undefined → untestable), (f) replaced "human-readable" with concrete
output fragments. Card bodies carry `(Critic gap fix: ...)` inline annotations
marking where the critic's findings landed. **But** the critic subagent had
full agent tooling and called `kanban_complete` prematurely on the plan card —
`premature_completion_bug: true` in metadata. Required a recovery run. The
plan card is stuck `done` and won't auto-promote (documented honestly).

### C3 — strongest analysis, weakest execution (the double-dispatch board)

Critic found 8 real issues including a DAG bug (test task depended on sibling
task 3, NOT task 2 — temperature test could execute before temperature code
existed), Req-9 no-owner (no AC checks for external imports), T3 bundling
three independent API functions, and multiple untestable ACs. The revised plan
was excellent (5 tasks with format split out, DAG bug fixed via fan-in).

**But the dispatch was a three-attempt mess** (traceable via `task_events`):

1. **Attempt 1 (archived):** First `kanban_chains` created the revised 4-task
   parallel chain (`t_49523758` skeleton + 3 parallel children). The skeleton
   task was claimed and spawned (`run_id=3`) but then `reclaimed` ("task
   archived with run still active"). All 4 cards archived at 10:04:04.
2. **Attempt 2 (PROBE-ONLY-DELETE):** A probe `kanban_chains` invocation left
   `t_a679de1d` ("PROBE-ONLY-DELETE") as root + `t_8378cd3d` ("probe") as
   child. Both immediately archived. Empty placeholder bodies. This is a
   worker testing the API before committing — the title signals intent to
   delete, but the cards persist as archived garbage.
3. **Attempt 3 (ACTIVE):** Final dispatch: `t_89c25a47` root → `t_c2c81510`
   skeleton → `t_5e07f3e5` temperature → `t_8f31050b` list_units+format+
   convert_batch → `t_91fbc9d8` pytest → `t_3679f9ce` verify. **4 dev tasks,
   serial, format re-bundled into T3** — partially ignoring the critic's split
   recommendation. The DAG bug was sidestepped by over-serializing tasks the
   critic said could be parallel.

### The PROBE-ONLY-DELETE question: is this a bug in the approach?

**Yes.** It is not a deliberate verification artifact. Compare to B3's probe
cards (`[probe] fresh-eyes AC verification`, `[probe] static review`) which are
legitimate verifier sub-tasks with meaningful titles and real review work. C3's
PROBE-ONLY-DELETE / probe are empty placeholders created and archived within
seconds — a failed `kanban_chains` probe that leaked into the DB.

### Cross-variant comparison

```
| Spec      | Variant-A | Variant-B | Variant-C |
|-----------|-----------|-----------|-----------|
| mdtable   | 1 (monolith) | 1 | 3 (serial slices) |
| jsondiff  | 3         | 5         | 6 (most granular) |
| unitconv  | 1 (monolith) | 1 | 4 |
```

Version C consistently produces the most granular decompositions. For mdtable
and jsondiff this is a clear improvement over A/B's monoliths. For unitconv,
C's critic correctly diagnosed the monolith problem A/B both shipped — but C's
own dispatch was buggy (double-dispatch + probe leakage + revision partially
ignored).

### The critic template has two visible defects

1. **Premature completion** (C2): the critic subagent gets full tool access and
   can call `kanban_complete`, closing the plan card before dispatch.
2. **kanban_chains probe leakage** (C3): the worker probes the chains API
   mid-run, leaving archived garbage cards (PROBE-ONLY-DELETE). No other
   variant exhibits this — A/B don't probe `kanban_chains`.
