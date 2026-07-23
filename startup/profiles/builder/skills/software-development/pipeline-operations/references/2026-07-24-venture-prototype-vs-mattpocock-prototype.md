# Venture Prototype vs Matt Pocock's Prototype Skill

## Comparison (2026-07-24)

Matt Pocock's `prototype` skill (in `shared-skills/mattpocock/prototype/`) was reviewed for fit with our venture pipeline. **Verdict: does NOT match our needs.**

### Matt Pocock's prototype skill is for:
- In-codebase prototyping within an existing repo
- Two branches: LOGIC (terminal TUI for state machines) vs UI (multiple variants on an existing route with floating switcher)
- A developer exploring "does this state model feel right?" or "what should this look like?"
- Decisions captured via commit messages, ADRs, NOTES.md
- Anti-patterns: no tests, no persistence, no generalization

### Our venture pipeline prototypes are:
- Standalone single-file HTML clickable demos (no existing repo, no task runner, no routing)
- Prove a business concept/value narrative, not a technical implementation detail
- Must communicate problem, features, and aha-moment to a non-technical founder for review
- Require a README as a review surface for promote/fix/shelve decisions
- Come out of a grill process that locks design decisions (7-15 decisions across 5-12 branches)
- All data is simulated/hardcoded — no backend

### What we need instead: a venture-prototype skill

The builder needs a skill that covers:
1. **Build approach**: single-file HTML/CSS/JS demos with simulated data
2. **README structure** (the review surface for the founder):
   - What It Is (one paragraph)
   - The Problem (pain, who has it, what they do today)
   - Core Features (3-7, each mapped to a pain point)
   - How to Review (step-by-step: open this, click that, try this)
   - Grill Decisions (summary table, link to grill-decisions.md)
   - Riskiest Assumption (the one thing that kills it if wrong)
   - What Happens Next (fix / promote / shelve)
   - Dossier link
3. **Quality bar**: every prototype ships with index.html + README.md + grill-decisions.md

### E2E test evidence
From the 10-card E2E test (2026-07-24):
- Only 2/10 prototypes had READMEs (LeadPilot, OSINT Desk — the first two built)
- The other 8 had grill-decisions.md but no README
- Portfolio entries had rich descriptions but in table-cell format, not README format
- The queue-builds.sh card body now requires README.md

### Status
Skill not yet created. User asked to research the structure first. The proposed README structure above is the draft — awaiting user confirmation before creating the skill.
