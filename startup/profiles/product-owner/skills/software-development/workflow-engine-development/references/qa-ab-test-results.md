# QA Workflow Template A/B/C/D/E/F/G Test Results

## Test setup
- Board A (qa-ab-a): old cron phase_qa_trigger
- Board B (qa-ab-b): new engine qa-test.json (single card, body lists 8 phases)
- Board C (qa-ab-c): new engine qa-test-c.json (7-card fan-out, no schemas on intermediate cards)
- Board D (qa-ab-d): qa-test-d.json (7-card, 6 gap fixes: uppercase verdict, findings[], findings_filed, risk_level, delta-first, inline evidence)
- Board E (qa-ab-e): qa-test-e.json (adaptive sizing — qa-quick for small, fan-out for medium/large + schemas on ALL intermediate cards)
- Board F (qa-ab-f): qa-test-f.json (E + qa-quick evidence depth in body_template) — FAILED, DITCHED
- Board G (qa-ab-g): qa-test-g.json (E + schema-enforced verdicts[]/checks[] on qa-quick) — VERIFIED, PINNED

## Final scorecard

| Version | Verdict Quality | Execution Rigor | Findings | Wall-clock | Tokens | Cards | Status |
|---------|----------------|-----------------|----------|------------|--------|-------|--------|
| A (cron) | 28/60 | 4/10 | 0 | 4 min | ~20K | 1 | Disabled |
| B (1-card) | 34/60 | 5/10 | 0 | 4 min | ~28K | 1 | Disabled |
| C (7-card) | 52/60 | 7/10 | 0 | 7 min | ~110K | 7 | Disabled |
| D (7-card fixed) | 53/60 | 7/10 | 0 | 7 min | ~110K | 7 | Disabled |
| E (adaptive) | 45/60 | 7/10 | 1 real | 4 min | ~30K | 2 | Disabled (superseded by G) |
| F (E+body depth) | 35/60 | 5/10 | 0 (missed) | 2 min | ~25K | 2 | FAILED |
| **G (schema-enforced)** | **55/60** | **8/10** | **0** | **~4 min** | **~30K** | **2** | Disabled (superseded by H) |
| **H (G+exploration)** | **57/60** | **9/10** | **1 real** | **~4 min** | **~30K** | **2** | **PINNED — VERIFIED** |

## The critical lesson: F vs G (body text vs schema enforcement)

### F — body_template approach (FAILED)

F strengthened qa-quick's body_template with structured output requirements:
- Per-claim evidence table (markdown table with columns)
- Enumerated security checklist (PASS/FAIL/SKIP + reason per check)
- Testability feedback section

**The agent completely ignored the structured format.** It produced a narrative
paragraph summary. None of the required sections appeared in the output.

