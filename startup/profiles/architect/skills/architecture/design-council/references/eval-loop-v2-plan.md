# Design-Council v2: Evaluate-Gated Architecture Loop (autoresearch-inspired)

> **Status:** Planning — for implementation in a new session.
> **Builds on:** design-council v1 (stakes-led, kanban_chains-based, intercom interview),
> validated across low/standard/high tiers on 2026-07-12. All code committed.
> **Reference:** https://github.com/karpathy/autoresearch (the improve→measure→keep/discard pattern).

## Why evolve — the gap v1 revealed

design-council v1 works: all 3 tiers pass, the intercom interview functions, ADRs are
research-backed + cite the council. But an adversarial quality review (4-agent workflow,
2026-07-12) exposed the core weakness:

**The v1 loop iterates on the architect's SELF-CONFIDENCE — a weak signal.** The review found:
- **proxy_cache click-undercounting defect** shipped as a *benefit* in round 1 (self-confidence
  said "high"). Caught only by a SECOND independent peer pass (round 2). A solo architect
  would have shipped a core-feature-breaking bug.
- **Multitenant scaling analysis hand-waved** — connection pooling at 1000+ tenants (the #1
  DB-per-tenant operational pain) gets one generic sentence. Self-confidence said "high."
- **CLI tier over-invested** — 2 ADRs + 2 councils for a 17-line throwaway. Self-confidence
  didn't flag the inverted depth-to-stakes ratio.

An **independent evaluation** caught all three. The upgrade: **replace self-confidence with
independent evaluation as the iteration signal.**

## The idea — autoresearch for the architect

Karpathy's autoresearch: edit `train.py` → train 5min → measure `val_bpb` → keep if improved,
discard if not → repeat. Its power: `val_bpb` is **ground truth** (an objective number).

The architect analogue: **improve the design → evaluate quality (independent judge) → keep if
improved, revert if not → repeat.** Crucial difference: "design quality" is **subjective** (an
LLM judge with a rubric), not ground truth. The transfer is valuable (independent evaluation
catches what self-confidence misses) but the signal is noisier. **The evaluator quality is the
crux of the whole loop.**

## The design — evaluate-gated loop with keep/discard

### Loop structure
```
Round N:
  1. IMPROVE  — round 1: research + perspectives + synthesis (kanban_chains, as v1)
              — round 2+: TARGETED improvement on the evaluator's flagged weaknesses
  2. EVALUATE — an independent judge scores across 5 dimensions + flags specific weaknesses:
              correctness / depth / alternatives-weighed / edge-cases-failure-semantics / consequences
              → overall score (1-5 per dimension) + delta vs round N-1 + grounded citations
  3. DECIDE   — score improved over N-1?            KEEP   → round N+1
              — plateau (delta < threshold, 2 rounds)? CONVERGED → write ADR
              — max rounds (stakes-scaled)?           STOP   → write ADR (+ Residual risks)
```

### The evaluator (build FIRST — the crux)
- **Structured rubric** — 5 dimensions, each with CONCRETE CHECKABLE criteria (not "is it
  good?"). The v1 rubric = this session's quality-review dimensions (the 4-agent workflow is
  the template). Anchors must be specific: "does it name PgBouncer / connection-pool
  economics?" not "is the scaling analysis adequate?"
- **Judge** — an independent agent. Candidates: the `verifier` profile (exists), a dedicated
  judge, or for high-stakes an **ensemble** (3 judges, average/majority) to reduce individual
  bias. The judge output must be GROUNDED (cite specific ADR passages) — no generic flags.
- **Output schema:** `{dimension_scores: {correctness, depth, alternatives, edge_cases,
  consequences}, overall, delta_vs_last, flagged_weaknesses: [{dimension, issue, severity,
  citation}], verdict: improve|converged|regressed}`.

