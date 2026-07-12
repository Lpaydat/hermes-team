# ADR-003: Design-council v2 — evaluate-gated loop (autoresearch-inspired)

- Status: Accepted
- Date: 2026-07-12
- Deciders: tech-lead
- Introduced-by: hermes-teams-jov (refines) / `intercom-qre` (implements)
- Refines: ADR-002 (`ADR-002-design-council.md`) — the v1 stakes-led council

## Decision

Replace v1's **self-confidence-gated** iteration (the architect's own H/M/L
confidence decides whether to iterate) with an **evaluate-gated** loop: after
each synthesis, an **independent evaluator** (the `verifier` profile) scores
the design across five rubric dimensions and returns a verdict
(`improve | converged | regressed`). The architect acts on the verdict —
improving targeted weaknesses, discarding regressions, and converging when the
score plateaus or clears the bar.

The loop is **improve → evaluate → keep/discard → converge**, monotonically:
each round is kept only if the evaluator score improved; a regressed round is
reverted to the *best-so-far* design-doc version. This is the
autoresearch pattern (edit → measure `val_bpb` → keep/discard) applied to
design quality, with the crucial difference that design quality is a
**subjective proxy** (an LLM judge with a structured rubric), not ground truth.

The five evaluator dimensions, each with concrete checkable anchors:
**correctness** (the proxy_cache class — technical errors), **depth** (the
scaling-analysis class — shallow hard sections), **alternatives** (the strawman
class — steelmanned options), **edge cases** (the failure-semantics class),
**consequences** (risk coverage). The evaluator output is a structured schema
with scores, grounded flags (every flag cites the exact passage), a delta
vs the prior round, and a verdict.

Stakes-scaling governs evaluator cost:
- **Low** — no evaluator (1 round; the floor is the ceiling).
- **Standard** — single judge (`verifier`), ≤3 rounds, plateau at delta < 0.3.
- **High** — ensemble of 3 independent judges (averaged, flags unioned,
  critical-flag agreement required), ≤5 rounds.

## Context

ADR-002 established the v1 design-council: research + peer perspectives via
`kanban_chains`, stakes-led scaling, and the architect's self-reported
confidence (H/M/L) as the iteration gate. V1 was validated across low/standard/
high tiers on 2026-07-12 — all three passed functionally.

An adversarial quality review (4-agent workflow, same day) exposed v1's core
weakness: **self-confidence is a weak iteration signal.** The review found:

1. **A correctness defect shipped as a benefit.** The proxy_cache click-
   undercounting bug (nginx caches the 302, so a cache HIT never reaches the
   app → ~90% undercount on warm links) was presented as a *positive* in round
   1. The architect's self-confidence said "high." A *second independent* peer
   pass in round 2 caught it. A solo architect (or one who trusted self-
   confidence) would have shipped a core-feature-breaking bug.
2. **Depth hand-waved where stakes were highest.** The multitenant scaling
   analysis — the #1 operational pain for DB-per-tenant — got one generic
   sentence ("we can scale horizontally"). Self-confidence said "high."
3. **CLI tier over-invested.** 2 ADRs + 2 councils for a 17-line throwaway.
   Self-confidence didn't flag the inverted depth-to-stakes ratio.

An independent evaluation caught all three. The upgrade: replace the signal.

## Alternatives Considered

### Option A: Keep v1's self-confidence gate (rejected)

Self-reported H/M/L confidence as the iteration signal. **Rejected because:**
the quality review proved it misses correctness defects, depth gaps, and
cost-discipline failures. It optimizes for the architect's self-assessment,
not for independent quality. The proxy_cache bug is the decisive evidence.

### Option B: Add a verifier gate on the ADR only (rejected)

A single verifier check after the ADR is written, rejecting ADRs that fail
the rubric. **Rejected because:** this catches defects *after* the design is
fixed, not during iteration. The keep/discard mechanic — reverting a bad round
— requires evaluation *inside* the loop, not just at the end. A post-hoc gate
is ADR-002's already-rejected Option D, just delayed.

### Option C: Objective metric (autoresearch-faithful) (rejected)

Seek a ground-truth signal analogous to `val_bpb` — e.g. "does the design
survive a property-based test suite?" **Rejected because:** design quality
does not have an objective metric. The closest proxies (static analysis,
threat modeling) cover narrow dimensions and miss the subjective strengths
(depth, alternatives, consequences). The rubric is an honest admission that
the signal is subjective, with mitigations (concrete anchors, grounded flags,
ensemble, noise floor) rather than a false promise of objectivity.

