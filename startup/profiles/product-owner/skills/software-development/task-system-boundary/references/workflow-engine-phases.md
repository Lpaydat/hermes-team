# Workflow Engine — 5-Phase Architecture

Location: `startup/profiles/product-owner/scripts/workflow-engine.py`
Runs: every 1 minute as a no-agent cron (zero tokens)
State: `active-projects.json` (project registry)

## Phase 1: bead-sync

Syncs kanban card completion → bead closure. When a card with idempotency key `bead-<id>` reaches `done`, the engine runs `bd close <id>`. This makes beads the durable canonical store — the board is rebuildable from beads.

## Phase 2: dispatch

Checks `bd ready` for each project. Routes beads:
- **Bug beads** (`issue_type=bug`) → `dispatch_bug_to_debugger()` creates `[auto] bug:` card assigned to debugger
- **Wayfinder beads** (special labels) → routed to scout/ops/architect
- **All other beads** → creates ONE `[dispatch] N ready bead(s)` card assigned to PO

**Pitfall:** `hermes kanban create` does NOT accept `--skills` flag. Passing it causes silent failure (exit 2).

**Pitfall:** `bd create --type=bug` may store `issue_type=task`. The engine has a fallback: checks `issue_type == "bug"` OR (`issue_type == "task"` AND any label contains "bug" keyword). This catches the case where bd stores the type incorrectly but the label still carries the signal.

## Phase 3: human-escalation

Human-flagged beads → operator HQ card on the `hermes-hq` board.

## Phase 4: scanner (board escalation)

Blocked tasks → escalate one level up on the SAME board:
- developer/verifier/debugger/qa blocked → tech-lead
- tech-lead blocked → product-owner
- product-owner blocked → HUMAN_REQUIRED comment

**Pitfall:** The escalation chain originally omitted `debugger` and `qa`. Blocked debugger/qa cards hit HUMAN_REQUIRED immediately instead of escalating to tech-lead first. Fixed by adding both to ESCALATION_CHAIN.

Checks for existing escalation cards and RESOLVED comments to avoid duplicates.

## Phase 5: qa-trigger (card-based)

Scans kanban DB for recently-completed verifier/debugger cards → creates QA re-test card.

**Why card-based with regex merge detection:** The original implementation parsed git merges (`git rev-list --merges`). This had two failure modes: (1) fired on PO spec/doc commits (not code merges), and (2) required baseline seeding on first run (creating bogus QA cards for initial commits). The card-based approach scans the kanban DB directly. But the first card-based version (filtering by parent-child debugger relationships) failed because the debugger's loop_engine creates complex parent chains that don't match simple patterns. The regex approach — checking the completion summary for merge keywords — is robust because it detects the outcome ("merged to master") rather than inferring from relationships. Validated against 18 historical cards: 6 correct triggers (all real merges), 0 false positives.

**Logic:**\n1. Query board DB for cards where `assignee IN ('verifier', 'debugger')`, `status = 'done'`, `outcome = 'completed'`, and `completed_at > (now - 3600)` (1-hour window)\n2. Filter out `[probe]` and `verify t_` cards (sub-reviews, not merge events)\n3. **Regex merge detection:** Only trigger if the card's completion summary (lowercased) matches merge patterns: `merged to master`, `merged to main`, `. merged `, or `^merged `. Internal loop phases (falsification, RCA, discover) never say "merged to" — they say "GREEN", "RED", "RCA", "verified".\n4. For each match, check idempotency key `qa-after-<source-card-id>` — skip if QA card already exists\n5. Create `[qa] Re-test: <title>` assigned to `qa` with the source card's completion summary as context

**Dedup:** idempotency key `qa-after-<source-card-id>` prevents duplicate QA cards for the same completed card.

**Time window pitfall:** Without a time window, the engine replays ALL historical card completions on first run (35+ cards across all boards). The 1-hour lookback prevents this. If a board has been running for weeks, only the last hour's completions are processed.

**No git state file needed:** Unlike the git-based approach, this version has no `qa-merge-state.json` — dedup is purely through kanban idempotency keys.

**Known limitations from full script review:**
- The 1-hour lookback window means engine downtime >1h causes permanent QA trigger misses (card completed while engine was down → never processed).
- `completed_at` comparison assumes epoch integers. If a kanban version stores datetime as strings, the `> ?` comparison silently skips all rows.
- `import re` was initially placed inside the for-loop body (redundant — already imported at module level). Fixed but worth noting as a pattern to watch for.
- The engine never exits non-zero on top-level exceptions (`sys.exit(0)` on any error). Cron never reports failure — if the engine is fundamentally broken, it silently does nothing every minute forever.

## Idempotency Keys Summary

| Card type | Key format | Purpose |
|-----------|-----------|---------|
| Feature dispatch | `bead-<bead-id>` | Prevent re-dispatch of same bead |
| Bug dispatch | `bead-<bead-id>` | Same — bugs use same key space |
| QA re-test | `qa-after-<source-card-id>` | Prevent duplicate QA for same completed card |
| PO dispatch | `po-dispatch-<board>-<timestamp>` | Prevent duplicate dispatch batch |
| Wayfinder | `bead-<bead-id>` | Same key space |

## Full Pipeline Lifecycle

```
1. PO creates epic + feature beads
2. Engine phase 2: creates dispatch card → PO
3. PO creates tech-lead cards (one per bead)
4. Tech-lead creates dev + verifier cards via kanban_chains
5. Dev builds, verifier reviews (iterate on FAIL)
6. Verifier merges to master on PASS
7. Engine phase 5: verifier card completed → creates QA card
8. Engine phase 1: bead-sync closes the feature bead
9. QA tests assembled artifact
   - PASS: done
   - FAIL: files bug bead linked to epic
10. Engine phase 2: bug bead → debugger card
11. Debugger: discover → RED repro → fix → falsify → converge → RCA
12. Debugger creates verifier card for merge (or closes if already-fixed)
13. Verifier merges fix to master
14. Engine phase 5: verifier card completed → creates QA re-test card
15. Engine phase 1: bead-sync closes the bug bead
16. QA re-tests → PASS → done
```

## When This Will Disappear

The workflow engine exists because beads and kanban lack event hooks into each other. When the team builds their own harness (planned), beads absorbs kanban and the engine disappears into native lifecycle hooks:
- `bd post-ready` hook replaces phase 2
- `kanban on-complete` hook replaces phase 1
- Card-completion event replaces phase 5
- The scanner (phase 4) becomes native blocked-task surfacing
