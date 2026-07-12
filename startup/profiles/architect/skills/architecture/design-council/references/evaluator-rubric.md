# Design-Council Evaluator Rubric (v2)

> The evaluator is the crux of v2. It replaces the architect's self-confidence
> with an **independent judgment** scored across five dimensions. autoresearch
> measures `val_bpb` (objective ground truth); design quality is **subjective**,
> so the rubric is the only thing standing between a real defect and a shipped
> "benefit." Every criterion below is **concrete and checkable** — "does it name
> PgBouncer?" not "is the scaling adequate?" — so the judge can be held to it.

## The five dimensions

Each dimension is scored **1–5** against explicit anchors. A score of 3 is
"adequate"; 4 is "strong, minor gaps"; 5 is "exceptional, a senior reviewer
would not flag it." Scores must be **grounded**: every score ≤ 4 carries at
least one `flagged_weakness` citing the specific ADR/design-doc passage.

---

### 1. Correctness — does it contain technical errors?

The proxy_cache class: a claim or mechanism that is *technically wrong*, not
merely shallow. The v1 review shipped a 302-caching defect as a benefit.

**Anchors:**
- **5.** Every mechanism described (caching, pooling, auth, retry, queueing) is
  *technically accurate*. Rate-limiting algorithms named by their actual
  semantics (token bucket vs leaky bucket vs sliding window). Cache-key
  composition and invalidation paths are explicit and correct. No conflations.
- **3.** Mechanisms are mostly right but at least one is vague enough to hide an
  error (e.g. "we'll cache aggressively" without naming what or for how long).
- **1.** A core mechanism is *technically wrong* (e.g. asserting nginx
  `proxy_cache` transparently skips 302s, or conflating token/leaky bucket).
  Any such finding → this dimension caps at 2 and is tagged a **critical flag**.

**Check for:** algorithm/conflation errors, wrong tool for the job stated as
right, security assumptions that don't hold (e.g. "OS user boundary" over a
network socket), data-loss paths presented as safe.

---

### 2. Depth — are the hard sections deep enough?

The scaling-analysis class: the #1 operational pain gets one generic sentence.

**Anchors:**
- **5.** The section that matters most (scaling, isolation, durability, or
  cost) names the *specific mechanism* — e.g. "PgBouncer transaction-mode
  pooling: ~100 backend conns per PgBouncer, ~50–100 tenants per pool, so
  ~10 PgBouncer instances per 1000 tenants" — and traces the cost/limit at
  that scale.
- **3.** The hard section says the right category ("connection pooling") but
  does not name a specific tool, the pool size economics, or the per-tenant
  boundary.
- **1.** The hard section is hand-waved ("we can scale horizontally") with no
  mechanism, no bottleneck named, no cost envelope.

**Check for:** sections where the stakes are highest but the depth is lowest
(inverted depth-to-stakes ratio). The evaluator should flag *the gap between
where depth was spent and where stakes live*.

---

### 3. Alternatives weighed — are the options real and steelmanned?

The strawman class: "Option A vs do nothing" or alternatives weakened so the
chosen one wins.

**Anchors:**
- **5.** ≥2 genuine alternatives are presented, each in its *steelman* form
  (the strongest version of that option), with a stated trade-off (cost /
  complexity / reversibility) that is the *actual* reason to reject it. The
  chosen option wins on a named dimension, not by default.
- **3.** Alternatives exist but at least one is a strawman (weakened,
  mis-named, or missing its real advantage). The rejection reason is generic.
- **1.** One alternative is "do nothing" or "status quo," or alternatives are
  absent.

**Check for:** false dichotomies, an alternative rejected for a reason that
also applies to the chosen option, or the chosen option never compared on the
dimension where an alternative is actually stronger.

---

### 4. Edge cases & failure semantics — what breaks and what happens then?

The write-failure / operational class: happy-path design with silent failure
paths.

**Anchors:**
- **5.** The design names the failure modes that *will* occur (process crash,
  socket death, partial write, timeout, duplicate delivery, restart-mid-op)
  and states the *semantics* for each: what the system does, what the caller
  observes, what is lost vs recovered. Failure semantics are *explicit*, not
  "it handles errors."
- **3.** Some failure paths acknowledged but at least one material one is
  unstated (e.g. in-memory queue + no mention of broker-crash loss).
- **1.** Happy-path only; failure modes are unaddressed or dismissed.

**Check for:** the operational realities of the chosen architecture — if it's
in-memory, is data loss acknowledged? If it's fire-and-forget, is the
no-delivery-receipt semantic stated? If it spawns sessions, what happens if the
spawn fails?

---

### 5. Consequences — are risks (positive, negative, residual) covered?

The ADR Consequences section quality.

