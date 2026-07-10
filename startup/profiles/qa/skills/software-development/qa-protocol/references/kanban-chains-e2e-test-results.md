# kanban_chains End-to-End Test Results

Three rounds of testing against cross-browser-ai MVP (Next.js webapp + Supabase + Stripe + Playwright).

## Round 1: Option A (`hermes kanban swarm` CLI)

**Result: workers crashed (first attempt), then succeeded (second attempt after fixes)**

Bug 1: CLI bracket syntax — `--worker qa:"Title"[:qa-functional]` produced skill name `qa-functional]` (trailing bracket) → agent crash on startup. Fix: use `"qa:Title:qa-functional"` without brackets.

Bug 2: Platform `kanban_swarm.py` hardcodes verifier skill `requesting-code-review` and synthesizer skill `humanizer`. Neither exists on QA profile. Fix: installed stub versions that redirect to QA roles.

Bug 3: Card bodies were generic boilerplate — workers had to parse a shared blackboard blob for their assignment. This worked but wasted time.

After fixes: all 4 workers completed in ~20 min each, produced 18 findings (1 P0, 4 P1, 5 P2, ...). Real evidence-backed findings.

## Round 2: Option B (`qa_swarm` plugin)

**Result: clean success, zero crashes, better card content**

Plugin baked tailored checklists directly into each worker card body. Workers started immediately — no blackboard parsing. 19 findings comparable to Option A. Faster (10-17 min per worker vs 20 min).

## Round 3: `kanban_chains` (unified plugin)

**Result: full pipeline success — QA → triage → fix → verify → merge ran autonomously**

3 workers (functional, exploratory, security) ran in parallel. Verifier gated. Synthesizer deduped 14 worker findings to 13 unique root causes and filed ONE triage report to tech-lead. Tech-lead delegated fixes via kanban_chains → dev+verifier pairs. Fixes merged. Full autonomous loop.

**But:** orchestrator created a SECOND swarm on re-dispatch (bug), and blocked itself with `kind=null` instead of `kind=dependency` (bug). Both fixed in qa-protocol v3.1.0.

## Key metrics across all rounds

| Metric | Option A (CLI) | Option B (qa_swarm) | kanban_chains |
|---|---|---|---|
| Worker crashes | 8 → 0 (after fix) | 0 | 0 |
| Card body quality | Generic boilerplate | Tailored checklist | Tailored checklist |
| Findings produced | 18 | 19 | 13 (deduped) |
| Fix loop | Manual | Manual | Autonomous (tech-lead → dev → verifier → merge) |

## Architecture lessons

1. **Plugin > CLI for topology creation** — models skip CLI commands embedded in skill text. A tool in the tool list gets called reliably.
2. **Tailored card body is the key advantage** — each worker knowing exactly what to test (specific claims, ports, env facts) eliminates the blackboard parsing step.
3. **Synthesizer dedup is critical** — 3 workers independently found SSRF. Without dedup, that's 3 redundant developer cards for the same root cause.
4. **Findings route to tech-lead, not developer** — tech-lead triages and uses kanban_chains for dev+verifier pairs. Filing to developer bypasses the verifier pipeline.
5. **ONE swarm per card** — re-dispatch after swarm completion means "read results," not "create another swarm."
6. **Always `kanban_link` + `kanban_block --kind dependency`** — a block without a link or with `kind=null` creates a permanently stuck card.
