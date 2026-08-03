# Architecture Decision Methodology — Multi-Round Subagent Review

> Technique validated 2026-08-02 for the stateless graph engine design. Produced
> a rock-solid design through 3 review rounds with zero human intervention on
> technical correctness.

## When to use

When making a significant architecture decision (engine rewrite, state model
change, new orchestration pattern) that will cost 1000+ lines and is hard to
reverse. The cost of 5-6 subagent reviews (~15 min total) is trivial compared
to implementing a flawed design.

## The technique

### Step 1: Write a design doc FIRST

Before any review, write a complete design doc covering:
- Problem statement (what's broken and why)
- What to keep / rip out / replace (be specific about line counts)
- The core algorithm or data flow (pseudocode, not prose)
- Migration plan (how to get from here to there without losing data)
- Scope estimate (honest, broken down by component)
- Risks and mitigations
- What you are NOT doing (scope boundaries)

The doc forces you to think through the design before reviewers find gaps. A
vague doc gets vague reviews.

### Step 2: Round 1 — broad coverage (5 subagents, different lenses)

Dispatch 5 subagents, each with a DIFFERENT review lens. Do NOT give them all
the same generic "review this" prompt. Each lens should force a different
reading of the code:

- **State/concurrency lens** — races, atomicity, crash recovery, lost updates
- **Algorithm correctness lens** — does the core algorithm actually work? Edge
  cases, ordering, missing steps
- **Backwards compatibility lens** — test breakage count, DB migration, import
  failures, completion semantics equivalence proofs
- **Trigger/handoff lens** — cross-workflow interaction, guard logic, key format
  changes
- **Scope completeness lens** — did the doc account for ALL the logic in the
  current code? Method-by-method inventory. Is the estimate realistic?

Each subagent reads the ACTUAL code (not just the design doc) and grounds every
claim in file:line references. This is critical — a review that doesn't read the
code is just opinion.

Batch into groups of max_concurrent_children (3 at a time).

### Step 3: Synthesize — group findings by severity

Collect all review outputs. Group findings into:
- **BLOCKERS** (CRITICAL/HIGH) — must fix before implementation
- **SPEC GAPS** (MEDIUM) — must specify before coding (algorithm undefined, etc.)
- **NON-BLOCKING** (LOW) — nice-to-have documentation, can address during impl

The synthesis should produce a numbered list of exactly what to fix.

### Step 4: Revise the design doc

Fix ALL blockers and spec gaps in the design doc. Be specific — add pseudocode,
add crash-safety arguments, add the exact algorithm that was missing. Don't
hand-wave; if you can't specify it precisely, you don't understand it well enough
to implement it.

### Step 5: Round 2 — targeted re-review (3 subagents)

Dispatch 3 subagents, each checking whether specific v1 blockers were fixed.
Give them the v1 review for context. They verify FIXED / PARTIALLY FIXED / NOT
FIXED for each concern. This catches fixes that look right but have subtle gaps.

### Step 6: Iterate until APPROVED

If round 2 finds blockers, fix them (v2.1, v3, etc.) and re-review. Each round
should find fewer issues. When all reviewers say APPROVED FOR IMPLEMENTATION,
the design is rock solid.

## Key principles

1. **Each reviewer reads the actual code.** A design review without code
   references is opinion, not engineering. Every finding should cite file:line.
2. **Different lenses find different bugs.** The concurrency reviewer found the
   non-atomic blob; the scope reviewer found the 850 lines of unaccounted dispatch
   logic; the backcompat reviewer found the completion model non-equivalence. No
   single lens would have found all three.
3. **Quantify impact.** "57 node_states queries across 10 files" is actionable.
   "Tests will break" is not. Reviewers should count, not estimate.
4. **The estimate is a finding, not a given.** If all reviewers say the estimate
   is naive by 2x, it is. Accept the revised estimate; don't defend the original.
5. **Iteration converges.** Round 1 found 7 gaps. Round 2 found 2. Round 3 found
   0. Each round is cheaper than implementing a wrong design.

## Anti-patterns

- **"Review this design"** (generic prompt) — produces generic reviews. Always
  assign a specific lens.
- **Reviewers who don't read code** — they can only check the doc's internal
  consistency, not whether the design works against the real engine.
- **Defending the design against reviewers** — the reviewer is right more often
  than the designer. Fix the design, don't argue.
- **Stopping after round 1** — round 1 finds the obvious gaps. Rounds 2-3 find
  the subtle ones that would have cost days during implementation.
