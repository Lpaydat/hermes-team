# Self-Healing System — Board Scanner + 429 Resilience Layers

## The problem

The autonomous dev workflow has a critical reliability gap: **when a task blocks, the board freezes silently**. Three failure modes:

1. **Crash exhaustion**: agent crashes N times (max_retries), dispatcher gives up → task stuck as `blocked` with generic "protocol_violation" error. No way to distinguish 429 from a real bug.
2. **Spec ambiguity**: developer finds contradictory ACs, correctly blocks with `needs_input`. Children stay in `todo` forever — nobody sees the question.
3. **No incident trail**: when deadlocks happen, there's no structured log for future analysis.

## The 4-layer architecture (IMPLEMENTED Jul 2026)

```
Layer 1: In-session retry
  agent.api_max_retries: 10 (was 3)
  model.rate_limit_delay: 30 (was ~2-5s exponential)
  → Agent survives ~5 min of 429 storms without dying

Layer 2: Kanban reclaim (existing)
  max_retries: 2 (default, consider increasing to 3)
  → Fresh session retry for genuine crashes

Layer 3: Board scanner cron (NEW — every 3 min, zero-token)
  scripts/board-scanner.py
  → Detects deadlocks, auto-resolves transient blocks, escalates needs_input

Layer 4: Incident logging (NEW)
  INCIDENTS.md in project dir
  → Structured log of every deadlock for future workflow analysis
```

## Board scanner design

### Detection logic

The scanner reads the board via `hermes kanban --board <board> list --json` and identifies:

1. **Crash-exhausted tasks**: `status=blocked` but no `blocked` event in event log — only `gave_up` events from the dispatcher. These are classified as `transient` (the crash was likely a 429 storm, not a logic error).
2. **needs_input blocks**: `status=blocked` with a `blocked` event containing `kind: "needs_input"`. These require human/planner resolution.

### Actions per type

| Block type | Scanner action | Why |
|------------|---------------|-----|
| `transient` (crash) | Auto-unblock after 2-min cooldown | 429s clear in 30-60s; a fresh dispatch will likely succeed |
| `needs_input` (developer) | Create escalation card → tech-lead | Tech-lead wrote the contract; it can resolve spec issues |
| `needs_input` (tech-lead) | Create escalation card → PO | PO owns the beads/PRD; it can clarify intent |
| `needs_input` (verifier) | Create escalation card → tech-lead | Tech-lead owns the contract |
| `needs_input` + HITL tag | Create escalation card → PO (TODO: gateway notify) | HITL = human-in-the-loop, needs user not agent |
| `needs_input` (PO) | Create escalation card → PO | PO needs human input |

### Anti-loop protection

- State file at `/tmp/board-scanner-state.json` tracks all escalations
- Max 3 escalation attempts per blocked task
- Escalations expire after 1 hour (TTL)
- Idempotency keys on escalation cards prevent duplicate creation within 1-hour buckets
- Before creating a new escalation, checks if the previous one is still active

### Incident logging format

Every deadlock/escalation is appended to `INCIDENTS.md`:

```markdown
## [2026-07-05 17:05:56 UTC] DEADLOCK ESCALATION → tech-lead — t_5a01057c

**Blocked task**: t_5a01057c (developer)
**Title**: Implement debounce_text.py (maker)
**Block reason**: Spec inconsistency: AC2 test case...
**Block kind**: needs_input
**Stuck children**: 0 ()
**Escalated to**: tech-lead (card: t_7fcf2597)
**Escalation #1 of 3**
```

This log is the input for the PO's meta-analysis: patterns of repeated spec ambiguities suggest the grilling phase needs improvement; patterns of 429 crashes suggest the retry config needs tuning.

## 429 detection problem

**The 429 root cause is invisible to the kanban API.** When a 429 storm kills an agent:
1. The agent retries internally (3-10 times)
2. After exhausting retries, exits cleanly (rc=0) without calling `kanban_complete` or `kanban_block`
3. The dispatcher sees: `"worker exited cleanly (rc=0) without calling kanban_complete or kanban_block — protocol violation"`
4. This is a GENERIC error — identical for any crash, not just 429

