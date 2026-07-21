# Stage 2 — Filter & rank

Disclosed detail for the Filter & Rank stage. Reached from [SKILL.md](../SKILL.md).

Score every signal on five dimensions. Cut anything that doesn't pass the bar.

## Scoring rubric (1–5 each, max 25)

| Dimension | 1 | 3 | 5 |
|-----------|---|---|---|
| **Pain intensity** | Mild annoyance | Real frustration | Urgent, costly pain |
| **Frequency** | One-off complaint | Recurring across a few sources | Pervasive, repeated everywhere |
| **Willingness-to-pay evidence** | None | Indirect (hated paid solutions) | Direct ("I'd pay", existing spend) |
| **Competition density** | Saturated (many strong solutions) | Some players but gaps | Wide open / incumbents are weak |
| **"Why now"** | No timing advantage | Moderate timing case | Strong window (new tech, regulation, behavior shift) |

## Cut rules

- Total score < 15 → **CUT**. No exceptions.
- Pain intensity ≤ 2 → **CUT**. (Mild annoyance rarely sustains a venture.)
- No willingness-to-pay path at all → **CUT**. (Even if the pain is real, no revenue = no
  venture.)
- No "why now" → **CUT**. A timeless problem with no new angle means incumbents have
  already solved it.

Record cut ideas with a one-line reason in `~/vault/killed-ideas.md`.

## Output

A shortlist of survivors with scores and rationale. Typically 10% of raw signals survive.
