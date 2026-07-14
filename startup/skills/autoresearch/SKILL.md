---
name: autoresearch
description: Autoresearch — improve → measure → keep if better, revert if worse → converge, against a metric. Use when the user wants to iterate a design, doc, code, or skill until it is good, mentions autoresearch or keep/discard improvement, or asks to refine something against a measurable quality signal.
---

# Autoresearch

Autoresearch is **improve → measure → keep/discard**, repeated until the artifact stops getting better. Each round you change the artifact, **measure** it against a **metric**, **keep** the change if the metric improved, **revert** it to the **best-so-far** if it regressed. The artifact improves monotonically — a bad round is undone, not accumulated. (Karpathy's `autoresearch`: edit `train.py`, measure `val_bpb`, keep the edit iff `val_bpb` fell.)

The technique stands or falls on one property of the metric.

## 1. Name the metric — ground truth or proxy?

A **ground-truth** metric is objective and unarguable (`val_bpb`, a test pass count, a mechanical tally). A **proxy** is a judgment that approximates quality (an LLM judge, a rubric score, a human rating). Name yours, and label which it is.

A ground-truth metric makes keep/discard infallible. A **proxy** is **gameable**, and the rest of this skill exists to defend against that. If the metric is a proxy, step 2 is mandatory.

*Done when:* the metric is defined, checkable, and labelled ground-truth or proxy.

## 2. For a proxy metric — build the held-out battery

A proxy **overfits**: the loop optimizes for the judge's taste, not real quality, and reports success while doing it. The defense is a **held-out battery** — a set of checks the improving agent never sees, run by an **independent** evaluator, not the agent that produced the artifact.

- **Disjoint.** Whatever the improving agent can read, the battery must not grade on; the battery grades only on what the agent cannot see.
- **Mechanical where possible** — counts, greps, pass/fail — to minimize the surface that is itself a judgment.
- **Structural fixes only.** When the proxy says *improved* but the battery does not pass, the proxy is overfit; fix it structurally (sharper anchors, more independence, an ensemble) and **re-qualify it blind** (it must flag a planted defect unaided before you trust it again). Tuning the proxy toward agreement with the battery *is* the overfitting.

*Done when:* the battery is disjoint from everything the improving agent sees, run independently, and the proxy is blind-qualified.

## 3. The loop

Each round:

1. **Improve.** Round 1 builds from research and perspectives; round 2+ targets the specific weaknesses the last measurement flagged.
2. **Measure.** Score the new version — the number for ground truth; the judge plus the battery for a proxy.
3. **Decide.**
   - **Improved** → **keep**; advance.
   - **Regressed** → **revert** to the **best-so-far**.
   - **Plateau** (the metric did not move across 2 rounds) → **converged**; ship the best-so-far.
   - **Max rounds** → **stop**; ship the best-so-far with its *residual risks*.

*Done when:* the round ended on a measurement-grounded keep/revert, and the best-so-far is updated or confirmed.

## 4. Ship the best-so-far

Convergence is the metric's call, not a feeling of done-ness. Ship the **best-so-far**, not the last round — a regressed last round does not ship. Stopped at max rounds without converging, the *residual risks* are the still-failing battery checks or the proxy's open flags; a plateau without a battery pass is escalation, not done.

*Done when:* the shipped artifact is the best-so-far, the convergence reason is recorded, and every residual gap is named, not hidden.

---

## In this repo

`design-council` is autoresearch applied to architecture decisions: the **proxy** is the evaluator rubric (`startup/profiles/architect/skills/architecture/design-council/references/evaluator-rubric.md`), the **held-out battery** is the runner-only defect set under `startup/profiles/verifier/secrets/`, and the **best-so-far** is the highest-scoring design-doc version.
