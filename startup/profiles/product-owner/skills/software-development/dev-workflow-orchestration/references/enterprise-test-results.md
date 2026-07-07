# Enterprise Test Results (Tests 10b-21, Jul 2026)

## The breakthrough: 3-role pipeline works (Test 10b)

**Enforcement stack** (all 3 needed):
1. Disable `delegation`, `file`, `code_execution` on tech-lead
2. Remove harness-direct option from loops-engineering skill entirely
3. Delete the `claude` symlink (prevents Claude Code one-shot shortcut)

Result: tech-lead created developer + verifier kanban cards for the first time.
Developer used pi (GLM-4.5-air), verifier ran adversarial-review v4.0.0.

## The failure-fix loop works (Test 14)

GLM 4.5-air produced a real bug: syslog process field returned `"su[1234]"` not `"su"`.
Developer's test used substring check (`'su' in result`) — masked the bug.
Verifier caught it via equality probe.

Iteration 1: FAIL → fix card → developer warm-resumed pi → fix applied.
Iteration 2: PASS — delta check confirmed fix, fresh-eyes found no new bugs.

**Why GLM 4.5-air is essential**: GLM 5.2 produced clean code in Tests 10b, 12, 13.
Only the weaker model (4.5-air) produced bugs that exercised the full loop.

## Crash recovery at developer level (Test 15)

Developer task showed 3 runs (68→69→70) — auto-reclaim fired twice. The developer
profile survived crashes and completed on the 3rd attempt with 20 tests + trace saved.
Verifier then ran 42 independent probes — PASS.

**Key insight**: crash recovery is transparent to the pipeline. The verifier doesn't
know the developer crashed — it just sees the completed work and verifies it independently.

## Circular dependency prevention (Test 19)

Attempted to create A→B→A circular deps in beads. bd silently rejected the reverse
edge. Only B was "ready" (no blockers). The cron dispatched B correctly, and A was
blocked. No infinite loop, no crash.

## Consistency data (Tests 10b-21)

| Test | Dev model | Dev tests | Verifier probes | Iterations | Verdict |
|------|-----------|-----------|-----------------|------------|---------|
| 10b | 4.5-air | 19 | 18 | 1 | PASS |
| 11 | 5.2 | 21 | 17 (tech-lead) | 1 | PARTIAL |
| 12 | 5.2 | 34 | 37 | 1 | PASS |
| 13 | 4.5-air | 36 | 38 | 1 | PASS |
| 14 | 4.5-air | 27 | 30 | 2 | PASS (fix loop) |
| 15 | 4.5-air | 20 | 42 | 1 | PASS (2 crashes) |
| 16 | 4.5-air | 24 | — | 1 | PASS |
| 17 | 4.5-air | 19 | 42 | 1 | PASS |
| 18 | 4.5-air | 6 | 10 | 1 | PASS |
| 21a | 4.5-air | — | — | 1 | PASS |
| 21b | 4.5-air | — | — | 1 | PASS |
| 21c | 4.5-air | — | — | 1 | PASS |

## Test-tampering detection

The verifier caught two types of test-tampering across Tests 9-14:
1. **Substring instead of equality** (Test 14): `'su' in result` instead of `result == 'su'`
2. **Keys-only assertion** (Test 9): test wrote a comment but only asserted keys survived, not the comment

Both are classic generator cheats — the test appears to pass but doesn't actually verify the AC.
The AC checklist gate (step 5 of adversarial-review) catches these because the verifier writes
its OWN probe for each AC, not the developer's test.

## Spec gap detection (Test 13)

Verifier detected PRD said "minimum 8 chars" but bead AC said "minimum 6 chars".
Resolved correctly: "bead ACs beat PRD prose" — the bead is the contract, not the PRD.
The verifier did NOT escalate to tech-lead — it resolved the ambiguity itself by treating
the bead as authoritative. This is reasonable but technically violates the doctrine
(spec gaps should escalate). A future improvement: add explicit "if PRD and bead conflict,
escalate to tech-lead" to the verifier skill.

## 429 Rate Limit Handling (identified across multiple tests)

Z.AI returns HTTP 429 ("temporarily overloaded") frequently under concurrent load.
Current Hermes behavior: 3 retries with exponential backoff (~2.3s, 4.7s, 10.5s),
then the agent session dies → auto-reclaim (1-3 min) → fresh session.

**Evidence** (from t_ef1ffba4 log, battle-5 era):
```
⚠️ API call failed (attempt 1/3): RateLimitError [HTTP 429]
⏳ Retrying in 2.3s (attempt 1/3)...
⚠️ API call failed (attempt 2/3): RateLimitError [HTTP 429]
⏳ Retrying in 4.7s (attempt 2/3)...
⚠️ API call failed (attempt 3/3): RateLimitError [HTTP 429]
⚠️ Provider unreachable — switching to fallback provider...
❌ API failed after 3 retries
```

**Problem**: For transient Z.AI rate limits (typically clear in 30-60s), 3 retries over ~17s
isn't enough. The task dies and burns a full reclaim cycle (~2-3 min wasted).

**Recommended fix** (IDENTIFIED Jul 2026, **DEPLOYED**):
- `agent.api_max_retries: 10` in config.yaml (was 3) — **APPLIED**
- `rate_limit_delay: 30` on all profiles' model config (was ~2-5s) — **APPLIED**
- Board scanner Layer 3 auto-unblocks crash-exhausted tasks after 2-min cooldown — **DEPLOYED**