**Anchors:**
- **5.** Consequences name both the positive and negative outcomes, *plus*
  residual risks (what we accept but don't fully resolve). The negative
  consequences include the *cost* (cards spawned, tokens, latency, maintenance
  burden), not just the abstract downside. Open questions are named, not
  hidden.
- **3.** Positive and negative covered, but no residual-risks section, or the
  costs are vague ("more cards") without a number.
- **1.** Consequences are one-sided (positive only) or absent.

**Check for:** hidden trade-offs, missing cost numbers, open questions buried
in prose rather than surfaced.

---

## Output schema

The evaluator returns this structure. It is the **iteration signal** — the
architect acts on it the way autoresearch acts on `val_bpb`.

```json
{
  "round": <N>,
  "design_version": "<slug of the design-doc version evaluated>",
  "dimension_scores": {
    "correctness": <1-5>,
    "depth": <1-5>,
    "alternatives": <1-5>,
    "edge_cases": <1-5>,
    "consequences": <1-5>
  },
  "overall": <float, mean of the five>,
  "delta_vs_last": <float, overall_N minus overall_{N-1}; null on round 1>,
  "flagged_weaknesses": [
    {
      "dimension": "correctness | depth | alternatives | edge_cases | consequences",
      "issue": "<one-sentence description of the specific gap>",
      "severity": "critical | important | minor",
      "citation": "<quote or §-reference of the exact ADR/design passage>"
    }
  ],
  "verdict": "improve | converged | regressed",
  "notes": "<optional: judge's one-line overall impression>"
}
```

### Verdict logic (the judge applies this, not the architect)

- **critical flag present** → verdict is `improve` regardless of score (a
  technical error must be fixed before convergence).
- **overall ≥ 4.0 AND zero critical/important flags** → eligible for `converged`.
- **delta_vs_last ≥ +0.3** → `improve` (meaningful progress; another round will
  help).
- **delta_vs_last < plateau_threshold for 2 consecutive rounds** → `converged`
  (diminishing returns; further rounds chase noise).
- **delta_vs_last < 0** → `regressed` (the round made it worse; revert via
  keep/discard).

### Severity calibration

| Severity | Meaning | Action |
|---|---|---|
| **critical** | A technical error or a missing core mechanism (correctness ≤ 2 or a hard section at depth 1). | Must fix before the ADR. Blocks convergence. |
| **important** | A real gap that a competent reviewer would flag (shallow depth, strawman, unstated failure path). | Should fix this round. |
| **minor** | A polish-level gap (vague cost number, a residual risk that could be more explicit). | Note it; may converge with it outstanding. |

The **noise floor**: minor-severity flags alone do not block convergence. A
design with only minor flags and overall ≥ 4.0 converges. This prevents the
loop from chasing subjective noise — the failure mode the plan warns about.

---

## The judge

### Who evaluates

| Stakes | Judge | Rationale |
|---|---|---|
| **Low** | *None* — 1 round, no evaluator. | A throwaway doesn't justify the cost; the floor (research + 1 peer) is the quality floor. |
| **Standard** | **Single judge** — the `verifier` profile (independent context, adversarial stance is native). | One competent independent reviewer catches the proxy_cache-class defects. Cost is bounded. |
| **High** | **Ensemble of 3** — the `verifier` profile runs 3 independent evaluator cards; scores are averaged, flags are unioned, convergence requires ensemble agreement (no critical-flag disagreement). | Individual LLM judges have bias and drift. Averaging reduces variance; requiring agreement on critical flags prevents a single judge's false positive from blocking convergence or a false negative from shipping a defect. |

### Independence (non-negotiable)

The judge **must not** be the architect who synthesized the round. The
verifier profile is a separate spawned session with a clean context window —
it sees only the design doc and this rubric, never the architect's reasoning
trace. This is the same maker/checker separation that makes code verification
meaningful: the evaluator who can grade the design must not be the agent who
wrote it.

### Grounded output

Every flag cites the specific passage. "The scaling analysis is shallow" is
**not** a valid flag. "§ Consequences: 'we can scale horizontally' — names no
pooling tool, no tenant-per-pool ratio, no cost at 1000 tenants; depth score
2" **is**. Unanchored flags are treated as noise and discarded by the
architect on resume.

---

## Mitigations for the subjective-metric risk

The plan's crucial challenge: autoresearch's `val_bpb` is infallible; this
evaluator is a proxy. Three mitigations, in priority order:

1. **Concrete anchors** (above) — the rubric replaces "is it good?" with
   "does it name PgBouncer?" The judge is graded on the same checklist as the
   design.
2. **Grounded citations** — unanchored flags are noise. This forces the judge
   to engage with the actual text, not generate plausible-sounding critique.
3. **Ensemble for high-stakes** — averaging + agreement-on-critical reduces
   individual judge bias and drift. The cost (3× evaluator spawns) is paid
   only at high stakes where a missed defect is most expensive.

The **noise-floor threshold** (minor flags don't block convergence) is the
fourth mitigation, applied by the verdict logic: it stops the loop from
optimizing for the judge's taste instead of real quality.

---

## Integration with the loop

The architect creates an **evaluator card** (kanban_chains worker or
kanban_create) after each synthesis round. The card body contains: the design
doc / ADR draft, this rubric (by reference), and "score across the five
dimensions; return the output schema; cite every flag." The architect parks
until the evaluator completes, then reads the verdict and acts:

- `improve` → run a targeted improvement round on the flagged weaknesses.
- `converged` → write the final ADR (citing the evaluator's verdict).
- `regressed` → discard this round's changes (keep/discard mechanic).

See `call-templates.md` § "Evaluator card" and § "High-stakes ensemble" for
the exact topology.
