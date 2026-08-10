# qa-gate Trigger Suppression Bug (CONFIRMED + FIXED 2026-08-08)

## Symptom

Full dev pipeline runs end-to-end. All verifier cards complete with
`verdict: "PASS"` in task_runs.metadata. But qa-gate NEVER fires. Zero
qa-gate instances created.

## Confirmed Evidence (wf-test board, 2026-08-08)

- 89 cards total, 5 tickets all closed + merged
- 6 verify-b/re-verify-b cards, all with `verdict: "PASS"` in task_runs.metadata
- Metadata is rich and correct: `{"verdict": "PASS", "behavior_tests_total": 31, ...}`
- Zero qa-gate instances on the board
- User asked "I don't see qa run" — caught the missing stage

## Root Cause

The self-trigger suppression logic in `_check_triggers()` (runtime.py ~line 2990)
blocks ALL cross-workflow triggers when the card was created by a workflow that
uses explicit edges.

```python
if card.idempotency_key:
    parent_wf_id = _extract_parent_workflow(card.idempotency_key)
    if parent_wf_id is not None:
        if parent_wf_id == wf.id:
            continue  # same-workflow self-trigger (CORRECT)
        parent_wf = self.store.load(parent_wf_id)
        if parent_wf and parent_wf.edges:
            continue  # parent routes internally — skip (← THIS IS THE BUG)
```

The verify-b cards have idempotency keys like:
```
wf:wf_1786182348_tech-lead-execute_1763e5d3:verify
```

The parent workflow (`tech-lead-execute`) HAS explicit edges. So the engine
sees these cards as "already handled by their parent's internal routing"
and skips them for ALL cross-workflow triggers — including qa-gate.

## Why Gauntlet Lesson #18 Got It Wrong

Gauntlet lesson #18 claimed: "qa-gate fires correctly — not a bug." That
was observed on livetest boards where verifier cards were created via
kanban_chains (no `wf:` prefix on idempotency key). When the verify card
IS engine-dispatched (via tech-lead-execute's verify/re-verify node),
the `wf:` idempotency key triggers the suppression and qa-gate is blocked
entirely.

## The Fix Applied

Instead of patching the suppression logic, qa-gate was MERGED into
`milestone-gate.json` along with refactor-cycle. The milestone-gate
workflow fires on milestone card completion (not verifier completion).
Milestone cards have NULL idempotency keys (PO-created via kanban_create),
so self-trigger suppression does NOT apply.

The old `qa-gate.json` is disabled. The new `milestone-gate.json` contains
all QA nodes (receive, build, functional, journeys, security, explore,
quick, verdict, route-bug) plus the refactor nodes (scan, review, decompose).

See `references/milestone-gate-unification.md` for the design rationale.

## Detection Queries

```sql
-- 1. Check if verifier cards have engine idempotency keys
SELECT title, idempotency_key FROM tasks
WHERE title LIKE '[verify-b]%' OR title LIKE '[re-verify-b]%';
-- If idempotency_key starts with "wf:" → engine-created → suppressed

-- 2. Verify metadata IS present (it's in task_runs.metadata, NOT tasks.result)
SELECT task_id, outcome, metadata FROM task_runs
WHERE task_id IN (SELECT id FROM tasks WHERE title LIKE '[verify-b]%')
AND outcome = 'completed';
-- Shows {"verdict": "PASS", ...} — data exists, trigger can't reach it

-- 3. Check trigger_keys for any qa-gate triggers
SELECT * FROM trigger_keys WHERE key LIKE '%qa-gate%';
-- Empty = qa-gate never fired
```
