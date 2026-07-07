# Architecture: 3-Role Separation

This is the core architecture that prevents the sycophancy trap (an agent grading its own work). Three roles, three context windows, three profiles. They communicate exclusively through the kanban board — never directly.

## Role separation (critical)

| Role | Profile | Does | Never Does | Model |
|------|---------|------|------------|-------|
| **Front Door** | `product-owner` | Grills user, writes PRD, decomposes into beads, prioritizes, observes | Writes code, creates dev/verifier cards, interferes with loops | GLM 5.2 |
| **Planner** | `tech-lead` | Contracts bead → technical design, creates dev/verifier cards, reads traces, iterates | Writes code, grades code, runs to-prd/to-issues | GLM 5.2 |
| **Generator** | `developer` | Invokes coding harness (`pi`/`zz`), runs mechanical gates (tests/lint), captures trace | Grades quality, merges, touches contract | GLM 5.2 (governs) → **harness model writes code** |
| **Verifier** | `verifier` (was `reviewer`) | Executes tests independently, adversarial probes, `/review` + `ponytail-review`, two-phase protocol, merges on pass / creates fix card on fail | Writes code, touches contract | GLM 5.2 |

### Why "verifier" not "reviewer" (research-backed, Jul 2026)

The profile does BOTH dynamic verification (runs tests) AND static review (adversarial diff). ISTQB defines "review" as a *subset* of verification (static only, no execution). "Verifier" is broader and more accurate.

Academic consensus: 6 of 11 surveyed papers use "verifier" (generator-verifier pattern). Industry: Anthropic uses "evaluator-optimizer", LangGraph uses "critic", banking/finance uses "maker-checker". All describe the same pattern; "verifier" is the most recognized cross-domain term.

The `/review` skill (mattpocock) is a **tool the verifier uses**, not a role name. It provides the static analysis layer (standards + spec axes on git diffs). The verifier's full protocol lives in the `adversarial-review` skill (v5.1.0).

## The two-phase verification protocol (adversarial-review v5.1.0)

The verifier's core innovation: every iteration runs BOTH a delta check AND a fresh-eyes pass. This prevents **confirmation bias** — the tendency for a verifier to stop hunting for new issues after checking whether prior findings were fixed (Huang et al., "LLMs Cannot Self-Correct Reasoning Yet").

```
Verifier receives card (iteration N)
  │
  ├─ 1. EXECUTE: tests + build + lint (dynamic verification)
  │
  ├─ 2. COMPLETENESS GATE (mechanical, v5.0.0):
  │   ├─ 2a. Stub scan: grep TODO/FIXME/NotImplementedError + AST pass/return None → Critical
  │   ├─ 2b. Deferred-work scan: ponytail-debt markers → Important
  │   └─ 2c. Uncovered-function scan: AST extract functions → cross-ref vs ACs → Note
  │
  ├─ 3. TWO-PHASE PROTOCOL:
  │   ├─ Phase A: Delta check (iterations 2+, skip on 1)
  │   │   └─ Re-run prior findings' repros → FIXED / STILL-FAILING / REGRESSED
  │   ├─ Phase B: Fresh-eyes subagent (every iteration, parallel with C)
  │   │   └─ delegate_task, ZERO prior context — only contract + ACs + diff
  │   │   └─ Executes tests, writes own probes per AC, discovers bugs
  │   └─ Phase C: Static analysis (parallel with B)
  │       └─ /review (standards + spec axes) + ponytail-review (complexity)
  │
  ├─ 4. SYNTHESIZE: deduplicate, detect regressions, prioritize
  ├─ 5. PROBE GAPS + INTENT (v5.1.0):
  │   ├─ 5a. Scrutinize: should this exist? Simpler alternative? (scrutinize skill)
  │   ├─ 5b. Error-path probing: None/empty/huge/concurrent/file errors per public function
  │   └─ 5c. Mutation check: mutate 3 critical assertions, verify tests catch the mutation
  ├─ 6. VERIFY-FINDINGS: reproduce every finding
  ├─ 7. AC CHECKLIST GATE: independent probe per bead AC
  └─ 8. VERDICT:
      PASS → merge (serialized, post-rebase execution)
      FAIL → fix card → developer (warm resume, NOT tech-lead)
      ESCALATE → tech-lead (iteration ≥ 3 or spec gap)
```

### Finding routing

```
Verifier FAIL (code bug)     → fix card → developer (warm resume harness)
  → NOT tech-lead — keeps the loop tight, no planner overhead per iteration
Verifier FAIL (spec gap)     → escalate to tech-lead immediately
  → tech-lead routes to PO if bead intent is wrong
Verifier iteration ≥ 3       → escalate to tech-lead (circuit breaker)
```

### The AC checklist gate (prover-verifier pattern)

| Step | Who | What |
|------|-----|------|
| **Write ACs** | PO (in bead) | Checkbox items — what the slice must deliver |
| **Provide proof** | Developer (completion report) | Maps each AC to test + output — a **claim** |
| **Re-verify each** | Verifier (step 7) | Writes own probe, executes independently — the **fact** |

