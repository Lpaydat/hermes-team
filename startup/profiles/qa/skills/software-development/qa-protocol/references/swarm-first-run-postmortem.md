# Swarm First-Run Postmortem

What worked, what broke, and the fixes applied during the first end-to-end QA swarm tests (2026-07-09).

## Test 1: Option A (hermes kanban swarm CLI) — all workers crashed

**What worked:** Orchestrator received card, read contract, built container, created swarm topology (root + 4 workers + verifier + synthesizer), posted blackboard, blocked correctly.

**Bug 1 — Bracket syntax:** Skill showed `--worker qa:"Title"[:qa-functional]`. The CLI parser captured literal `]` in the skill name → `qa-functional]` not found → agent crash. Fix: use `"qa:Title:qa-functional"` (no brackets).

**Bug 2 — Hardcoded skills:** `kanban_swarm.py` hardcodes `requesting-code-review` for verifier and `humanizer` for synthesizer. Neither exists on the QA profile → crash. Fix: installed thin stub skills that redirect to QA roles. Do NOT edit platform source — it's overwritten on `hermes update`.

**Mistake — Edited platform source:** I edited `kanban_swarm.py` directly. User caught this: "isn't kanban_swarm.py official code?" Reverted immediately. Work around at profile level only.

## Test 2: Option A (fixed) — 4 workers completed

All 4 workers ran ~20 min each, produced real findings (P0 results-404, P1 SSRF, P1 rate limit bypass, P2 CSRF, etc.). Card bodies were generic boilerplate — workers had to parse a shared blackboard blob for their assignment.

## Test 3: Option B (qa_swarm plugin) — 4 workers completed, better content

Plugin created worker cards with tailored bodies (specific checklists, container commands, port allocation). Workers completed in ~10-17 min each (faster — less time figuring out what to test). Comparable finding depth.

## Post-test discovery: finding routing bypassed verifier

Synthesizer filed individual finding cards directly to `developer` — no verifier child created. The dev→verifier pipeline invariant was broken. Three workers independently found the same SSRF → 3 separate developer cards for the same vulnerability. Fix: synthesizer now dedupes by root cause and files ONE triage report to `tech-lead`, who uses `kanban_delegate` to create dev+verifier pairs.

## Bug: kanban_block without kanban_link = permanent stuck

Orchestrator called `kanban_block(reason="waiting for synthesizer")` without `kanban_link(synthesizer, self)`. The block sets status to `todo`, but without a parent→child link in `task_links`, `recompute_ready()` never promotes the card when the synthesizer completes.

**Always pair `kanban_block(kind=dependency)` with `kanban_link(dependency_target, my_card_id)`.** The `qa_swarm` plugin does this correctly. The bug only appeared when the orchestrator blocked manually.

## Auto-decomposer ≠ self-healing

User feedback submitted via the dashboard ("QA files directly to developer...") created a triage card. The auto-decomposer picked it up and created tech-lead + developer + verifier tasks with `created_by: "auto-decomposer"`. This was NOT the team self-correcting — it was the auto-decomposer reacting to user input. Always check `created_by` and read session DBs before claiming system behavior.
