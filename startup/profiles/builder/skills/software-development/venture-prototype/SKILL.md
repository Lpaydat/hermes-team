---
name: venture-prototype
description: "Build the right prototype type (HTML, API, CLI, or concierge) from grilled venture decisions. Includes POC gate for technical risks and standard README structure for founder review."
disable-model-invocation: true
---

# Venture Prototype

You've been grilled. Decisions are locked. Now build the prototype and write the README so the founder can review it in 5 minutes.

Load this skill AFTER self-grill completes and BEFORE completing the kanban card.

## Step 1 — Read the grill output

Read the grill decisions in `~/projects/<slug>/grill/`. This is your spec — one file per branch, each with locked decisions and Q&A history. Every locked decision tells you what to build and what NOT to build.

Also read the dossier at `~/vault/ventures/ideas/<slug>.md` for full context.

## Step 2 — POC Gate

Check the grill's riskiest assumption. Is it a "can we do X?" question (technical capability) or a "will people want X?" question (market/product)?

| Riskiest assumption type | Action |
|---|---|
| Technical capability ("Can LLM detect X with >Y% accuracy?") | Build POC first. If POC fails, block the card — no point prototyping. |
| Market/product ("Will people pay $39/mo for this?") | Skip POC. Go straight to prototype. |
| Both (technical AND market) | POC the technical risk first. Prototype after if POC passes. |

POC = a minimal test that answers ONE question. Output is a verdict (pass/fail with evidence), not a demo. Write `poc-result.md` in `~/projects/<slug>/prototype/`.

If POC is needed and fails: `kanban_block` with the evidence. Don't build a prototype on a dead assumption.

## Step 3 — Pick Prototype Type

Match the prototype medium to the product, not the other way around.

| Product type | Right prototype | Example |
|---|---|---|
| Web app / SaaS dashboard | Single-file HTML clickable demo | LeadPilot, LedgerLife |
| API / middleware | Working endpoint (Flask/FastAPI) + web dashboard showing it | CrawlPay, Scraper Micropayments |
| CLI / terminal tool | Runnable Python script with sample data + terminal output in README | Dockerless CI, FlowGuard |
| IDE plugin / MCP server | Architecture diagram + interaction walkthrough (HTML simulation or screenshots) | FlowGuard MCP |
| Concierge / manual service | Process doc + automation scripts + sample deliverables | LeadPilot phase 1 |

Default rule: if the product IS a web app, build HTML. If it's not, don't shoehorn it into HTML — build the real thing or a faithful simulation.

## Step 4 — Build

All prototypes go in: `~/projects/<slug>/prototype/`

### Build rules (all types)

1. **One command to run.** No build step, no dependencies beyond stdlib.
2. **Simulated/hardcoded data** — no real API calls, no database.
3. **Browser-test it** before completing. Zero JS errors if HTML.
4. **Show the aha moment** — the single interaction that makes the founder say "I get it."

### HTML prototype specifics
- Single `index.html`, zero dependencies, works by opening in browser
- Simulated data hardcoded in JS
- Dark theme, mobile-responsive

### API prototype specifics
- Single `app.py` (Flask/FastAPI), runs with `python app.py`
- 3-5 endpoints with sample request/response
- Include a simple HTML viewer that calls the API and shows results
- curl examples in README

### CLI prototype specifics
- Single `script.py`, runs with `python script.py`
- Sample input data included
- Terminal output captured in README (or as `output.txt`)
- If TUI: clear screen each frame, keyboard shortcuts at bottom

## Step 5 — Write README.md

README goes at: `~/projects/<slug>/README.md`

This is the founder's review surface. It must answer: what is this, why should I care, how do I test it, and what should I decide.

### Required sections

