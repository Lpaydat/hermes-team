---
name: venture-prototype
description: "Build the right prototype type (HTML, API, CLI, or concierge) from grilled venture decisions. Includes POC gate for technical risks and standard README structure for founder review."
disable-model-invocation: true
---

# Venture Prototype

You've been grilled. Decisions are locked. Now build the prototype and write the README so the founder can review it in 5 minutes.

Load this skill AFTER self-grill completes and BEFORE completing the kanban card.

## Step 1 — Read the grill output

Read the grill decisions in `~/projects/<slug>/context/`. This is your spec — one file per branch, each with locked decisions and Q&A history. Every locked decision tells you what to build and what NOT to build.

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
Summary table: decision | lock value. Link to context/ directory
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

## Step 6 — Handoff for review

When the prototype + README are done, write the review handoff. Load the `prototype-review-handoff` skill — it owns the portfolio entry, kanban comment, and the "what to look at" pointer. Don't ad-hoc these.

## Pitfalls

- **Shallow grill output (fewer than 20 decisions).** If `~/projects/<slug>/context/` has only 2 decisions per branch, the grill was shallow. Root cause: the builder self-played both roles (wrote questions AND answers without launching PO). The grill is a dialogue — PO must actually run as a separate session and the builder must wait for each `<Q>` tagged question. If the PO session DB shows 0 `<Q>` tags, the grill was self-played and must be re-run. The original ec521103 self-grill with single CONTEXT.md produced 50+ questions; the branch-based approach fragmented it.
- **Defaulting to HTML for everything.** CrawlPay is middleware — a curl-able endpoint + traffic dashboard is more honest than a fake web app.
- **Skipping the README.** The portfolio entry is NOT a substitute — it's a summary, not a review surface.
- **Vague "How to Review".** "Try the demo" is useless. "Click the Sync Transactions button, then switch to the Review Queue tab" is useful.
- **Building a POC when the risk is market.** Don't prove the tech works when the question is whether anyone cares.
- **Re-grilling.** The grill already happened. Don't re-run it. Read the decisions and build.
- **Skipping loop_engine.** The builder self-assesses every build as "simple enough" to skip loop_engine. This is premature completion every time — proven in the July 24 E2E test. loop_engine is MANDATORY.

## Build with loop_engine (MANDATORY)

You MUST use `loop_engine` for every prototype build. No exceptions. Do NOT self-assess the build as "simple enough" to skip it — that's premature completion, and the E2E test proved the builder does this every time when left to choose.

loop_engine breaks the one-shot build into phased steps with an independent verifier gate between each phase. The verifier is a separate agent session that checks the work against the spec (the grill decisions in context/). This is the "don't trust the LLM" principle — same as Claude Code's verification loops. A dumb model with a better workflow outperforms a smart model with none.

### Phase 0 — Write verification script (BEFORE building)

Before calling loop_engine, write a temporary verification script at `/tmp/verify-<slug>.py` that checks the prototype against the grill decisions. This is your DoD in executable form.

Read every `Lock D` line from `~/projects/<slug>/context/*.md`. For each locked decision, write a check. Example:

```python
#!/usr/bin/env python3
"""Verify <slug> prototype against grill decisions in context/."""
import re, os, sys

context_dir = os.path.expanduser("~/projects/<slug>/context")
proto_dir = os.path.expanduser("~/projects/<slug>/prototype")
readme_path = os.path.expanduser("~/projects/<slug>/README.md")

# Parse locked decisions from context/
decisions = {}
for f in os.listdir(context_dir):
    if f == "_state.md": continue
    with open(os.path.join(context_dir, f)) as fh:
        for line in fh:
            m = re.match(r'Lock (D\d+):\s*(.+?)\s*=\s*(.+)', line)
            if m:
                decisions[m.group(1)] = (m.group(2).strip(), m.group(3).strip())

failures = []

# Check 1: Prototype exists
proto_files = os.listdir(proto_dir) if os.path.isdir(proto_dir) else []
if not proto_files:
    failures.append("No prototype files in prototype/")

# Check 2: README exists with required sections
required_sections = ["## What It Is", "## The Problem", "## Core Features",
                     "## How to Review", "## Grill Decisions", "## Riskiest Assumption",
                     "## How to Run", "## What Happens Next", "## Dossier"]
if os.path.exists(readme_path):
    readme = open(readme_path).read()
    for section in required_sections:
        if section not in readme:
            failures.append(f"README missing section: {section}")
else:
    failures.append("README.md does not exist")

# Check 3: Each decision is referenced in README
if os.path.exists(readme_path):
    readme_lower = readme.lower()
    for d_id, (title, value) in decisions.items():
        # At least the decision topic should appear somewhere
        keywords = title.lower().split()[:2]
        if not all(kw in readme_lower for kw in keywords):
            failures.append(f"Decision {d_id} ({title}) not reflected in README")

# Report
print(f"Decisions checked: {len(decisions)}")
print(f"Checks passed: {3 - len([f for f in failures if 'Check' in f])}")
print(f"Failures: {len(failures)}")
for f in failures:
    print(f"  FAIL: {f}")

sys.exit(1 if failures else 0)
```

This script IS the verifier's DoD. The verifier runs it. If exit code != 0, the phase replans.

### Phase 1 — Build prototype

```
loop_engine(
  goal: "Build <slug> prototype from context/ grill decisions",
  blackboard: {
    spec_path: "~/projects/<slug>/context/",
    extra: { "slug": "<slug>", "verify_script": "/tmp/verify-<slug>.py" }
  },
  phases: [
    {
      execution: {
        assignee: "builder",
        title: "Build prototype",
        body: "Read ~/projects/<slug>/context/*.md for locked decisions. Pick prototype type per skill rules. Build in ~/projects/<slug>/prototype/. Follow build rules: one command to run, simulated data, show aha moment."
      },
      verifier: {
        assignee: "builder",
        title: "Verify prototype against grill decisions",
        body: "Read ~/projects/<slug>/context/*.md. Check the prototype reflects every locked decision. Run: python3 /tmp/verify-<slug>.py. If exit != 0, the phase fails and must replan."
      },
      max_iterations: 2
    },
    {
      execution: {
        assignee: "builder",
        title: "Write README",
        body: "Write README.md at ~/projects/<slug>/README.md using the template from venture-prototype skill. Read context/ for grill decisions. Include specific click-by-click 'How to Review' steps."
      },
      verifier: {
        assignee: "builder",
        title: "Verify README completeness",
        body: "Run: python3 /tmp/verify-<slug>.py. Check all 9 sections exist. Check 'How to Review' has specific click instructions (not vague). Check every grill decision from context/ is referenced. If verify script fails, replan."
      },
      max_iterations: 2
    }
  ]
)
```

The verifier reads `~/projects/<slug>/context/*.md` as the spec and runs the verification script. This is NOT the builder self-reporting — it's an independent check that the prototype matches the locked decisions.

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
- **NEVER skip the grill validation gate.** If grill decisions are missing from `~/projects/<slug>/context/`, do NOT guess what the decisions were. Block with evidence or run `validate-grill-output.sh` first.
