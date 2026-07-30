# QA Trigger in Parallel Tracer-Bullet Pipelines

## IMPORTANT CORRECTION: Dispatch is Sequential, Not Parallel

**Livetest finding (2026-07-30):** The workflow engine dispatches ONE ready bead
at a time to the tech-lead. Each tech-lead card receives ONE bead, creates
dev+verifier cards, iterates until merge, completes. Then the engine dispatches
the next ready bead. In a 3-slice livetest, slices merged ~1 hour apart
(05:34, 06:33, 07:31). **The "merge burst" problem does NOT occur with
sequential dispatch.**

This means:
- **Per-merge QA is correct** — each merge creates a stable, long-lived state
  of master (~1 hour) that QA tests independently.
- **The debounce technique below is unnecessary** unless the dispatch model
  changes to parallel (multiple tech-lead cards running simultaneously).
- The 3 QA cards in the clean livetest run were all legitimate — each tested a
  genuinely different, stable state of master.

## When This Reference Applies

The debounce technique becomes relevant IF:
- The dispatch model changes to parallel (multiple tech-lead cards per project)
- The team runs multiple gateway instances per profile
- A future harness dispatches all ready beads simultaneously

In the current sequential model, keep per-merge QA as-is.

## Why NOT switch to post-all-merge (Approach B)

The alternative — fire QA once after ALL slices of an epic merge — was evaluated
and rejected:

- **Implementation complexity:** Requires tracing card → bead → epic to detect
  "all slices merged." The current trigger is self-contained per-card;
  epic-grouping restarts the 5-iteration failure-mode cycle.
- **Single point of failure:** Engine downtime >1h (lookback window), a missed
  regex match, or a stuck slice = zero QA for the entire epic. Per-merge
  degrades gracefully — each card is independent.
- **Later feedback:** Bugs in early-merging slices aren't caught until the last
  slice merges.
- **Bisection value lost:** Per-merge QA on {S1} then {S1+S2} can isolate which
  slice introduced a regression. A single post-all-merge run can't.

## The debounce technique (for future parallel dispatch)

Coalesce near-simultaneous merges into a single QA card via a time window.
Purely time-based — no epic-grouping, no cross-card state.

**Logic:**
1. When phase 5 detects a merge (existing regex path), before creating the QA card:
2. Query for any QA card on this board in `todo`/`ready`/`running` status created
   in the last 10 minutes.
3. If one exists: append this merge's context to it as a comment, skip card
   creation (debounced).
4. If none exists: create the QA card as normal (it will catch any other merges
   within the next 10 min).

**Result:** 3 slices merging within 10 min → 1 QA card (not 3). Slices merging
hours apart → still fires per-merge (preserves early feedback).

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
    run_kanban(board, [
        "comment", pending[0]["id"],
        "--body", f"**Additional merge detected:** {title}\n\n{summary_text}"
    ])
    actions.append(f"qa-trigger: debounced — appended context to {pending[0]['id']}")
    continue

# ... proceed with normal QA card creation
```

## Decomposition Hierarchy (for reference)

```
Epic (bead, P1)
├── Slice 1 (bead, P2) — feature: complete, shippable on its own
│   └── dev/verifier cards (kanban, ephemeral) — one PR's worth of work
├── Slice 2 (bead, P2) — feature: slice 1 + more capability
│   └── dev/verifier cards (kanban, ephemeral)
└── Slice 3 (bead, P2) — feature: slice 2 + robustness
    └── dev/verifier cards (kanban, ephemeral)
```

Each slice IS a feature, not a fragment needing assembly. Slices are progressive
enhancements. The tech-lead receives one slice bead at a time (sequential
dispatch) and creates dev+verifier execution cards via `kanban_chains`.

## Full analysis

The complete trade-off matrix (efficiency, risk coverage, latency, implementation
complexity, failure modes) is in the session artifact:
`docs/analysis/qa-trigger-per-merge-vs-post-all-merge.md` (project repo)

Real-world CI/CD research (Google TAP, GitLab merge trains, GitHub merge queue,
Facebook push-on-green, CD book) is in:
`merge-burst-qa-research.md` (project repo)