This gives ~5 minutes of in-session resilience before crashing, plus the scanner
auto-unblocks crash-exhausted tasks so the dispatcher retries. Gateway restart required
for config changes to take effect.

## Test 20 (5-slice dependency chain) — ✅ COMPLETE, SELF-HEALING PROVEN

Set up: 5 beads (KV core → file persistence → TTL → CLI → benchmarks) with strict
dependency chain. Slices 1-2 completed successfully (3-role pipeline, dev + verifier).

### Slice 4 — deep failure-fix loop (3 iterations)

The deepest fix loop tested. GLM 4.5-air produced increasingly subtle bugs:

**Iteration 1 — FAIL (hollow tests):** T15/T16/T19 (TTL cross-process tests) were
SKIPPED, not real tests. Also `/tmp/` path violations. Verifier: "a skip is not a test."

**Iteration 2 — FAIL (spec gap):** Developer fixed hollow tests but TTL expiry wasn't
persisting across CLI processes. Slice 3's `ttl.py` deliberately dropped `_expiry` on
save/load. Verifier caught via real cross-process subprocess probes.

**Iteration 3 — PASS:** Developer implemented composite format `{"data":{...},"expiry":{...}}`.
Verifier verified with **negation proof** — broke `ttl.save()` in scratch copy, confirmed
all 3 probes detected the break. 104/104 tests (0 skipped).

### Crash + deadlock + self-healing

Slices 3 and 5 crashed: tech-lead hit 429 storms, crashed twice each, exhausted
max_retries=2. Board froze — no running, no ready, just blocked + todo.

**Self-healing deployed and PROVEN**: board scanner cron detected the crashes,
auto-unblocked crash-exhausted tasks (after 2-min cooldown), escalated the
needs_input blocks, and logged incidents. Board unfroze. All 5 slices completed.

### Concurrent verifier session race (NEW failure mode)

Two verifier sessions claimed the same parent review simultaneously. Both filed FAIL
verdicts and created fix chains — producing **duplicate cards**:

- Session A: created fix card assigned to **verifier** (role violation) → blocked itself
- Session B: created fix card assigned to **developer** (correct) → canonical chain

Session A then posted misleading "SUPERSEDED — do not work" comment on the CORRECT chain.
Tech-lead resolved it: posted authoritative override comment, archived the dead chain.

**Root cause**: no merge-slot-style lock on FAIL verdict filing. Same race class as
the cron duplicate (Test 7). The self-healing scanner detected the deadlock and escalated
to tech-lead, who resolved it autonomously.

**Resolution pattern (proven)**:
1. Verifier blocks itself on role violation ("I constitutionally cannot write code")
2. Scanner detects deadlock → escalates to tech-lead
3. Tech-lead reads conflicting comments, determines canonical chain
4. Tech-lead posts override comment, archives dead chain
5. Canonical chain proceeds normally

### Final tally (Test 20)

| Slice | Module | Tests | Iterations | Verdict |
|-------|--------|-------|------------|---------|
| 1 | kvstore.py | 18 | 1 | PASS |
| 2 | persistence.py | 26 | 1 | PASS |
| 3 | ttl.py | 28 | 1 | PASS |
| 4 | cli.py | 30 | **3** | PASS (fix loop + race) |
| 5 | benchmark.py | 19 | 1 | PASS |
| **Total** | **5 modules** | **121** | | **All done** |

## What was NOT tested

1. **Iteration cap escalation (≥4)** — GLM 4.5-air passed on iteration 2 in Test 14,
   and on iteration 3 in Test 20. Neither hit the ≥4 escalation circuit breaker.
2. **Merge slot serialization** — bd merge-slot not tested
3. **Long-running loops (>12hr)** — identified as a future test category
4. **Sandboxing** — identified as infrastructure gap (no filesystem isolation)
5. **HITL gateway notification** — scanner stubs this as TODO; needs gateway integration
6. **Completeness gate (v5.0.0)** — the new step 2 (stubs/dead-code/uncovered scan) was
   added AFTER Test 20. It has not yet been exercised in a live test. Future test:
   inject a stub function into a slice and verify the verifier catches it.
7. **Scrutinize + error-path + mutation testing (v5.1.0)** — steps 5a/5b/5c added after
   Test 20. Not yet exercised in live test. Future test: inject over-engineered code
   (5a), a function that crashes on None (5b), and a test that passes despite mutation (5c).

## Enterprise verdict (Jul 2026)

**ENTERPRISE-GRADE.** The full 3-role pipeline (tech-lead → developer → verifier)
works end-to-end. The system proved resilient even when agents made mistakes
(concurrent sessions, role violations, test-tampering). Every failure was caught
by either the verifier doctrine, the self-healing scanner, or tech-lead intervention.

**Proven capabilities**:
- ✅ 5-slice dependency chains with sequential dispatch (Test 20, 121 tests)
- ✅ Failure-fix loops at depth (3 iterations, Test 20 Slice 4)
- ✅ Crash recovery with auto-reclaim (Tests 6, 15)
- ✅ Self-healing deadlock detection + escalation (Test 20, concurrent verifier race)
- ✅ Spec gap detection (Test 13)
- ✅ Test-tampering detection (Tests 9, 14)
- ✅ Zero-token automation via cron scripts (Tests 7, 20-21)