### Convergence
- **Plateau:** overall score delta < threshold over 2 consecutive rounds → converged.
- **Max rounds (stakes-scaled):** low=1 (no evaluator), standard=3, high=5.
- **Non-convergence at max:** write ADR with a *Residual risks / open quality gaps* section
  (the evaluator's remaining flags), so the gap is visible, not hidden.

### Keep/discard (the autoresearch mechanic)
- Each round's improvement is **kept if the score improved; reverted if decreased.** The design
  monotonically improves (bad rounds are undone). v1 only accumulates (critique rounds stack);
  it never says "that round regressed, undo it." Open question: how does the architect "revert"?
  (maintain a best-so-far design-doc version? git-style? see Open Questions.)

### Stakes-scaling (cost discipline — addresses the CLI over-investment)
| Stakes | Evaluator | Max rounds | Convergence |
|---|---|---|---|
| **Low** | none (converges immediately — don't burn evaluator cost on a throwaway) | 1 | n/a |
| **Standard** | single judge | 3 | plateau detection |
| **High** | ensemble (3 judges) | 5 | plateau + ensemble agreement |

## The crucial challenge — subjective metric

autoresearch's `val_bpb` is infallible. The architect's evaluator is a **proxy**. Risks:
- **Overfitting to the judge** — the loop optimizes for the judge's biases, not real quality.
- **Judge drift** — inconsistent scores across rounds/judges.
- **False positives** — the judge flags non-issues → the loop chases noise.

Mitigations: structured rubric with concrete anchors; ensemble for high-stakes; grounded output
(cite passages); a noise-floor threshold (ignore low-severity flags).

## Implementation plan

### Phase 1 — the evaluator (FIRST; it's the crux)
1. Design the rubric: 5 dims × concrete criteria. Ground in the quality-review findings:
   - correctness → the proxy_cache class (conflations, technical errors).
   - depth → the scaling-analysis gap (hand-waved sections, missing mechanisms).
   - alternatives → strawman detection (are options real + steelmanned?).
   - edge-cases → failure semantics (write-failure paths, operational concerns).
   - consequences → risks covered (positive/negative/residual).
2. Pick the judge: `verifier` profile vs dedicated. Ensemble size for high-stakes.
3. Implement as a kanban card (assignee: judge) the architect creates after each synthesis.
4. The evaluator output schema (above).

### Phase 2 — the loop (evolve the skill)
1. Replace the v1 confidence-gated step 4 with the evaluate-gated step: evaluate → decide on
   score delta → keep/adjust/converge.
2. The kanban topology per round: kanban_chains (improve) + an evaluator card (evaluate); the
   architect orchestrates (create → park → resume → read eval → decide).
3. The keep/discard: maintain a best-so-far design version; revert on regression.

### Phase 3 — stakes-scaling + convergence
1. Stakes-scale (low: 1 round/no evaluator; standard: single judge/3; high: ensemble/5).
2. Convergence: plateau detection + max rounds.

### Phase 4 — validation
1. Re-run the 3 tiers with the eval loop. Compare quality vs v1 (the quality-review findings
   are the baseline — does v2 catch proxy_cache-class defects in round 1? does it deepen the
   scaling? does it avoid the CLI over-investment?).
2. Cost comparison: tokens/time per decision, v1 vs v2.

## Where to start (new session)
1. **Read:** this plan + `SKILL.md` + `call-templates.md` (the v1 skill) + ADR-002
   (`docs/adr/ADR-002-design-council.md`) + the quality-review findings (bd memory
   `design-council-validation-2026-07-12-board-dc` + the intercom memories).
2. **Start with Phase 1** (the evaluator rubric). Ground it in the quality-review dimensions.
   The 4-agent quality-review workflow from this session is the v1 evaluator template.
3. **Existing infrastructure:** `kanban_chains` (the improve step), the `verifier` profile
   (judge candidate), the design-council skill (the loop to evolve), the intercom ask (the
   PO interview, already working).
4. **The autoresearch reference:** https://github.com/karpathy/autoresearch — the
   improve→measure→keep/discard loop against a metric.

## Key files
| File | Purpose |
|---|---|
| `startup/profiles/architect/skills/architecture/design-council/SKILL.md` | v1 skill (the loop to evolve) |
| `startup/profiles/architect/skills/architecture/design-council/references/call-templates.md` | v1 kanban_chains templates |
| `docs/adr/ADR-002-design-council.md` | v1 decision record (5 alternatives weighed) |
| `_shared/intercom/broker/server.py` (commit a5b19e9) | the offline-ask-spawn fix (the interview mechanism) |
| `_shared/intercom/broker/spawner.py` (commit de05228) | fail-loud HERMES_HOME (prevention) |
| bd memories | `design-council-validation-…`, `intercom-fixed-…` (the session findings) |

## Open questions (for the new session)
1. **Judge profile:** `verifier` (exists) vs a dedicated judge? Or the architect self-judges
   with the rubric (weaker, no extra spawn — but no independence)?
2. **Ensemble size** for high-stakes: 3 judges? Majority or average? Cost budget?
3. **Keep/discard mechanic:** how does the architect "revert" a regressed round? Maintain a
   best-so-far design-doc file? A versioned stack?
4. **Evaluator cost:** each eval round = a spawned judge session (+ ensemble for high). Budget
   per decision? Does the cost justify the quality gain vs v1?
5. **The convergence threshold:** what score delta counts as "plateau"? Too tight → infinite
   loop; too loose → premature convergence (miss defects).
6. **Should the evaluator be model-invoked (a skill the architect loads) or a structural card
   (the architect creates an evaluator card per round)?** The structural-card approach fits
   the kanban_chains model better (durable, observable) — but adds cards/latency.
