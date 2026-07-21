# Stage 4 — Design project spec

Disclosed detail for the Design Spec stage. Reached from [SKILL.md](../SKILL.md).

For survivors that pass deep dive, author the build-ready spec. This is the handoff
document. Use `templates/project-spec.md` as the required template.

## Tool for MVP scope decisions

- **`mvp-scoping`** — MoSCoW prioritization (Must/Should/Could/Won't) to distill a full
  feature vision down to the smallest version worth building. Produces a scope document with
  explicit inclusions, exclusions, and success criteria. Use when deciding what makes the cut
  for the prototype.

## The spec MUST include

- Problem statement (one paragraph).
- Target audience / ICP (specific, not "everyone").
- Riskiest leap-of-faith assumption (stated as a falsifiable hypothesis).
- Lean-canvas summary (filled template).
- Recommended MVP experiment type (smoke test, concierge, single-feature, etc.).
- Recommended tech stack for the prototype (see `templates/tech-stack-recommendations.md`).
- Validation/kill metric (threshold defined before building).
- Pivot/kill criteria (pre-committed).

## Confidence labels — and the gate they enforce

Every claim in the spec must be labeled per the spine's confidence rule
([Analysis] / [Judgment] / [Speculation]) — see "Confidence & honesty" in
[SKILL.md](../SKILL.md). The labels calibrate the gate's trust.

**Spec-gate rule (enforced).** Before authoring the build-ready spec, the **riskiest
assumption** must be labeled **[Analysis]** — i.e. backed by demand-side evidence (organic
complaints, negative-feature reviews, interview quotes, willingness-to-pay signal), not
[Judgment] or [Speculation]. A spec whose core assumption is still [Judgment] is a paper
spec on top of an untested inference; do not author it. Instead, run the cheapest demand pass
that converts the label (targeted community-scan for gap language, negative-feature reviews on
the comp set's G2/Capterra pages, or a single ICP interview) and either promote the label to
[Analysis] or kill the idea. OnCallDigest (grilllive13) was killed at exactly this gate by
product-owner: the brief's gap was [Judgment], a spec was authored anyway, and the demand pass
landed zero organic complaints + an incumbent already shipping the thesis for free. Do not
repeat that loop — if the core assumption is [Judgment], run the pass yourself before the spec
reaches product-owner's queue.

The spec-gate rule only constrains the **riskiest** assumption. Secondary assumptions may
remain [Judgment] or [Speculation] and be tested later via the experiment design — that is
what the MVP is for.
