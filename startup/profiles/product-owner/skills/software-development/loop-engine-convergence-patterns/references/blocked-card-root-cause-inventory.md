# Blocked Card Root Cause Inventory

Complete inventory of every blocked-card root cause found across 6 e2e tests
(wf-test, wf-gate-test, hashtree, e2e-final, e2e-clean, port-csv2md + compose-dataviz).

## Classification Framework

| Category | Meaning | Action |
|----------|---------|--------|
| SILLY | Card blocked for a wrong reason — pipeline bug | Fix at source |
| REAL | Card blocked for correct reason — working as designed | Leave alone |
| HERMES | Platform behavior we can't fix in our code | Report upstream |

## SILLY Blocks (all FIXED at source)

### 1. Cross-profile skill crash (loops-engineering)
- **Symptom:** `Error: Unknown skill(s): loops-engineering` — developer/verifier cards crash on spawn
- **Root cause:** `loops-engineering` skill exists only on tech-lead. Agents passed it to cards assigned to developer/verifier.
- **Fix:** Symlinked loop_engine + kanban_chains to ALL 15 profiles (commit c0f3d7a)
- **See:** Pattern 22 in SKILL.md

### 2. Cross-profile skill crash (live-testing)
- **Symptom:** `Error: Unknown skill(s): live-testing` — debugger cards crash on spawn
- **Root cause:** Bug cards created by QA with `skills: ["live-testing"]` assigned to debugger. live-testing only exists on qa.
- **Fix:** Installed live-testing on debugger profile + added "DO NOT pass skills on finding cards" to bug-handoff skill (commit 2c4f145)

### 3. Bug-handoff link direction inverted
- **Symptom:** QA quick card stuck in `todo` forever — can't dispatch because parent is a blocked bug card
- **Root cause:** bug-handoff skill said "link the card as a parent of the QA card" — agent linked bug as PARENT of QA (backwards). The bug card blocked, and its "child" (QA) couldn't promote.
- **Fix:** Rewrote bug-handoff skill to clarify direction: finding card is CHILD of QA, `parents: [qa_card_id]` means QA is parent (commit 6c6cb22)

### 4. Developer self-blocking for "review"
- **Symptom:** Developer cards block with `kanban_block(reason="review-required: ...")` despite being told to COMPLETE
- **Root cause:** Developer-loop skill says block with `transient` or `needs_input` only, but some developers invent a "review-required" reason not in the skill. This is agent non-compliance.
- **Fix:** Can't fix non-compliance with more instructions. The developer-loop skill already says the right thing. Gauntlet lesson #8 covers the related gateway-level issue.

### 5. git diff --name-only → git log --oneline (semantic regression)
- **Symptom:** QA told to identify changed files via a command that returns commit messages
- **Root cause:** When merging qa-gate into milestone-gate, `git diff --name-only` was changed to `git log --oneline`. Both are git commands but produce different output.
- **Fix:** Restored git diff --name-only alongside git log --oneline (commit ab011ca)

### 6. REFACTOR.md written to scratch workspace
- **Symptom:** REFACTOR.md metadata says repo path but file doesn't exist on disk
- **Root cause:** Verifier runs in scratch workspace, writes REFACTOR.md there. Workspace cleaned up after completion.
- **Fix:** Explicit path in body: `${trigger.card_body}/REFACTOR.md (the actual repo, NOT your workspace)` (commit c0f3d7a)

## REAL Blocks (working correctly — leave alone)

### dependency
- Card waiting on parent task to complete. This is the kanban dependency gate working correctly.
- Example: milestone-02 card has parents [ticket-03, ticket-04]. It sits in `todo` until both complete.

### needs_input
- Agent genuinely needs human input (contract dispute, design decision, missing credentials).
- Example: developer found acceptance criteria that seem wrong → `kanban_block(needs_input)`.

### transient
- Gates failing after retry. Developer harness produced broken code, warm-resume also failed.
- Example: `kanban_block(transient)` with session_id + transcript path.

## HERMES Blocks (platform behavior — can't fix in our code)

### Circuit breaker with empty block_kind
- **Symptom:** Card status=blocked, block_kind=NULL, consecutive_failures=2
- **Root cause:** Circuit breaker trips at 2 consecutive crashes, sets status=blocked but doesn't set block_kind. This is hermes-agent behavior in the kanban lifecycle.
- **Can't fix:** This is in hermes-agent's kanban_db.py. The stale-claim reaper in workflow-engine.py (phase 6) catches dead-PID cases but NOT alive-but-crashed cases.

## The Rule

**Fix silly blocks at the source. Never build a sweeper that auto-unblocks.** The user's hard line: "we might ruin the system/workflow instead" if we unblock without understanding why. Every silly block is a bug — find it, fix it, and that class of block never happens again. A sweeper would just mask it.
