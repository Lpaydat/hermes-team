# Iterative Design Review — Methodology

> Technique: review a design doc with parallel subagents, fix all findings,
> re-review until rock solid. Used for the stateless graph engine redesign
> (4 rounds, 9 reviewers total, caught 8 load-bearing bugs before any code
> was written).

## When to use

Any non-trivial design doc (architecture, rewrite, migration plan) before
implementation begins. The cost of a design bug found in review is ~10x
cheaper than one found during implementation, and ~100x cheaper than one
found in production.

## The cycle

1. **Write the design doc** — be concrete: data structures, algorithms,
   line-level scope estimates. Vague docs produce vague reviews.

2. **Round 1: multi-focus parallel review** — dispatch 3-5 subagents, each
   with a DIFFERENT focus area (concurrency, algorithm correctness, backwards
   compat, scope completeness, industry patterns). They read the ACTUAL code
   the design replaces, not just the design doc. Each produces a structured
   review with risk ratings and concrete fixes.

3. **Revise the design** — close every gap found. Update the estimate if
   scope was underestimated. Be honest — don't deflect findings.

4. **Round 2: focused re-review** — dispatch reviewers for the areas where
   round 1 found blockers. Each checks whether their specific concerns were
   addressed, with quotes from the revised doc. This is NOT a general "looks
   good" pass — it's targeted verification.

5. **Repeat 3-4 until no blockers remain.** Non-blocking nits are fine; any
   item rated CRITICAL or HIGH must be FIXED or explicitly accepted with
   rationale.

## Key lessons (from the stateless graph engine review)

**Parallel focused reviewers beat sequential generalists.** Round 1 had 5
reviewers each focused on one domain. They found 7 issues. Round 3 had 1
generalist reviewer who said APPROVED but missed the node_phase() bug that
the round-2 graph-walk specialist caught. When re-reviewing after fixes,
cover the SAME focus areas as the round that found the bug.

**Line-count estimates are almost always naive for rewrites.** The v1 design
estimated ~1300 lines. The scope reviewer proved it was ~2500-3000 by
enumerating every method that must be preserved verbatim. The mistake: framing
a rewrite as "rip out X" when ~850 lines of dispatch topology is orthogonal
to X and must be ported. Lesson: for any rewrite, inventory EVERY method in
the current code and classify each as "rip," "port verbatim," or "rewrite."
The "port verbatim" bucket is where estimates go wrong.

**Derived functions that set flags must also read them.** The node_phase()
function wrote `skipped=True` and `failed=True` but never checked those flags
in its own logic — so the walker was blind to the states it produced. This
is a general pattern: any time a function writes state that another part of
the algorithm reads, verify the read path actually checks it.

**Single JSON blob persistence needs optimistic versioning.** A naive
read-modify-write (SELECT → mutate → UPDATE) is non-atomic. Two overlapping
ticks silently clobber each other. Fix: `WHERE version = ?` on every save,
discard on rowcount==0. This is the standard LangGraph/STM pattern.

**Completion models must account for ALL terminal states.** "All exit nodes
done" sounds right but breaks for conditional diamonds — a skipped exit node
(skipped = dead branch) is neither done nor failed. Fix: terminal-for-exit =
{done, failed, skipped}. This is provable: the models are equivalent iff no
skipped node is a leaf.

## Subagent dispatch pattern

```
Round 1: 3-5 subagents, each focused on one domain
  - Concurrency / state correctness
  - Algorithm correctness (the core logic)
  - Backwards compatibility / migration safety
  - Scope completeness (did they count everything?)
  - Industry patterns / prior art

Round 2+: 1-3 subagents, each re-checking a specific blocker domain
  - Read the REVISED doc + the v1 review that found the bug
  - Quote the relevant text to prove the fix is real
  - Produce VERDICT: FIXED / PARTIALLY FIXED / NOT FIXED / NEW ISSUE

Final: 1 subagent, full scan for remaining blockers
  - Must trace function bodies line by line, not just read docstrings
```

Max concurrency is 3 subagents per delegate_task call. For 5 reviewers, use
two batches (3 + 2). Results stream back asynchronously — don't wait idle.
