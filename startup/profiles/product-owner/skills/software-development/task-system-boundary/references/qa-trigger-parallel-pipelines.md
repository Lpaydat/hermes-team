# QA Trigger in Parallel Tracer-Bullet Pipelines

When the PO decomposes an epic into N parallel tracer-bullet slices (each a dev+verifier pair via `kanban_chains`), slices merge to master independently and often near-simultaneously. Phase 5's per-card QA trigger fires once per merge — a 3-slice epic can produce 3 QA cards within minutes. Each QA card spawns a swarm (5-7 agent sessions for medium/large artifacts), so 3 cards = 15-21 sessions doing largely overlapping work on progressively larger states ({S1}, {S1+S2}, {S1+S2+S3}).

This reference captures the design decision (keep per-merge, add debounce) and the implementation technique.

## Why NOT switch to post-all-merge (Approach B)

The alternative — fire QA once after ALL slices of an epic merge — was evaluated and rejected:

- **Implementation complexity:** Requires tracing card → bead → epic to detect "all slices merged." The current trigger is self-contained per-card; epic-grouping restarts the 5-iteration failure-mode cycle (see pipeline-gaps-livetest.md, gaps 3→15). Estimated 2-4 days for a new trigger that may need its own livetest cycle.
- **Single point of failure:** Engine downtime >1h (lookback window), a missed regex match, or a stuck slice = zero QA for the entire epic. Per-merge degrades gracefully — each card is independent.
- **Later feedback:** Bugs in early-merging slices aren't caught until the last slice merges.
- **Bisection value lost:** Per-merge QA on {S1} then {S1+S2} can isolate which slice introduced a regression. A single post-all-merge run can't.

The cost saving of B (1 swarm vs 3) is real but bounded and non-blocking — QA runs in the background and doesn't stall slice dev or merges.

## The debounce technique (recommended refinement)

Coalesce near-simultaneous merges into a single QA card via a time window. Purely time-based — no epic-grouping, no cross-card state.

**Logic:**
1. When phase 5 detects a merge (existing regex path), before creating the QA card:
2. Query for any QA card on this board in `todo`/`ready`/`running` status created in the last 10 minutes.
3. If one exists: append this merge's context to it as a comment, skip card creation (debounced).
4. If none exists: create the QA card as normal (it will catch any other merges within the next 10 min).

**Result:** 3 slices merging within 10 min → 1 QA card (not 3). Slices merging hours apart → still fires per-merge (preserves early feedback).

**Implementation (~30 lines in `phase_qa_trigger`):**

```python
# After the merge-pattern regex check passes, before run_kanban create:
DEBOUNCE_WINDOW = 600  # 10 minutes

debounce_cutoff = int(time.time()) - DEBOUNCE_WINDOW
pending = conn.execute(
    """SELECT id FROM tasks
       WHERE assignee = 'qa'
         AND status IN ('todo', 'ready', 'running')
         AND created_at > ?
       LIMIT 1""",
    (debounce_cutoff,)
).fetchall()

if pending:
    # Append this merge's context to the pending QA card
    run_kanban(board, [
        "comment", pending[0]["id"],
        "--body", f"**Additional merge detected:** {title}\n\n{summary_text}"
    ])
    actions.append(f"qa-trigger: debounced — appended context to {pending[0]['id']}")
    continue

# ... proceed with normal QA card creation
```

## Sizing the debounce window

| Window | Effect |
|--------|--------|
| 5 min | Too short — slices often merge 5-10 min apart in parallel dev. Misses coalescing. |
| 10 min | Sweet spot for 2-4 slice epics with parallel dev. Catches most bursts. |
| 20+ min | Risk of delaying feedback for genuinely sequential merges. Slices that merge 20+ min apart probably represent independent work batches. |

Start at 10 min, adjust based on observed merge clustering.

## When to revisit (escalation path)

If debounce proves insufficient (slices consistently merge >10 min apart but per-merge token cost is prohibitive):

**B-lite:** Fire QA after the LAST slice of an epic merges, but with a fallback — if no "all slices merged" detection fires within 2 hours of the first merge, fire per-merge QA for whatever has merged. This gives B's efficiency in the common case with A's safety net. Still requires card→bead→epic tracing — don't implement until debounce is proven inadequate.

## Full analysis

The complete trade-off matrix (efficiency, risk coverage, latency, implementation complexity, failure modes) is in the session artifact:
`docs/analysis/qa-trigger-per-merge-vs-post-all-merge.md` (project repo)