**The scanner's workaround**: treat ALL crash-exhausted blocks as `transient`. Most agent crashes ARE transient (429, connection errors). If a task genuinely can't succeed (bad contract, missing dependency), it will crash again after unblocking — the scanner's max-escalation counter catches that after 3 cycles.

## Deployment

```bash
# Copy scanner to PO scripts dir
cp board-scanner.py ~/.hermes-teams/startup/profiles/product-owner/scripts/

# Deploy as zero-token cron (every 3 min)
cronjob(action='create', no_agent=True, script='board-scanner.py', schedule='every 3m')
```

## What's NOT yet implemented

1. **HITL gateway notification**: tasks with `HITL` tag should notify the user via Telegram/Discord instead of creating an agent card. The scanner stubs this as `# TODO: gateway notification when built`. Needs the gateway integration built.
2. **Smart retry counting**: the scanner can't distinguish "crashed 3x from 429" (transient) from "crashed 3x from logic error" (permanent). Both look the same. A future improvement: parse the agent's stdout/stderr for specific error patterns.
3. **Cascade-block children**: when a parent blocks, its children should auto-block too (for state honesty). Currently they stay in `todo` — the scanner escalates the parent but doesn't touch the children.
4. **FAIL verdict filing lock**: concurrent verifier sessions on the same parent review create duplicate fix chains (Test 20). A merge-slot-style lock on FAIL verdict filing would prevent the race at the source.

## Production-proven incidents (Jul 2026, Test 20)

The scanner resolved 3 distinct incidents in its first real deployment:

1. **Crash exhaustion (2 tasks)**: slices 3+5 tech-lead tasks crashed twice each on 429 storms. Scanner auto-unblocked both after 2-min cooldown. Dispatcher retried, tasks completed.

2. **Spec ambiguity (1 task)**: developer found contradictory ACs in debounce_text bead. Blocked with needs_input. Scanner escalated to tech-lead (card t_7fcf2597). Tech-lead resolved the spec.

3. **Concurrent verifier race (2 tasks)**: two verifier sessions created duplicate fix chains for the same FAIL verdict. Wrong-session verifier blocked itself (role violation). Scanner escalated deadlock to tech-lead (card t_c1026e63). Tech-lead archived the dead chain (t_c4741baa + t_3f513327), posted override comment on canonical chain (t_29f7b154), and the correct iteration-3 review proceeded to PASS.

All 3 incidents logged to INCIDENTS.md. Board never froze permanently. Zero human intervention.

## Design clarifications (refined Jul 2026)

### HITL belongs on `blocked`, not `todo`

The `todo` status means "waiting for parent completion" — the dispatcher auto-promotes todo→ready when the parent finishes. No human needed. HITL (human-in-the-loop) only matters on `blocked` tasks — that's where a genuine decision is stuck. The scanner checks HITL tags only on blocked tasks. Do not add HITL tags to todo tasks — they're meaningless there.

### Scanner must filter by assignee

The scanner must skip tasks with `assignee=default` (or empty/None). These are cross-project or human-only tasks that don't belong to the dev workflow profiles. Without this filter, the scanner escalates stray tasks from other projects (e.g. a `taskboard` security push card that needs `git push` — agents can't push, so escalating to tech-lead wastes a dispatch cycle). The filter is a single line: `if assignee in ("default", "", None): continue`.

### Scanner escalation creates garbage on stray tasks

Before the assignee filter was added (Jul 2026), the scanner found a pre-existing blocked task from the `taskboard` project (a real Hermes extension at `~/workspace/taskboard`) and escalated it to tech-lead. Tech-lead received the escalation, re-verified the state, concluded "all paths fail", and completed without resolving — wasting ~2 minutes of dispatch. The fix: only act on tasks assigned to real dev workflow profiles (developer, tech-lead, verifier, product-owner).