### Option D: Self-evaluation with the rubric (rejected)

The architect loads the rubric and scores their own design. **Rejected
because:** this destroys maker/checker separation. The same context window
that wrote the design grades it — the sycophancy failure mode that makes
self-grading unreliable in code verification applies identically here. The
whole point is independence.

### Option E: Evaluate-gated loop with independent judge (ACCEPTED)

The architect creates an evaluator card (assigned to `verifier`) after each
synthesis. The evaluator scores across five dimensions with concrete anchors,
returns grounded flags + a verdict. The architect improves, reverts, or
converges based on the verdict. **Accepted because:**

- It replaces the weak signal (self-confidence) with the one that caught all
  three v1 defects (independent evaluation).
- The keep/discard mechanic (best-so-far tracking, revert on regression) makes
  the design monotonically improve — v1's critique rounds only accumulated.
- Stakes-scaling bounds the cost: low stakes pay nothing (no evaluator),
  standard pays one judge, high pays an ensemble.
- It reuses existing infrastructure: `kanban_chains` (the improve step), the
  `verifier` profile (the judge), and the design-council skill (the loop).
- The subjective-metric risk is mitigated (not eliminated) by concrete anchors,
  grounded citations, ensemble averaging, and a noise-floor threshold.

## Consequences

- **Positive.** The iteration signal catches what self-confidence misses —
  the proxy_cache-class defects, the depth gaps, the cost-discipline failures.
  The keep/discard mechanic ensures the design only gets better. The
  stakes-scaling pays the evaluator cost only where a missed defect is most
  expensive. The rubric makes quality criteria explicit and checkable, so the
  evaluator can be audited, not just trusted.
- **Negative.** Each standard-stakes round now costs an extra spawned
  evaluator session (+3 at high stakes for the ensemble). More cards, more
  tokens, more latency per decision. The evaluator is a subjective proxy —
  it can overfit to judge bias, drift across rounds, or flag noise. Mitigated
  by concrete anchors, grounded flags, ensemble, and noise floor, but not
  eliminated.
- **Residual risks.**
  - **Judge overfitting.** The loop optimizes for the rubric, not for real
    quality. If the rubric's anchors are wrong, the loop converges on a
    well-scored but wrong design. Remedy: tune the anchors against real
    defects (the proxy_cache class is the first test case).
  - **Convergence threshold.** Plateau at delta < 0.3 is a starting value.
    Too tight → infinite loop; too loose → premature convergence. Must be
    calibrated on real runs.
  - **Ensemble cost.** 3× evaluator spawns at high stakes. If the ensemble
    doesn't materially improve quality vs a single judge (bias reduction
    insufficient), downgrade to single-judge at high stakes too.
- **Ownership.** The `verifier` profile gains a second role: design evaluator
  (in addition to code verifier). The architect loses the self-confidence gate
  and gains the evaluator gate — less autonomy, more rigor. The rubric is
  maintained by tech-lead (skill-authoring domain).
- **Open.** The keep/discard mechanic relies on the architect maintaining a
  best-so-far version faithfully. A lazy architect could skip the revert. The
  evaluator's grounded output (citing the regressed passages) makes this
  auditable, but not enforced. A future Option: a structural "version lock"
  that prevents accumulation without a score-improvement.

## Citations

- v1 quality review (2026-07-12, 4-agent workflow): found proxy_cache defect
  shipped as a benefit (self-confidence "high"), scaling hand-waved
  (self-confidence "high"), CLI over-invested.
- bd memory `design-council-standard-run-board-dc-val-design`: the standard
  run where research corrected the peer's limit_req assumption (leaky, not
  token bucket) — evidence that independent review catches what self-assessment
  misses.
- ADR-002 § Decision (the v1 council this refines) and § Open ("Lazy-accept
  risk — the architect could call a thin council and declare high confidence.
  Option D (verifier) is the remedy if it becomes observed.") — this ADR
  *is* that remedy.
- Karpathy's autoresearch (https://github.com/karpathy/autoresearch): the
  improve → measure `val_bpb` → keep/discard loop against a metric.
- `references/eval-loop-v2-plan.md` (commit `1cd962b`): the planning document.

## References

- v1 skill: `startup/profiles/architect/skills/architecture/design-council/`
  (this commit evolves it)
- Evaluator rubric: `references/evaluator-rubric.md` (new, this commit)
- Call templates: `references/call-templates.md` (updated, this commit)
- Planning doc: `references/eval-loop-v2-plan.md`
- ADR convention: `docs/agents/adr-convention.md`
