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

## Phase 5: qa-trigger (structural metadata + fallback)

The most-iterated phase (8 approaches). Creates a QA re-test card when code lands on master.

**Approach history (what failed and why):**
1. **Git HEAD tracking** — fired on PO spec/doc commits (false positives)
2. **Git merge-commit count** (`git rev-list --merges`) — first-run seeding created bogus cards; also misses fast-forward merges (verifier may FF instead of `--no-ff`)
3. **Card-based with parent-child debugger filter** — loop_engine creates complex parent chains that don't match simple patterns; spurious QA cards
4. **Regex merge detection on summaries** — worked for most cases but fragile: verifiers write "PASS" not "merged", and fast-forward merges have no merge commit
5. **Regex with broader patterns** (`merged to master`, `. merged `, etc.) — still failed when verifier used "PASS" without mentioning merge
6. **Hybrid git-diff + verifier card** — language-independent: checks master HEAD advanced + code extensions in diff + verifier card completed. Works but relies on git state + time window.
7. **Card-based scan with time window + regex** — clean but natural-language dependency was fragile

**Final approach (8): structured metadata + fallback** — two-tier:
1. **PRIMARY**: check completed verifier/debugger cards for `merged_commit_sha` AND `verdict == "PASS"` in `task_runs.metadata`. Structural, no parsing, no git state, no time window dependency on the primary path.
2. **FALLBACK**: if no cards carry the metadata contract, fall back to approach 6 (git-diff + verifier card + code file extensions). Labeled `(fallback)` in action output.

The verifier's `adversarial-review` skill instructs PASS verdicts to include `merged_commit_sha` in metadata. The QA `live-testing` skill instructs verdicts to include `{verdict, claims_tested, claims_passed, findings_count, bug_bead_ids, commit_tested}`. Over time the fallback path will fire less as profiles adopt the contract.

**Dedup:** idempotency key `qa-merge-<current-sha>` — one QA card per master state.

**Known limitations:**
- The 1-hour lookback window means engine downtime >1h causes permanent QA trigger misses (verifier card completed while engine was down → never processed).
- `completed_at` comparison assumes epoch integers. If a kanban version stores datetime as strings, the `> ?` comparison silently skips all rows.
- The engine never exits non-zero on top-level exceptions (`sys.exit(0)` on any error). Cron never reports failure — if the engine is fundamentally broken, it silently does nothing every minute forever.

## Idempotency Keys Summary

| Card type | Key format | Purpose |
|-----------|-----------|---------|
| Feature dispatch | `bead-<bead-id>` | Prevent re-dispatch of same bead |
| Bug dispatch | `bead-<bead-id>` | Same — bugs use same key space |
| QA re-test | `qa-merge-<sha>` | Prevent duplicate QA for same master state |
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
7. Engine phase 5: master advanced + code files changed + verifier card done → creates QA card
8. Engine phase 1: bead-sync closes the feature bead
9. QA tests assembled artifact
   - PASS: done
   - FAIL: files bug bead linked to epic
10. Engine phase 2: bug bead → debugger card
11. Debugger: discover → RED repro → fix → falsify → converge → RCA
12. Debugger creates verifier card for merge (or closes if already-fixed)
13. Verifier merges fix to master
14. Engine phase 5: master advanced + code files changed + verifier card done → creates QA re-test card
15. Engine phase 1: bead-sync closes the bug bead
16. QA re-tests → PASS → done
```

## When This Will Disappear

The workflow engine exists because beads and kanban lack event hooks into each other. When the team builds their own harness (planned), beads absorbs kanban and the engine disappears into native lifecycle hooks:
- `bd post-ready` hook replaces phase 2
- `kanban on-complete` hook replaces phase 1
- Card-completion event replaces phase 5
- The scanner (phase 4) becomes native blocked-task surfacing