Worse, F produced a **false negative**: it missed the identical stale-label
finding E caught. The rigid structured format made QA:
- Check .driver/ docs for EXISTENCE only ("docs created with discovery content")
- Never inspect their CONTENT for stale references
- Test 8 claims (vs E's 6) but with shallower inspection per claim

**Root cause: body_template = instructions to the agent, NOT an output format.**

### G — output.schema approach (THE FIX)

G adds `verdicts[]` and `checks[]` as **required** fields in qa-quick's output schema:

```json
"required": ["verdict", "findings_count", "commit_tested", "verdicts", "checks"],
"properties": {
  "verdicts": {
    "type": "array",
    "items": {
      "type": "object",
      "required": ["claim_id", "claim", "verdict", "evidence"],
      "properties": {
        "claim_id": {"type": "string"},
        "claim": {"type": "string"},
        "verdict": {"type": "string", "enum": ["proven", "disproven", "untested"]},
        "evidence": {"type": "string"}
      }
    }
  },
  "checks": {
    "type": "array",
    "items": {
      "type": "object",
      "required": ["check", "result", "reason"],
      "properties": {
        "check": {"type": "string"},
        "result": {"type": "string", "enum": ["pass", "fail", "skip"]},
        "reason": {"type": "string"}
      }
    }
  }
}
```

If QA doesn't produce these arrays, the card **fails validation and retries**.
This is tool-level enforcement — the engine rejects non-compliant output.

The body_template still explains the contract ("engine validates them — missing
fields = card FAILS and retries") and shows the JSON shapes, but enforcement
is at the schema layer, not the prose layer.

## Key findings per version

### A (cron): baseline — tested wrong files
- Grepped changed file, ran deep checks on UNCHANGED files
- Custom metadata schema (`head_tested` instead of `commit_tested`)
- References beads (broken in kanban-only mode)

### B (1-card): best file targeting, skipped phases
- Ran `node --check` + `node app2.js` on actual changed file
- But skipped 5 of 8 phases despite body listing them all
- skill_enforcer loaded live-testing on BOTH A and B (skill field is no-op)

### C (7-card): best coverage, 2 schema failures
- 25+ test actions, 31 security checks, 2 exploration charters
- Schema failures: plan_complete boolean, image_tag null
- Tested unchanged files deeply (no delta-first instruction)

### D (7-card + 6 fixes): all gaps addressed
- ALL intermediate cards uppercase PASS|FAIL
- findings[] array on verdict card, inline evidence per phase
- findings_filed accountability, risk_level (not bare risk)
- Delta-first: git diff --name-only, test changed files
- Zero validation failures

### E (adaptive sizing): cost+coverage winner
- qa-receive computes sizing → small routes to qa-quick (1 card)
- 2 cards total vs 7: 47% faster, 57% fewer tokens
- Tested 6 claims + 2 journeys (D tested 4 + 1)
- Filed a REAL finding D missed (stale .driver/ labels)
- Single-session context caught cross-cutting issue fragmented cards missed
- Adaptive routing: sizing==small → qa-quick, sizing!=small → 7-card fan-out

### F (E + body depth): FAILED — agent ignored structured format
- Body template had per-claim evidence table, security checklist
- Agent produced narrative summary, ignored all structured sections
- False negative: missed stale .driver/ labels (existence check only, no content)
- Rigid format suppressed exploratory depth

### G (E + schema enforcement): tool-level enforcement — VERIFIED 8/10
- verdicts[] and checks[] as required schema fields
- Engine validates at completion — missing fields = card FAILS and retries
- Body explains contract and shows JSON shapes
- Adaptive sizing preserved from E

**Verification (2026-08-03):** Loaded G's actual completion metadata
(t_416ff4d5 on qa-ab-g) and ran it through the engine's real
`validate_against_schema()` (from `kanban_adapter.py`) against the
qa-quick node's declared `output.schema`. Result: **valid=True**.

- 4 verdicts (C1–C4), each with claim_id + claim + verdict + evidence
  (evidence 75–102 chars: exact command + exit code + result string)
- 4 checks (secrets-scan, dangerous-patterns, dependency-scan,
  input-validation), each with check + result + reason (reason 56–99 chars)
- Top-level required all present: verdict, findings_count, commit_tested,
  verdicts, checks

**Negative test (proves enforcement is real, not cosmetic):** Ran F's
metadata (t_09c187c4 on qa-ab-f) and D's verdict card (t_0b1a8efd on
qa-ab-d) through the same schema. Both **valid=False**:
- F: missing `verdicts` and `checks` (only has aggregate counts)
- D: missing `verdicts` and `checks` (phases{} has counts but no inline
  per-claim evidence — delegates detail to child cards)

**Score breakdown (8/10):**
- ✅ Schema declared with nested item validation (verdicts[].required,
  checks[].required)
- ✅ Engine validates at completion (runtime.py:1260–1267, 1898–1903;
  test_engine.py::test_output_schema_validation proves failure path)
- ✅ G produced fully-compliant output on first attempt (no retry needed)
- ✅ F/D would fail the gate (enforcement is real)
- ❌ No failed-then-retried run captured (only 1 passing sample)
- ⚠️ Evidence is free-text string — field presence enforced, content
  quality still agent-dependent

**G vs D evidence quality:** At the verdict-card layer, G is strictly more
self-contained. D's verdict card references 4 child cards for evidence;
G carries the evidence inline. (Caveat: D was multi-phase with child cards
holding the real evidence; G is single-session qa-quick — slightly
apples-to-oranges.)

## Template pitfalls (live-discovered)

1. **body_template ≠ output format.** Agent ignores structured instructions in body text. Use output.schema required fields for enforcement.
2. **Boolean conditions: `True` not `true`.** `str(True)` is `"True"`. Command scripts must output lowercase strings.
3. **Schema `boolean` not `string enum`.** Use `{"type": "boolean"}` for JSON boolean fields.
4. **Optional fields omitted from schema.** Don't declare optional fields as `{"type": "string"}` — agents output null.
5. **`depends_on` unreachable with explicit edges.** Add explicit edges for ALL deps.
6. **`skill` field is a no-op.** skill_enforcer handles loading. Don't rely on template's skill field.
7. **Corrupt board DBs crash tick.** Empty kanban.db → `no such table: tasks`. Engine has guard now.
8. **`node_states.status` stale on skip.** Skipped nodes remain `pending`. Read `engine_events` instead.
9. **Structured body text suppresses exploration.** Rigid checklists in body make QA test for breadth, not depth. Misses bugs found by flexible exploration. (F's false negative)
10. **Schema enforcement preserves flexibility.** Required schema fields enforce output structure WITHOUT constraining how QA works. Agent can still explore freely — it just must report results in the required format.

## Plugin scope facts (corrected)

- `loop_engine`: used by architect, builder, debugger (NOT debugger-only)
- `kanban_chains`: universal plugin on ALL profiles (NOT tech-lead-only)
- QA has `kanban_chains` but NOT `loop_engine`
- Debugger uses `loop_engine` for internal 3-phase converge loop (reproduce→fix→RCA)

## Structural insight

**Card structure drives execution depth.** Same 8-phase protocol in 1 card → agent skips 5 phases. In 7 cards → executes all 7. Adaptive sizing (E) gets the best of both: single-card flexibility for small artifacts, dedicated cards for depth on medium/large.

**Output schema enforces structure without suppressing exploration.** Required fields force QA to report per-claim evidence and security checks, but don't constrain HOW QA does the testing. This is the key difference from F's body-text approach, which made QA rigid and produced false negatives.

## Validation pattern (required for every template)

1. Build 2-3 versions with different approaches
2. Run in parallel on dedicated test boards (cloned repos, identical inputs)
3. Deep analysis with 8+ subagents comparing: verdict quality, metadata, execution rigor, cost, engine mechanics
4. Pin winner, disable losers (.disabled/.failed, kept in git)
5. Fork from winner, fix gaps
6. Repeat until full marks
