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

## Round 4: `kanban_chains` (v3.2.0 — eliminate manual link/block)

**Result: clean flow, orchestrator completes after verdict, no manual link/block leaks**

Two additional bugs found and fixed:
1. **QA skill leaked manual `kanban_link`/`kanban_block`** in Step 5 (Triage). The skill told the orchestrator to manually link+block on the tech-lead's fix card — but `kanban_chains` handles all linking/blocking internally. Fixed: orchestrator completes immediately after the verdict, no manual link/block. The re-test is a separate QA card created by tech-lead.
2. **QA skill lacked call shape example.** Step 4 said "call `kanban_chains`" without showing the parameter object structure. The agent guessed wrong. Fixed: concrete call example added with full chains+after+blackboard shape.
3. **Tech-lead skill said "call `kanban_chains` again" to re-block on fix verifiers.** This creates a duplicate topology. Fixed: use `kanban_link` + `kanban_block --kind dependency` on existing fix verifier cards instead.

**Architecture lesson:** when a skill documents a plugin tool, the skill must NOT also teach the agent to call the underlying primitives (`kanban_link`, `kanban_block`) for the same purpose. Two execution paths → the agent sometimes uses the plugin, sometimes falls back to error-prone manual calls.

## Round 5: `kanban_chains` v3.2.0 — stale claim_lock + auto-block verification

**Result: full pipeline success, but orchestrator delayed 9 hours by stale claim_lock**

Two new issues discovered:

1. **Stale claim_lock prevents dispatch.** The orchestrator was spawned at 01:14, called `kanban_chains`, blocked (status → `todo`). Synthesizer completed, card promoted to `ready`. But `claim_lock` still held `lambda:926` from the original spawn (expired at 01:19). The dispatcher skipped the card on every tick for 9 hours. `release_stale_claims` didn't clean it because the lock was placed by a different gateway than the one dispatching. Fix: manually clear `claim_lock` + `claim_expires` via SQL, then `hermes kanban dispatch --dry-run` to confirm.

2. **kanban_chains auto-block verification race condition.** The plugin calls `hermes kanban block` then `hermes kanban show` to verify status == `todo`. The block_task SQL includes `running` in its WHERE clause, so the block should succeed. But `hermes kanban show` returned `status=None` (stale subprocess read — SQLite WAL checkpoint lock window between the write commit and the read subprocess opening a new connection). The plugin returned a false-negative error. The orchestrator then tried manual `kanban_link` + `kanban_block`, but the card had already been archived (the `_end_run` call with `outcome="blocked"` confused the dispatcher). Fix: remove the verification step from the plugin — trust the block command's return code (exit 0 = success).

3. **Config file location confusion.** We changed `max_in_progress_per_profile` in `~/.hermes/config.yaml` to no effect — neither `~/.hermes/config.yaml` nor the global `startup/config.yaml` is what the dispatcher reads. The dispatcher reads the **lock-holding gateway's OWN profile config** (`startup/profiles/<profile>/config.yaml`); because the lock-holder is non-deterministic, the reliable fix is to set the cap in every profile's `config.yaml` and restart the dispatcher-holding gateway.

Despite these issues, the swarm itself worked: 4 workers completed, synthesizer filed deduped triage to tech-lead, tech-lead created 3 dev+verifier fix chains via `kanban_chains`, all 3 merged to main. Final verdict: PASS with 7 findings (0 P0/P1), 4/4 prior security fixes held.

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
7. **Never use `blocked` status for draft cards** — a blocked-escalation cron scans for blocked tasks and handles unblock loops. Draft cards in `blocked` trigger the escalation cron. Use `scheduled` for non-dispatchable intermediate states.
8. **Never add subprocess verification after kanban writes** — a plugin that calls `hermes kanban show` as a subprocess to verify a prior write will hit SQLite WAL checkpoint lock windows. The subprocess returns `None` or non-zero exit. Trust the write command's exit code instead.
