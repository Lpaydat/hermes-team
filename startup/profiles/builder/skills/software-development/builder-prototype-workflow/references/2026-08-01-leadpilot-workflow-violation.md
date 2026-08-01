# 2026-08-01: LeadPilot Prototype Workflow Violation

## Task

`t_98e98531` — "Build LeadPilot prototype (Phase 1): Create single-file HTML dashboard at ~/projects/leadpilot-ai-local-smb-lead-gen/prototype/index.html reflecting all 40 grill decisions from context/."

## What Actually Happened

The builder completed the task in a single session without loading the `venture-prototype` skill:

1. ✅ Read grill decisions from `context/` (8 branch files, 40 total decisions)
2. ✅ Created `index.html` (32KB, 939 lines, all 40 decisions reflected)
3. ✅ Called `kanban_complete` with the HTML file as artifact
4. ❌ **SKIPPED** README.md (no README.md was created)
5. ❌ **SKIPPED** loop_engine (build happened in one shot without phased verification)
6. ❌ **SKIPPED** review handoff (prototype-review-handoff skill was never loaded)

## The Correct Workflow (What Should Have Happened)

According to `venture-prototype` skill (Step 1-6):

1. **Read the grill output** ✅ Done
2. **POC Gate** — Check if risk is technical or market
   - Riskiest assumption: "the plumber can ATTRIBUTE calls to LeadPilot"
   - This is a market/product assumption (not technical)
   - **Result:** Skip POC, go straight to prototype ✅ Correct
3. **Pick prototype type**
   - Product: Web app dashboard (LeadPilot Report, funnels, pricing)
   - **Result:** Single-file HTML ✅ Correct
4. **Build with loop_engine** ❌ SKIPPED
   - Should have written `/tmp/verify-leadpilot-ai-local-smb-lead-gen.py` first (20+ checks)
   - Should have used `kanban_chains` or manual phased build with verifier gates
   - Builder self-assessed "simple enough" and built in one shot
5. **Write README.md** ❌ SKIPPED
   - Required sections: What It Is, The Problem, Core Features, How to Review, Grill Decisions, Riskiest Assumption, How to Run, What Happens Next, Dossier
   - Builder did not create README.md at all
6. **Handoff for review** ❌ SKIPPED
   - Should have loaded `prototype-review-handoff` skill
   - Should have written portfolio entry, kanban comment, review pointer

## Why This Happened

The builder received the task description and started working immediately without loading the `venture-prototype` skill. The task said "Create single-file HTML dashboard" — the builder saw "HTML" and "dashboard" and went straight to building.

The builder fell into the **"this is simple HTML, I don't need a full workflow"** trap, which is documented in venture-prototype as a common pitfall but has been violated 15/15 times across multiple batches.

## What Was Lost

1. **Verification script** — No `/tmp/verify-leadpilot-ai-local-smb-lead-gen.py` was written. This means:
   - No automatic check that all 40 decisions are reflected in the HTML
   - No check that the HTML is valid (no JS errors)
   - No check that dark theme and mobile responsiveness are present
   - No check that demo data is clearly labeled

2. **README.md** — No README means:
   - Founder doesn't have a review surface to understand the prototype
   - No "How to Review" section with specific click instructions
   - No documentation of what the prototype is and why it matters
   - No mapping of features to pain points
   - No link to the grill decisions that informed the build

3. **Independent verification** — loop_engine means a separate agent session verifies the work against the grill decisions. Skipping this means:
   - No independent check that the HTML actually reflects all 40 decisions
   - No runtime verification (opening the file in a browser to confirm it renders)
   - No catch of subtle bugs (e.g., unbalanced HTML, broken JS)

4. **Structured handoff** — No portfolio entry, no kanban comment, no review pointer. This means:
   - Founder doesn't have a clear "look here" signal
   - No portfolio record of the prototype's existence
   - No transition point for founder feedback

## Detection Pattern

The violation is detectable by these signs:
- Task completion with only the prototype file (no README.md)
- Kanban completion metadata shows only `artifacts=[.../index.html]`
- No verification script at `/tmp/verify-<slug>.py`
- No mention of loop_engine in the work log
- Task body said "build the prototype" but builder stopped at the file

## The Fix

**Load venture-prototype BEFORE starting ANY prototype build.**

```python
# ALWAYS start with this:
skill_view(name='venture-prototype')

# THEN read the grill decisions and build
```

The skill takes 5 seconds to load and prevents all of the above violations. It's not optional scaffolding — it's the workflow definition.

## Impact

The HTML file itself is good quality (32KB, 939 lines, all 40 decisions reflected, dark theme, mobile-responsive). The violation is in the PROCESS, not the OUTPUT.

However:
- Founder cannot properly review without README.md
- There's no verification that the HTML actually works in a browser
- No handoff means founder may not know the prototype exists
- Missing verification script means the grill decisions aren't systematically checked

## Lesson

**Even when you think you know the workflow, load the skill.**

The 5 seconds it takes to load `venture-prototype` is worth it to ensure you're following the mandatory 6-step process. The builder's intuition ("this is simple HTML, I don't need README") has been proven wrong 15/15 times — trust the skill, not your intuition.
