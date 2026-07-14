---
name: brownfield-intake
description: One-time adoption flow for an existing codebase - a single as-is inventory card maps the de-facto architecture with the design skills, writes ADR-000-series retro-ADRs (status quo - accepted, not endorsed) into the venture's docs/adr/, files known debt as beads in the venture's own tracker, and completes with structured metadata. Use when adopting a brownfield venture that has code but no ADR baseline.
---

# Brownfield Intake — as-is inventory to retro-ADRs

When the team adopts an existing codebase, the funnel needs a baseline to
govern changes against. This skill is that baseline's production line: **one
inventory card** turns the de-facto architecture into retro-ADRs and debt
beads, and from then on the normal gates apply.

This is an **inventory, not an audit**. You are recording what IS, with
evidence, so later decisions have something to cite and diff against. You are
not judging the code, not fixing it, and not redesigning it.

## Bounding rule (hard)

- **3–5 retro-ADRs per intake.** Only decisions that shape the architecture:
  module boundaries, data/storage shapes, bundled-vs-fetched data, provider
  seams, persistence formats. If you found more than five, you are auditing —
  merge or drop the smallest.
- **2–4 debt beads per intake.** Small, concrete, actionable items. Debt goes
  to the tracker, never into the ADRs.
- One pass, then complete the card. No follow-up inventory cards unless a
  human asks.

## The flow

### 1. Map the de-facto architecture

Read the venture's spec (`docs/specs/`) first, then map the code with the
design skills you already carry — `codebase-design` (modules, interfaces,
seams, depth) and `domain-modeling` (the venture's ubiquitous language).
The inventory is **read-only apart from `docs/adr/`**: no code edits, no test
edits, no config edits. The venture's test suite must pass identically before
and after intake.

### 2. Write retro-ADRs (the ADR-000 series)

Retro-ADRs follow `docs/agents/adr-convention.md` (template, append-only,
citations) with the brownfield deltas below. Write them into the venture
repo's `docs/adr/` (create the directory if missing).

**Status.** The status line is exactly:

```
- Status: Accepted (status quo — accepted, not endorsed)
```

Baseline means *accepted as the operative state*, not *endorsed as the right
design*. An architect signing a retro-ADR is acknowledging reality, not
approving it; misgivings belong in Consequences and in debt beads.

**Numbering — the ADR-000 series.** Retro-ADRs use a distinct series so the
baseline is visually separate from decided-forward ADRs:

```
docs/adr/ADR-000.1-<slug>.md
docs/adr/ADR-000.2-<slug>.md
...
```

- The series lives entirely inside the `ADR-000.` prefix; sub-numbers
  increase monotonically and are never reused.
- Normal forward ADRs still start at `ADR-001` — the first *decided* change
  after adoption takes `ADR-001` regardless of how many retro-ADRs exist.
- The series is closed after intake: new decisions are forward ADRs. A
  forward ADR that replaces baseline behaviour supersedes the retro-ADR the
  normal way (`Supersedes: ADR-000.N` header + `bd supersede` on the beads).

**Header.** `Introduced-by:` carries the inventory card/bead id — the intake
card is the architecture ticket that produced the baseline.

**Citations — evidence from the code itself.** A retro-ADR documents a
decision nobody wrote down, so the primary sources are the code and the
venture spec. Code citations are valid sources for retro-ADRs: named source =
the file with a line number (file:line), quotable line = the decisive line of
code or comment. The venture spec is cited the same way as any doc source.

```markdown
## Citations
- code `plantcare/override_store.py:41` — "merged = {**defaults, **overrides}"
- spec `docs/specs/mvp-slice.md` — "bundled JSON dataset, no network call"
```

Every retro-ADR cites at least one code location (file:line). The quotable
line is ALWAYS wrapped in straight double quotes — even when it quotes code.
Backticks wrap the named source only, never the quotable line: write
`- code` `` `file.py:41` `` `— "the quoted code line"`. A citation whose
quote sits in backticks does not parse as a citation. Uncited baseline
claims do not enter a retro-ADR — same rule as forward ADRs.

### 3. File debt beads — in the venture's own tracker

Known debt, risks, and misgivings surfaced by the inventory become beads in
the **venture's own tracker** (run `bd` from the venture repo root — bd
resolves the workspace by cwd; ids carry the venture's own prefix). Never
file venture debt in the HQ/root tracker. 2–4 beads, each small and concrete
(one risk or one fix per bead), each traceable to a retro-ADR or a file:line.

### 4. Commit the baseline

Commit **only** `docs/adr/` in the venture repo with a clear message, e.g.:

```
docs(adr): brownfield intake — retro-ADR baseline (ADR-000 series)
```

### 5. Complete the card with metadata

Complete the inventory card with:

- **metadata** listing the retro-ADR numbers and the debt bead ids:

  ```json
  {"retro_adrs": ["ADR-000.1", "ADR-000.2", "ADR-000.3"],
   "debt_beads": ["<venture-prefix>-abc", "<venture-prefix>-def"]}
  ```

- **summary**: a short inventory summary that links every debt bead by id and
  names what the retro-ADR set covers.

## After intake

Later gates, verifier lenses, and forward ADRs cite retro-ADRs **exactly like
normal ADRs** (`ADR-000.2` is as citable as `ADR-002`); the baseline is a
first-class part of the ADR record. The append-only rule applies unchanged:
a retro-ADR is never edited — changing baseline behaviour means a forward ADR
that supersedes it.
