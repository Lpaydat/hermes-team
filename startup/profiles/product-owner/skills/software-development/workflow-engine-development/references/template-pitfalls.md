# Template Authoring Pitfalls (learned the hard way)

## 1. Compound `!=` AND conditions silently break

Each clause must be individually correct. The old engine (pre-merge) silently returns True for all clauses after the first. The new engine (merged ecad177b) fixes this with proper AND/OR parsing.

**Fix:** Verify compound conditions with `evaluate_condition()` BEFORE deploying.

## 2. Output schema must match what the profile ACTUALLY writes

dev-dispatch route-bug declared `enum: ["root-caused", "cannot-reproduce"]` — but the debugger SOUL.md outputs `fixed`, `escalated-design`, `blocked-hitl`.

**Fix:** Audit the target profile's SOUL.md §output-contract before writing the schema.

## 3. `blocked-hitl` never fires `card_completed`

The debugger stays blocked on `blocked-hitl` (never completes). A trigger on `assignee=debugger, status=done` will NOT catch this exit. The scanner catches blocked cards.

## 4. `loop_engine` is the debugger's brain — do NOT decompose

loop_engine handles reproduce→fix→falsify→converge internally with adaptive replan, breadcrumb ledger, and fact-discipline enforcement. A workflow template that recreates these phases as nodes loses all of that.

**Fix:** One debugger node that calls loop_engine internally. The workflow engine routes exit verdicts only.

## 5. Don't put test cards on production boards

Create a dedicated test board, add it to `active-projects.json`, test there, delete after.

## 6. Corrupt board DBs crash the engine tick

Boards with empty kanban.db (no `tasks` table) cause `no such table: tasks`. `_boards_to_check()` now skips corrupt boards, but daemons can recreate deleted boards.

## 7. `${trigger.merged_commit_sha}` doesn't exist

The trigger context has `card_id`, `board`, `assignee`, `title`, plus metadata fields. Verify every `${trigger.*}` variable against `_start_from_trigger()`.

## 8. Never migrate a workflow without explicit approval AND a full audit

The qa-loop.json was a 1:1 copy of the old cron's card body — but the cron's TRIGGER logic was lost. Before migrating: (1) read the original cron phase, (2) read the profile's SOUL.md, (3) read the skills, (4) get explicit approval, (5) preserve trigger intelligence.

## 9-11. Back-edge, source clearing, cannot-reproduce

See stateless-engine-pitfalls.md for back-edge annotation (DFS-based), source node clearing on reset, and debugger verdict vocabulary.

## 12-16. Schema and condition pitfalls

- Boolean string enums fail (`str(True)` = `"True"` not `"true"`)
- Null optional fields fail string schema
- The `skill` field is a no-op under skill_enforcer
- `depends_on` ignored when explicit edges exist
- Command scripts must output lowercase string booleans

## 17. loop_engine is NOT debugger-specific

Used by architect, builder, debugger. kanban_chains is universal (ALL profiles).

## 18. Card structure drives execution depth (A/B/C/D/E proven)

Same 8-phase protocol in 1 card → agent skipped 5 phases. Same protocol in 7 cards → agent executed all 7. Card structure IS the enforcement.

## 19. Verdict vocabulary must be uppercase PASS/FAIL everywhere

Without schemas on intermediate cards: `pass`, `clean`, absent. With schemas: all `PASS`.

## 20. Schema on ALL task nodes, not just verdict

Without schemas: `risk` instead of `risk_level`, `head_tested` instead of `commit_tested`.

## 21. Delta-first testing instruction required

Cards must say `git diff --name-only` and test changed files first. Without this, agents test unchanged files.

## 22. Verdict card design (fan-in pattern)

Include: one key evidence per phase inline, `findings[]` array, `findings_filed` count, `phases{}` breakdown, `delta_summary`.

## 23. A/B/C/D/E/F validation pattern — required before pinning

Build 2-3 versions → run in parallel → 8+ subagent analysis → pin winner → fork + fix → repeat.

## 24. Adaptive sizing: single-card beats fan-out for small artifacts (E vs D)

E (adaptive, 2 cards) beat D (always fan-out, 7 cards) on small artifacts:
- 47% faster, 3× cheaper
- Tested MORE claims (6 vs 4) and journeys (2 vs 1)
- Found a REAL finding D missed (single-session context caught stale .driver/ labels)
- The finding was filed as an actual kanban card (findings_filed: 1)

**Lesson:** Single-session context lets QA see the full picture. Fragmented cards each see only their phase. For small artifacts, fragmentation HURTS quality, not just cost.

## 25. Intermediate card schemas enforce vocabulary consistency

Adding `output.schema` with `"verdict": {"type": "string", "enum": ["PASS", "FAIL"]}` to all 4 test cards (functional, journeys, security, explore) eliminated the vocabulary drift that plagued C. Schema enforcement > body text instructions.

## 26. body_template CANNOT enforce structured output (F FAILED)

**The most important template lesson from the A/B testing campaign.**

Version F strengthened qa-quick's body_template with structured output requirements:
- Per-claim evidence table (markdown table with columns)
- Enumerated security checklist (PASS/FAIL/SKIP + reason per check)
- Testability feedback section
- One-key-evidence-per-area citation

**The agent completely ignored the structured format.** It produced a narrative
paragraph summary. None of the required sections appeared in the output.

Worse, F produced a **false negative**: it missed the identical stale-label
finding E caught. The rigid structured format made QA:
- Check .driver/ docs for EXISTENCE only ("docs created with discovery content")
- Never inspect their CONTENT for stale references
- Test 8 claims (vs E's 6) but with shallower inspection per claim

**Root cause:** body_template serves as INSTRUCTIONS to the agent, NOT as an
output format. The agent reads body text as guidance but writes whatever
summary it wants. You CANNOT enforce structured output via body prose.

**Correct approach:** use `output.schema` fields that the engine validates
at completion. Mismatch → node fails. This is tool-level enforcement, which
always beats prompting.

## 27. Structured body format suppresses exploratory depth

F's rigid per-claim table + security checklist made QA MORE rigid and LESS
exploratory. It tested 8 claims vs E's 6 but found 0 findings vs E's 1 real
finding. E's looser, probe-oriented approach caught the bug F's rigidity hid.

**Trade-off:** structure improves breadth but reduces exploratory depth.
Adaptive sizing (E) gets both: single-session flexibility for small artifacts,
dedicated cards for depth on medium/large.

## 28. node_states.status stale on dead-branch skip

Skipped nodes remain `pending` in the node_states table. The engine_events
table has the authoritative skip events. This is a known bookkeeping quirk,
not a routing failure — the event log is unambiguous.