```markdown
# <Product Name> — Prototype

**Score:** X/25 | **Built:** YYYY-MM-DD | **Grill:** N decisions across M branches

## What It Is
One paragraph. What the product does, who it's for, the core insight.

## The Problem
2-3 sentences. What pain, who has it, what they do today instead.

## Core Features
Table or list. 3-7 features, each mapped to a pain point.

## How to Review
Step-by-step. Be specific — "Open index.html", "Click the Sync button",
"The aha moment is X". The founder should know exactly what to do.

## Grill Decisions
Summary table: decision | lock value. Link to grill/ directory
(one file per branch). Note any flaws PO caught and how they were corrected.

## Riskiest Assumption
The ONE thing that could kill this. Whether a POC was run and what it found.

## How to Run
One command. Tech stack in one line.

## What Happens Next
- "Fix X" → builder iterates
- "Promote this" → dispatches to PO
- "Shelve" → done

## Dossier
Link to `~/vault/ventures/ideas/<slug>.md`
```

## Step 6 — Verify Before Completing

- [ ] Prototype runs with one command
- [ ] README.md exists at `~/projects/<slug>/README.md` with all sections filled
- [ ] "How to Review" has specific click-by-click steps
- [ ] grill decisions exist in `~/projects/<slug>/grill/` (one file per branch)
- [ ] Portfolio updated with correct path to `~/projects/<slug>/prototype/`

## Pitfalls

- **Defaulting to HTML for everything.** CrawlPay is middleware — a curl-able endpoint + traffic dashboard is more honest than a fake web app.
- **Skipping the README.** The portfolio entry is NOT a substitute — it's a summary, not a review surface.
- **Vague "How to Review".** "Try the demo" is useless. "Click the Sync Transactions button, then switch to the Review Queue tab" is useful.
- **Building a POC when the risk is market.** Don't prove the tech works when the question is whether anyone cares.
- **Re-grilling.** The grill already happened. Don't re-run it. Read the decisions and build.

## Tools for quality and parallelism

**loop_engine** and **kanban_chains** are available. They are NOT tech-lead exclusive — a dumb model with a better workflow outperforms a smart model with none. Breaking a one-shot build into phased, verified steps gives ~30% quality boost (prevents drift from grill decisions, catches missing README before completion).

### When to use loop_engine (phased build with DoD gate)

Use for complex prototypes (API, CLI, multi-feature web app) or when the build card carries high-value ideas. Skip for simple single-file HTML demos.

**Phase structure for prototype build:**

```
loop_engine(
  goal: "Build <slug> prototype from grill decisions",
  phases: [
    {
      execution: { assignee: "builder", title: "Build prototype", body: "<build instructions>" },
      verifier: { assignee: "builder", title: "Verify prototype", body: "Check: prototype runs with one command? Zero JS errors? All grill decisions reflected? Aha moment is visible?" },
      max_iterations: 2
    },
    {
      execution: { assignee: "builder", title: "Write README", body: "<README template from this skill>" },
      verifier: { assignee: "builder", title: "Verify README", body: "Check: all 9 sections filled? How to Review has specific clicks? Grill decisions summarized? Correct paths?" },
      max_iterations: 2
    }
  ]
)
```

The verifier gate between phases prevents premature completion — the builder can't advance to README until the prototype passes its DoD check.

### When to use kanban_chains (parallel builds)

Use when building multiple prototypes in one session (batch mode) or when a single prototype has independent components.

**Batch pattern (build N prototypes concurrently):**

```
kanban_chains(
  goal: "Build N prototypes from grilled ideas",
  chains: [
    [{ assignee: "builder", title: "Build: <idea-1>", body: "..." }],
    [{ assignee: "builder", title: "Build: <idea-2>", body: "..." }],
    [{ assignee: "builder", title: "Build: <idea-3>", body: "..." }],
  ],
  after: [
    { assignee: "builder", title: "Update portfolio for all", body: "..." }
  ]
)
```

Concurrency is capped by `kanban.max_in_progress_per_profile` (default 3). Chains auto-queue when the cap is reached.

## NEVER

- **NEVER put prototypes in `~/vault/`.** That's the Obsidian vault. Prototypes go in `~/projects/<slug>/prototype/`.
- **NEVER skip the README.** It's mandatory for every prototype.
- **NEVER block the card during build.** The build card should run straight through to completion.
- **NEVER default to HTML for everything.** Match the prototype type to the product.
