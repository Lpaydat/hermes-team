---
name: builder-prototype-workflow
description: Use when building ANY prototype from grilled decisions — load venture-prototype skill FIRST, follow all 6 steps, never skip README or loop_engine. Enforces the mandatory workflow that the pinned venture-prototype skill defines but cannot be modified to emphasize.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [prototype, workflow, venture-prototype, builder, mandatory]
    related_skills: [venture-prototype, prototype-verification, prototype-review-handoff]
---

# Builder Prototype Workflow

**CRITICAL: Load this skill or venture-prototype BEFORE starting ANY prototype build.**

The venture-prototype skill is PINNED and cannot be modified, but it contains the definitive workflow. This skill exists to enforce the mandatory steps because builders frequently skip them when working directly from task descriptions without loading the skill.

## The Mandatory 6-Step Workflow

**DO NOT start building until you have loaded `venture-prototype`.**

```
skill_view(name='venture-prototype')
```

Then follow ALL 6 steps in order:

1. **Read the grill output** — `~/projects/<slug>/context/*.md`
2. **POC Gate** — Check if risk is technical or market. If technical, run POC first.
3. **Pick prototype type** — Match medium to product (HTML/API/CLI/concierge)
4. **Build** — Use loop_engine with verification phases. One command to run.
5. **Write README.md** — MANDATORY. 9 required sections. Never skip.
6. **Handoff for review** — Load prototype-review-handoff skill and follow it.

## What Goes Wrong Without Loading the Skill

When a builder does NOT load venture-prototype before starting, they consistently violate the workflow:

### Violation 1: Skipping README.md
- **What happens:** Builder creates `index.html` and calls `kanban_complete` immediately.
- **Why:** The builder thinks "this is simple HTML, no README needed"
- **Reality:** README is MANDATORY for ALL prototype types. It's the founder's review surface.
- **Real example:** 2026-08-01 — LeadPilot prototype (t_98e98531) completed with only index.html, no README.md.

### Violation 2: Skipping loop_engine
- **What happens:** Builder builds in one shot without phased verification.
- **Why:** The builder self-assesses "this is simple enough to skip loop_engine"
- **Reality:** loop_engine is MANDATORY for ALL builds. It prevents drift and premature completion.
- **Evidence:** Proven in July 24 E2E test — builder skipped loop_engine on 15/15 prototypes across 2 batches.

### Violation 3: Skipping the review handoff
- **What happens:** Builder calls `kanban_complete` without loading prototype-review-handoff.
- **Why:** The task description says "build the prototype" and builder stops there.
- **Reality:** The pipeline includes handoff — portfolio entry, kanban comment, review pointer.

### Violation 4: Wrong prototype type selection
- **What happens:** Builder defaults to HTML for everything.
- **Why:** HTML is the path of least resistance.
- **Reality:** Match medium to product. API → Flask/FastAPI, CLI → Python script, concierge → process doc + scripts.
- **Real example:** CrawlPay is middleware — a curl-able endpoint is more honest than a fake web app.

## Detection Pattern

A prototype was built WITHOUT loading venture-prototype if:
- Only the prototype file exists (no README.md)
- Kanban completion happened without loop_engine phases
- No review handoff was written
- Builder went straight from "read context/" to "write prototype file"

## The Correct Starting Pattern

```python
# ALWAYS start with this:
skill_view(name='venture-prototype')

# THEN read the grill decisions:
read_file('~/projects/<slug>/context/_state.md')
read_file('~/projects/<slug>/context/riskiest-assumption-&-pricing.md')
# ... read all branch files

# THEN proceed with the skill's steps
```

## Why Loading the Skill Matters

The skill is not optional scaffolding — it's the workflow definition. When you load it:

1. **You see the POC gate** — you don't waste time on technical POCs when the risk is market
2. **You see the build rules** — one command, no deps, simulated data, show aha moment
3. **You see loop_engine is MANDATORY** — you don't self-assess exemption
4. **You see README is MANDATORY** — you don't skip it for "simple HTML"
5. **You see the handoff requirement** — you don't stop at the prototype file
6. **You see the pitfalls** — you avoid the 15+ documented failure modes

## Common Excuses and Why They're Wrong

| Excuse | Reality |
|--------|---------|
| "This is just HTML, I don't need a README" | README is mandatory for ALL types. Founder review surface. |
| "This is simple, I'll skip loop_engine" | loop_engine is MANDATORY. Proven failure mode 15/15 times. |
| "The task just says 'build the prototype'" | The pipeline includes 6 steps, not just the file. |
| "I'll write the README after I complete" | README is part of the build — don't call kanban_complete without it. |
| "I know this workflow already" | If you know it, loading the skill takes 5 seconds and confirms you're following it. |

## Completion Criteria

A prototype build is NOT complete until ALL of these exist and pass verification:

1. **Prototype file** (`index.html` or `app.py` or `script.py` etc.)
2. **README.md** with all 9 sections (What It Is, Problem, Features, How to Review, Grill Decisions, Riskiest Assumption, How to Run, What Happens Next, Dossier)
3. **Verification script** (`/tmp/verify-<slug>.py`) with 20+ checks across 4-5 categories
4. **Verification passed** (`python3 /tmp/verify-<slug>.py` exits 0)
5. **Review handoff written** (via prototype-review-handoff skill)
6. **Kanban complete** (only after 1-5 are done)

## When to Use This Skill

Load this skill when:
- You receive ANY "Build: <idea>" kanban card
- The task says "build a prototype" or "create a demo"
- You're about to read `context/` files and start building

**Do NOT use this skill for:**
- Grilling ideas (use self-grill)
- Reviewing prototypes (use prototype-verification)
- Promoting to production (use project-promotion)
- Iterating on feedback (use prototype-iteration)

## Related Skills

- **venture-prototype** — The definitive workflow (PINNED, cannot be modified)
- **prototype-verification** — Independent verification guidelines
- **prototype-review-handoff** — Handoff writing instructions
- **self-grill** — Grilling ideas before building

## References

See venture-prototype skill for full details:
- `venture-prototype/references/verify-script-template.md` — Verification script template
- `venture-prototype/references/2026-07-24-e2e-lessons-poc-and-loop-engine.md` — E2E lessons

## Common Pitfalls

- **Starting to build without loading venture-prototype.** This is the #1 cause of workflow violations. Load the skill FIRST.
- **Thinking "I know the workflow" and skipping skill load.** Loading the skill takes 5 seconds and confirms you're following it correctly.
- **Treating the README as optional for HTML prototypes.** README is mandatory for ALL prototype types.
- **Self-assessing loop_engine exemption.** loop_engine is MANDATORY. The "simple enough" exemption has failed 15/15 times.
- **Calling kanban_complete before the review handoff.** The handoff is part of the build — don't skip it.
- **Defaulting to HTML for all prototypes.** Match the medium to the product type.
