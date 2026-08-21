---
name: ui-design
description: "Use when you receive a [design] or [design-visual] card. Drives the design protocol: choose the component system from tech-preferences, write the UI spec with wireframes and ALL states, derive design-tokens.json, build offline-renderable HTML mockups, and verify with Playwright screenshots. Design conformance checks the built app against the approved design."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [design, ux, ui, wireframes, tokens, mockups, playwright, design-gate]
---

# UI Design — the design protocol v1.0

You produce designs that are **checkable**, not decorative. Every artifact you
write is later verified — by an adversarial reviewer, by Playwright
screenshots, and after build by design conformance. Prose claims get proven
with rendered pixels.

The four layers, in order — each constrains the next:

1. **Component system** (choice): read `~/.hermes-teams/startup/tech-preferences.json`.
   Match the architect's tech stack (React → shadcn/ui, Svelte → shadcn-svelte,
   etc.; Tailwind is the styling base). Record choice + one-line why in the
   UI spec. Never invent a bespoke system when a preferred one fits.
2. **UI spec + wireframes** (`docs/ui-spec.md`): every screen with ASCII or
   mermaid wireframes. For EVERY screen design the **empty state**, **error
   state**, and **loading state** (if async) — a screen with only a happy path
   is an incomplete screen and the review will fail it. Include user flows and
   a two-way traceability table: user story ↔ screen.
3. **Design tokens** (`design-tokens.json`, repo root): colors, spacing scale,
   type scale, radii. Mostly INHERITED from the chosen system; customize only
   what the spec demands. Tokens are a build constraint — the app inherits them.
4. **HTML mockups** (`docs/mockups/<screen>.html`): static HTML per screen,
   styled with inline styles derived STRICTLY from `design-tokens.json` (the
   real components arrive at build time). Then screenshot each with Playwright
   to `docs/mockups/<screen>.png` — a mockup that does not render is a failed
   mockup. Playwright is local and headless; no browser API keys needed:
   `python -m playwright screenshot <file.html> <out.png>` (or the Node
   equivalent). If Playwright is missing, install it in the workspace:
   `pip install playwright && playwright install chromium`.

## What adversarial review will check you on

- State coverage (empty/error/loading per screen)
- A11y basics: WCAG AA text contrast, focus order described, text alternatives,
  semantic headings
- Consistency: mockup styles actually derive from the tokens; tokens from the system
- Traceability: every user story has a screen; no orphan screens

## Design conformance ([design-visual] cards)

After build: screenshot the RUNNING app's screens, check structurally (never
pixel-diff — flaky): screen exists and serves its purpose, error state
reachable, colors derive from tokens. File findings like QA findings.

## Hard rules

- Never complete a `[design-done]` gate card — that belongs to design-close.
- Never design in your head only: artifacts land in the repo, always.
- A spec without states is not a spec. A mockup without a screenshot is not a
  mockup.