### 5-layer static checking (v5.1.0)

| Layer | Question | Tool | Step |
|-------|----------|------|------|
| Completeness | "Is anything stubbed or uncovered?" | AST scan + ponytail-debt | 2 |
| Standards | "Is the code well-written?" | `/review` | 3C |
| Spec | "Did the code meet the contract?" | `/review` | 3C |
| Complexity | "Is the code over-engineered?" | `ponytail-review` | 3C |
| Intent | "Should this exist at all?" | `scrutinize` | 5a |
| Error paths | "What crashes on bad input?" | Error-path probes | 5b |
| Mutation | "Do tests actually guard behavior?" | Mutation testing | 5c |
| Criteria | "Does this slice deliver what was asked?" | AC probes | 7 |

## The correct flow

```
PO grills user → PO writes PRD (full context, in-session)
→ PO runs to-issues → ALL beads + dependencies created at once (persistent)
→ Session ends → PO forgets → beads REMEMBER

CRON loop (zero-token auto-dispatch.sh):
→ bd ready → if nothing ready, exit silently
→ check ready+running quota → if at cap, exit silently
→ create ONE kanban card (idempotency-key dedup) for tech-lead
→ Tech-lead runs loops-engineering on that bead → dev/verifier cards
→ Loop completes
→ Next cron tick → repeat
```

## Model separation

The harness uses a DIFFERENT (weaker) model than the governance layer. If the Generator were also GLM 5.2, the verifier (also GLM 5.2) would be reviewing its own cognitive twin — the adversarial stance weakens.

- Governance (tech-lead, developer, verifier): GLM 5.2
- Generation (harness: pi/zz): GLM 4.5-air or GLM 4.7 (weaker, produces bugs the verifier catches)

## Crash recovery model

| Crash Level | State Location | Recovery Mechanism |
|-------------|---------------|-------------------|
| **Harness crash** (pi/zz dies) | Harness session file | Developer warm-resumes: `pi --session <id>` |
| **Developer crash** (Hermes dies) | Kanban card (status=running, claim lock) | Dispatcher reclaims after stale timeout → re-dispatches → new developer reads comment thread + resumes harness session |
| **Verifier crash** | Kanban card (status=running) | Same as developer — reclaim + re-dispatch |
| **Tech-lead crash** | Kanban card + trace ledger | Re-dispatch reads prior comments + trace |

**Verified (Battle Test 6, Jul 2026)**: Auto-reclaim fires within 1-3 min of process death. New agent independently re-verifies all prior work — does NOT trust crashed run's claims.

## Battle-tested findings (Jul 2026)

### The cheat that invalidated Tests 1-4
PO wrote full contracts into task bodies + manually unblocked reviewer mid-loop. Both are cheats. Correct: PO gives tech-lead ONLY the goal + workspace path. Tech-lead plans autonomously.

### What the REAL test (Test 5R) proved
3 slices, 92 tests, 8 defects found. pi harness (GLM 4.5-air) produced bugs that the verifier (GLM 5.2) caught. Failure-fix loop worked end-to-end: verifier FAIL → fix card → developer warm-resume → harness fix → re-verify → PASS.

### Cron duplicate prevention (Test 7)
`--idempotency-key "bead-<id>"` + ready/running quota check. Tested: double-fire produces zero duplicates.

### Full 3-role pipeline (Test 10b, Jul 2026)
First time ALL 3 profiles worked together: tech-lead created dev + verifier cards, developer invoked pi (GLM 4.5-air), verifier ran adversarial-review v4.0.0. 19 dev tests + 18 verifier probes = 37 green.

### Failure-fix loop with verifier profile (Test 14, Jul 2026)
Verifier caught syslog process field bug ("su[1234]" vs "su"), detected developer's test-tampering (substring instead of equality), created fix card → developer warm-resumed → iteration 2 PASS with delta + fresh-eyes.

### Crash recovery at developer level (Test 15, Jul 2026)
Developer task showed 3 runs (68→69→70) — survived 2 crash recoveries. Verifier then ran 42 probes — PASS. Crash recovery is transparent to the pipeline.

### `/review` and `ponytail-review` integration
`/review` (mattpocock) is a **tool** the verifier uses for static analysis — not a role name. It checks git diffs along Standards + Spec axes against `contract.md` and bead acceptance criteria (NOT the PRD — too high-level). `ponytail-review` adds the Complexity axis (over-engineering, dead code, YAGNI). Together they form the 4-layer static checking in Phase C of the verifier's two-phase protocol.

### 429 rate-limit behavior (identified Jul 2026)
Hermes retries 429s 3 times (~17s), then the agent dies → auto-reclaim (1-3 min). For Z.AI's transient rate limits (typically clear in 30-60s), this wastes a full reclaim cycle. **Recommended config fix**: `api_max_retries: 10`, `rate_limit_delay: 60`, `max-retries: 5` on kanban tasks. This gives ~10 min of in-session resilience before crashing.
