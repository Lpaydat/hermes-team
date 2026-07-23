# Venture Prototype vs Matt Pocock's Prototype

## Why we need a separate skill

Matt Pocock's `prototype` skill (in `shared-skills/mattpocock/prototype/`) is designed for **in-codebase technical prototyping** — answering questions like "does this state model feel right?" or "what should this page look like?" within an existing project repo.

Our venture pipeline needs something fundamentally different: **standalone venture concept demos** built from grilled decisions, presented to a non-technical founder for promote/fix/shelve review.

## Comparison

| Aspect | Matt Pocock `prototype` | Our `venture-prototype` |
|--------|------------------------|------------------------|
| Context | Inside an existing codebase | Standalone, no existing repo |
| Question | "Does this logic/UI feel right?" | "What would this product feel like?" |
| Output | TUI or UI variants on a route | HTML demo / API endpoint / CLI script |
| Audience | Developer working on the code | Founder reviewing for promotion |
| Documentation | NOTES.md (optional, AFK) | README.md (mandatory, structured) |
| Decisions | Captured in commit/ADR | Captured in grill-decisions.md |
| Data | In-memory, no persistence | Simulated/hardcoded |

## Key differences in practice

1. **No existing codebase.** Matt's skill assumes routing conventions, task runners, component libraries. Our prototypes start from nothing — single-file HTML or standalone Python.

2. **Founder is the audience, not a developer.** Matt's prototype is for the dev to feel out a design. Ours is for a founder to decide whether to invest in production. The README is the review surface — it must communicate the vision, not the implementation.

3. **Prototypes come from grills, not from code questions.** Our prototypes are downstream of a structured design grill (self-grill skill) that locks 5-15 decisions across multiple branches. Matt's prototypes start from a loose question.

4. **Prototype type varies.** Matt defaults to TUI (logic) or UI variants (visual). We need HTML demos, API endpoints, CLI scripts, or concierge process docs depending on the product.

## What to use when

- **Use Matt Pocock's `prototype`** when working inside a codebase on a specific design question (developer, tech-lead contexts).
- **Use our `venture-prototype`** when building a standalone demo from grilled venture decisions for founder review (builder pipeline context).

## Research basis

Searched skills.sh (2026-07-24) for "prototype demo", "product prototype", "venture prototype", "clickable demo", "readme generator" — none matched our use case. The closest was `product-on-purpose/pm-skills@tool-design-sprint-prototype-plan` (351 installs) but it's about planning a Design Sprint Thursday, not building/presenting a venture prototype.
