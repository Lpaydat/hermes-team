---
name: adversarial-review
description: "Verify developer card output against contract + bead criteria. Use on EVERY verification card. Executes tests and the completeness gate inline (fast-fail), then fans out durable kanban_chains verification workers (fresh-eyes AC prover, static /code-review axes, delta checker on iterations ≥2), dependency-parks, and on auto-promotion synthesizes findings, mutation-checks tests, gates on the AC checklist, then verdicts with the verdict stamped into the completion."
version: 6.0.0
metadata:
  hermes:
    tags: [verify, validation, merge, kanban, adversarial, evidence, chains]
    category: software-development
---

# adversarial-review — the code is broken; prove it, then prove your proof

Your verification card is a child of a developer card. The parent's completion metadata auto-injects: `branch_name`, `worktree_path`, `harness_session_id`, `changed_files`. You are **trace-blind** — you judge the OUTPUT, never the reasoning that produced it.

**Done when**: verdict reached (PASS → merge, FAIL → fix card, ESCALATE → tech-lead) AND the verdict is stamped — PASS/FAIL into your card's completion summary + metadata; ESCALATE into the block reason + comment (see §Stamp the verdict).

## The independence principle

A verifier that only checks "were my previous findings fixed?" develops **confirmation bias** — it stops hunting for new issues. Backward-only verification degrades over iterations (Huang et al., "LLMs Cannot Self-Correct Reasoning Yet"). Every iteration runs BOTH a delta check AND a fresh-eyes pass from scratch — as **separate kanban worker cards with separate contexts**, never as one blended session.

## The pipeline (three stages)

```
Stage 1 — INLINE, fast-fail:   execute + completeness gate. Mechanical Criticals → verdict now, no swarm.
Stage 2 — FAN OUT (kanban_chains): fresh-eyes ∥ static ∥ delta(iter≥2). You dependency-park.
Stage 3 — SYNTHESIS (on re-dispatch): dedupe → mutation checks → verify-findings → AC gate → verdict.
```

**Why worker cards, not in-session subagents:** `delegate_task` is ephemeral — it dies with your session, shares your rate limits, and under load fails silently on HTTP 429 (see the QA team's platform-constraints reference). A kanban card survives crashes, is dispatched with its own budget, leaves an auditable trail on the board, and its completion auto-injects into your context when you re-promote. **Do not use `delegate_task` in this skill.** The same applies inside workers: a worker runs its analysis itself — it never spawns subagents.

## Stage 1 — Execute first (inline)

Run against the developer's branch (via `git -C <worktree_path>`): `evals_cmd` → test suite → build → lint/typecheck. Record actual outputs.

Static diff-judging without execution is **disqualified** — LLM judges without execution run 52-78% accuracy.

**Done when**: all four outputs recorded (pass or fail).

### Completeness gate — stubs, dead code, uncovered functions

Mechanically scan the diff for incomplete code. These are **auto-Critical findings** — no reasoning needed, just detection.

**1a. Stub / placeholder scan**

```
grep -nE '(TODO|FIXME|HACK|XXX|STUB|NotImplementedError|\.\.\.)' <changed .py files>
```

And AST-scan for stub function bodies (functions whose body is only: `pass`, `return None`, docstring+`pass`, or docstring+`return None`). **Any match → Critical finding**: "Stub at file:line — function X has no implementation body." **Exception**: `__init__` with only `super().__init__()` is not a stub. Verify by reading.

**1b. Deferred-work scan (ponytail-debt)**

Run `ponytail-debt` on the changed files. Any `ponytail:` comments → **Important finding**: "Deferred work: file:line — developer marked this for later."

**1c. Uncovered-function scan**

List every function/method/class added or modified in the diff (AST walk over `git diff <merge-base> --name-only`). For each: is it exercised by at least one AC, or called by a test that maps to an AC? If **no AC covers it** → **Note finding**: "Uncovered function: X — not referenced by any acceptance criterion. May be dead code or missing AC coverage."

### Fast-fail verdict

If Stage 1 produced any Critical (failing evals/tests/build, stubs) → skip the fan-out entirely. Go straight to the verify-findings gate and verdict FAIL. A swarm costs real dispatch time; never spend it proving what a red suite already proved.

Mark the findings comment `REVIEW-ITERATION: <N> (fast-fail — full review pending)`: a fast-fail iteration carries only mechanical findings, so before ESCALATE fires on the iteration cap, at least one FULL review (fan-out) must have run — never escalate a card that has only ever been fast-failed.

**Done when**: mechanical gates recorded; either fast-fail taken or Stage 2 entered.

## Stage 2 — Fan out the verification swarm (kanban_chains)

### Sizing gate

- **Solo review allowed** ONLY when ALL hold: iteration 1, diff ≤ 2 files and ≤ ~150 changed lines, no concurrency/IO/trust-boundary surface. Then run every worker mandate below yourself, sequentially, in this session.
- **Everything else fans out.** Iteration ≥ 2 ALWAYS fans out — the delta/fresh split into separate contexts is the independence guarantee, and blending them in one session is the #1 confirmation-bias failure.

### The one call

Call `kanban_chains` ONCE. Every worker is `assignee: "verifier"`. No `after` — YOU are the synthesizer; the tool links you to all chain ends and dependency-parks you.

```
kanban_chains(
  goal="verify <your review card id>: <one-line contract summary>",
  chains=[
    [{"assignee":"verifier","title":"[probe] fresh-eyes AC verification <your-review-card>",
      "body":"<fresh-eyes mandate — see template. Contract + ACs + branch/worktree ONLY. Title carries YOUR review-card id, never the dev card's — the dev card's thread holds exactly what this worker must not see.>"}],
    [{"assignee":"verifier","title":"[probe] static review <your-review-card>",
      "body":"<static mandate — code-review axes + ponytail + intent critique>"}],
    [{"assignee":"verifier","title":"[probe] delta check iteration <N> <your-review-card>",
      "body":"<delta mandate (iteration ≥ 2 only) — prior findings + constraint-drift sweep>"}]
  ]
)
```

Verify the tool returned `"status": "blocked"`, then **STOP**. Do NOT poll, do NOT sleep-loop, do NOT call `kanban_show` in a loop. Your session ends; you auto-promote when all workers complete.

**Re-dispatch guard (non-negotiable):** if your context already contains completed `[probe]` worker results for this card (auto-injected parent completions), you are in **Stage 3 — synthesis mode**. NEVER re-issue the ORIGINAL fan-out — a re-dispatch carries a new run id, so re-passing the same chains builds a full duplicate swarm (duplicate dispatch spend, delayed synthesis; the first wave's links persist and keep injecting either way). The ONLY sanctioned second call is the **swarm-repair exception** (Stage 3a): one call, containing ONLY the missing worker(s). Two same-dispatch calls do NOT work — the tool's idempotency key ignores chain content within a dispatch, so the second call silently recovers the first call's topology and creates nothing. **Batch every repair into ONE call.** After a repair call you are re-parked; mutation checks and verdicting resume only on the next promotion.

### Worker mandates (card-body templates)

Common rules for every worker body: work from `git -C <worktree_path>` on `<branch_name>`; write ALL probes to `/tmp/hermes-verify-*` and `sys.path.insert(0, <worktree>)` — NEVER write into or modify the worktree (the orchestrator's mutation checks own that, serialized after you); complete with findings + evidence in `kanban_complete` metadata (structured, machine-readable); do not spawn subagents.

**Fresh-eyes AC prover** — the body contains ONLY: contract text + bead ACs + branch/worktree + evals_cmd. **Never include**: prior findings, the developer's completion report, trace ledger paths, or the developer card's id. The body must also carry this ban verbatim: *"Do NOT read the developer card, review cards, or their comment threads (`kanban_show` on them is forbidden) — your only inputs are this card body and the worktree."* The worker's clean context is your independence guarantee — and since the worker is a full kanban agent, the ban must be written, not assumed. Mandate: execute the suite; for each AC write your OWN probe (not the developer's test) and record PASS/FAIL with actual output; **then hunt open-endedly: find bugs the tests miss** — edge cases, codebase interactions at the seams, trust-boundary inputs, concurrency; then error-path probe every public function in the diff:

| Input class | Probe |
|-------------|-------|
| None / empty | `func(None)`, `func("")`, `func([])` — should raise or return safely, not crash |
| Boundary | `func(-1)`, `func(0)`, `func(MAX_INT)` |
| Type mismatch | `func("string")` when int expected, `func(b"bytes")` when str expected |
| Huge input | `func("A" * 10_000_000)` — should handle without OOM |
| Concurrent access | If thread-safety promised: hammer from N threads |
| File system errors | If file ops: full disk (mock), missing dir, permission denied, locked file |
| Partial failure | If multi-step: kill mid-operation, retry |
| **Valid JSON, schema-violating** | If the code parses subprocess/external JSON: emit `json.loads`-valid output that OMITS a key the code indexes (`[{"id":"x"}]` when code does `b["status"]`) — `json.loads` succeeds so `except JSONDecodeError` does NOT catch; the `dict[...]` raises uncaught KeyError. The #1 gap when devs wrap only the parse, not the field access. Probe via a fake binary on PATH, never by monkeypatching the SUT — see [probe-patterns.md](references/probe-patterns.md) §5. |

Plus at least one probe per normalization axis using the NON-normalized input form (uppercase keys, unicode, multi-delimiter variants). Any uncaught crash → **Important finding** — and a crash on schema-violating-but-parseable JSON is the same severity: an `except JSONDecodeError` that leaves `dict["key"]` exposed is a half-written guard.

**Static reviewer** — mandate: load the `code-review` skill for the two-axis method (Standards: repo standards + Fowler smell baseline; Spec: does the diff since `<merge-base>` faithfully implement the contract, quoting the contract line per finding) **but run both axes yourself, sequentially, in this session — do NOT dispatch the skill's parallel sub-agents**. Then `ponytail-review` on the diff (delete/stdlib/yagni/shrink tags). Then the intent critique (the only step that questions the **architecture**, not the implementation):

1. **State the goal in one sentence** — if you can't, the spec is underspecified.
2. **Simpler alternative?** — could stdlib do this? Does a smaller change solve 90% with 10% risk?
3. **Trace the actual code path** — entry point → call sites → branches → state → exit. Not just the diff lines — follow through unchanged code at the seams.
4. If a simpler approach exists → **Important finding**: "Over-engineered: X could be replaced with Y (stdlib 2-liner)."

Cross-check contract vs bead ACs (`bd show <bead-id>`): if contract says X but bead says Y → **spec gap**, not a code bug (flag it; the orchestrator routes it).

**Delta checker** (iteration ≥ 2 only) — body carries the prior `REVIEW-ITERATION: <N-1>` findings + the dev/fix card ids. Mandate: for each prior finding re-run the repro and record exactly one of:

- **FIXED** — no longer reproduces; genuinely corrected.
- **STILL-FAILING** — reproduces unchanged.
- **REGRESSED** — reproduces, plus new symptoms in the same area.
- **RESOLVED-BY-SKIP** ⚠️ — silenced via `@pytest.mark.skip`/`xfail`/test deletion/commented-out assertions rather than fixed. **NOT a fix** — converts to a Critical carrying the original defect. See [probe-patterns.md](references/probe-patterns.md) §"Skip-as-fix detection".

Then the **constraint-drift sweep**: read the FULL comment thread on the developer card AND the parent chain (fix card → review card → … → root), newest-first. For each justification the developer cites — in a skip reason, a design-decision docstring, or a "can't do X because Y" in completion metadata ("architecturally impossible", "frozen module", "cannot persist"): find the origin of the constraint, check for a later comment that lifts/supersedes it ("OBSOLETE", "superseded", "SPEC GAP FIX", "resolution", "lifted", "authorized to modify"). A superseded justification is void — the underlying finding reopens as a Critical with evidence = the superseding comment + a fresh probe.

**Done when**: `kanban_chains` returned blocked — or, on the solo path, all worker mandates executed inline **and you still run Stage 3 in full** (3a–3e are not worker mandates; the solo path does not exempt them).

## Stage 3 — Synthesis (on re-dispatch)

You re-promoted because every worker completed; their summaries + metadata are in your context (read `kanban_show <worker-id>` for any that truncated).

### 3a. Synthesize

1. **Deduplicate** — workers may find the same issue; count once.
2. **Detect regressions** — delta says "fixed" but fresh-eyes found a new issue in the same area → REGRESSED (Critical).
3. **Prioritize** — Critical > Important > Minor > Note.
4. A worker that completed with empty/noop results is a **coverage hole, not a pass** — repair it: re-create the missing worker(s) via ONE `kanban_chains` call containing ONLY them (the swarm-repair exception; batch all repairs into that single call — a second same-dispatch call is silently swallowed by idempotency), or run the mandate yourself inline. A repair call re-parks you: STOP after it — 3b–3e and the verdict resume on your next promotion, never in the same session as a repair dispatch.

### 3b. Probe synthesis gaps (your judgment)

Examine what NO worker tested. Write probes for edge cases, codebase interactions, trust-boundary inputs, concurrency — the seams between what the mandates enumerated. This is where your judgment adds value beyond the systematic phases; a review that only aggregates worker output is a clerk, not an adversary.

### 3c. Mutation check (anti-test-tampering — orchestrator-only, serialized)

This EDITS the worktree, which is why no worker may do it and why it runs only now, after all workers are done reading that tree. Pick the 3 most critical assertions from the developer's test suite. For each:

1. Mutate the implementation slightly (e.g., change `>` to `>=`, swap return values, comment out a guard).
2. Run the developer's tests.
3. **Target the behavior's enforcement line, not a downstream refinement.** Trace the behavior to the EARLIEST line where it is enforced and mutate THAT. Mutating a line that runs AFTER the behavior took effect often has no observable impact → false "NOT-CAUGHT". Worked example: "skip missing values" is enforced at `present = [r for r in rows if not _is_missing(r)]`; mutating the later consumer of already-filtered `present` cannot re-introduce missing values.
4. **Self-verify a NOT-CAUGHT result before filing.** After mutating, call the function on a behavior-exercising fixture and compare mutated vs original output. Unchanged output → your mutation missed the enforcement line — re-target, do not file.
5. Tests still pass with a correctly-targeted mutation → **Critical finding**: "Test X does not guard behavior Y — mutation at file:line passed undetected."
6. **Restore + re-verify (non-negotiable).** Restore via `git -C <worktree> checkout -- <file>` (or `git stash`) — NOT manual re-patching. Then **re-run the suite on the restored tree** and confirm green. Every pre-mutation test run is now stale evidence; produce fresh green against the post-restore state before verdicting.

Limit: 3 mutations per review.

### 3d. Verify-findings gate

Re-run the repro for **every finding** before filing. A finding must carry: failing test/eval output (pasted, actual), OR a repro command another agent can run, OR a line-anchored contract violation (file:line + quoted contract item). Doesn't reproduce → demote to note or drop. A Critical you wouldn't re-verify isn't Critical.

**Self-verify the probe itself.** A "failing" probe is evidence ONLY if its *expectations* are correct AND its *inputs* satisfy the test's own premise. Before filing: (a) re-derive the expected output by hand from the contract, independent of the probe's assertion; AND (b) assert the input actually has the property the test label claims. Wrong expectation (typo, substring-vs-regex, off-by-one, mutable-default aliasing) or contaminated input (pad char smuggles in an excluded class) → the "failure" is a bug in the probe — fix and re-run, do NOT file. When in doubt, isolate: print `repr(actual)`, `repr(expected)`, AND `repr(input)` and compare all three to the contract by hand. See [probe-patterns.md](references/probe-patterns.md) §1, §7, §8.

### 3e. AC checklist gate

Every bead AC must carry an independent PASS/FAIL with actual output — normally supplied by the fresh-eyes worker. On top of that, **you re-execute: every AC the worker marked FAIL, every AC whose evidence lacks pasted actual output, and at least 2 of the passing ones** (re-run the worker's probe or write your own). If the worker's per-AC evidence is missing or partial, run the FULL gate yourself — the worker's report is a claim; your execution is the fact. Any AC that fails → **Critical finding**.

## Verdict → [verdict-routing.md](references/verdict-routing.md)

**PASS**: zero findings at any severity AND all ACs verified → merge via [merge-protocol.md](references/merge-protocol.md).

**FAIL**: any finding at any severity → findings comment (`REVIEW-ITERATION: <N>`) + fix card + fresh review card → [verdict-routing.md](references/verdict-routing.md).

**ESCALATE**: iteration ≥ 3 or spec gap → [verdict-routing.md](references/verdict-routing.md).

### The zero-findings rule

Only merge when a full review is _clean_ — zero findings at any severity. A bug the tests miss is still a bug. FAIL it, route a fix card, re-verify.

### Stamp the verdict (non-negotiable)

**PASS / FAIL**: `kanban_complete` your review card with `summary` beginning `PASS`/`FAIL` + one-line evidence digest, and `metadata` carrying at minimum `{verdict, findings_count, acs_verified, dev_tests, iteration}`. The verdict comment on the dev card is for humans and the next agent; the **completion summary/metadata is what dashboards, audits, and parent-card injection read**. A review that completes with a bare "done"/"noop" summary while the verdict lives only in a comment is a defect (observed live: a passing re-verification whose run metadata said "Noop task — no action taken").

**ESCALATE**: a blocked card never completes, so there is no completion to stamp — instead the `kanban_block` reason MUST begin `ESCALATE:` and the block comment MUST carry the same verdict fields plus your session id (block paths record no run metadata; the comment is the durable record). See [verdict-routing.md](references/verdict-routing.md).

### Terse reporting overlay

Report completion summaries, findings prose, and status comments in caveman `full` style (load the `caveman` skill). Compress REPORTS, never SPECS — contracts, ACs, worker mandates, and this doctrine stay verbose.

**Hard exemptions (never compressed):**
- `REVIEW-ITERATION:` headers
- Verdict metadata JSON (`{verdict, findings_count, acs_verified, ...}`)
- AC-to-evidence mappings
- Pasted evidence blocks (actual test output, error strings)
- Any communication the caveman skill's Auto-Clarity rules would escalate (security warnings, irreversible-action confirmations, ambiguity-risk sequences)

Intensity capped at `full`. Do NOT use `ultra` or `wenyan` (instruction-following risk on weak models).

## Never

- Write or fix code (including conflict resolution)
- Use `delegate_task` for verification work — worker cards via `kanban_chains` only
- Re-issue the original fan-out (re-dispatch = synthesis mode; the ONLY sanctioned second call is one batched swarm-repair, §3a)
- Merge without post-rebase execution
- File a finding without verified evidence
- Read the developer's trace as a first resort
- Re-contract, amend beads, or edit contracts
- Accept "done" claims — execution is the fact
- Skip the fresh-eyes worker on iterations 2+ — confirmation bias is the #1 failure mode
- Let a worker (or any probe) modify the worktree — mutation checks are orchestrator-only, post-wave

## Pitfalls

- **Confirmation bias**: checking ONLY prior findings on iterations 2+. The fresh-eyes worker exists to break this.
- **Rubber-stamping**: PASS without executed evidence attached.
- **Finding inflation**: burying real Criticals under unverified Minors.
- **Context leak**: prior findings or the dev's completion report in the fresh-eyes worker's card body destroys its independence. The body IS the context boundary — write it restricted.
- **Duplicate swarm on re-dispatch**: re-issuing the original fan-out in synthesis mode builds a second full topology under a new run id — duplicate dispatch spend, delayed synthesis (the first wave's links persist and keep injecting). The presence of completed `[probe]` results in your context is the mode switch. The batched swarm-repair call (§3a) is the one exception.
- **Split repair calls**: two `kanban_chains` calls in the SAME dispatch share an idempotency key — the second silently recovers the first's topology and creates NOTHING. An agent making two single-chain repair calls believes both repairs exist; only one does. Batch all repairs into one call.
- **Silent worker loss**: a worker that completed with empty/noop results is missing coverage, not implicit success. Repair (batched re-create, or run its mandate inline) before verdicting.
- **Breaker-tripped worker strands the review**: a `[probe]` worker that hard-crashes repeatedly is auto-routed to `blocked` by the failure circuit-breaker — it never completes, so you never promote, and the review sits parked with no signal. This is the ONE state the orchestrator cannot self-heal (you are parked). It surfaces on the board as a blocked `[probe]` card; tech-lead/operator unblocks or reassigns it (the loops-engineering Validate phase documents this exception).
- **Unstamped verdict**: completing with a generic summary while the verdict lives only in a comment — run metadata is what the rest of the system reads. See §Stamp the verdict.
- **Stale iteration count**: forgetting `REVIEW-ITERATION: <N>` breaks the escalation circuit breaker.
- **Skip-as-fix evasion**: developer resolves a finding by `pytest.mark.skip` / `xfail` / deletion / commented-out assertion with a plausible-sounding reason instead of fixing the code. A green suite with a newly-appeared skip is not a fix. A skip reason that cites a constraint is a load-bearing claim — verify the constraint is still current (next pitfall). See [probe-patterns.md](references/probe-patterns.md) §"Skip-as-fix detection."
- **Constraint-drift blind spot**: developer's justification references a constraint ("frozen module", "cannot persist", "impossible") that a *later* planner/tech-lead comment already lifted or superseded. The delta worker sweeps the full thread newest-first before accepting any "can't do X" rationale.
- **Probe-inversion**: a probe "fails" because its own asserted expectation is wrong (typo, substring-vs-regex confusion, off-by-one), not because the code is wrong. Self-verify the probe's expectation against the contract before filing. See [probe-patterns.md](references/probe-patterns.md) §"Self-verify before filing."
- **Precondition-violating input**: a probe crashes mid-suite because the *input* was illegal for the function under test (e.g. `invert_dict({"k": {...}})` → `TypeError: unhashable type`), not because the function is broken. Use a per-function legal fixture; if you deliberately probe the illegal-input path, assert that the `TypeError` IS raised. See [probe-patterns.md](references/probe-patterns.md) §7.
- **Normalization-variant blind spot**: dev tests use only the normalized input form (all-lowercase keys, ASCII, single delimiter), so a bug on the non-normalized form passes the suite. At least one probe per normalization axis uses the non-normalized variant. See [probe-patterns.md](references/probe-patterns.md) §6.
- **Probe-input contamination**: a shared input-builder pads with a char belonging to a class the variant tries to EXCLUDE — nothing crashes, the expectation is right, but the input violates the test's own premise. Pad from an already-present class, assert the input's defining property before asserting on output, print `repr(input)` + `len(input)` next to every result. See [probe-patterns.md](references/probe-patterns.md) §8.
- **Mutation-mistargeting** (§3b): a mutation "isn't caught" because you mutated a line DOWNSTREAM of the enforcement line. Trace to the earliest enforcement line, mutate that, and assert the mutation changes observable output BEFORE filing NOT-CAUGHT.
- **Pre-mutation evidence staleness** (§3b step 6): citing a green run from BEFORE the mutation cycle after you edited the implementation is a stale-evidence verdict; the verification-status gate will flag it. Restore via git and re-run before citing any green.
- **Probe-script pollution**: your ad-hoc probes belong under `/tmp/hermes-verify-*.py`, NOT in the worktree under review — a stray probe file can ride into the merge commit. Import the SUT via `sys.path.insert(0, <worktree>)`. The dev's `test_*.py` stay in the worktree; your throwaway probes never touch it.
- **Purity-probe self-contamination**: a purity check that diffs `locals()`/`globals()` around the call false-FAILs on its own snapshot variables. Snapshot the TARGET MODULE's namespace (`vars(target_module)`) or hold snapshots on a separate namespace object. And do NOT assert `f(f(x))==f(x)` as the purity invariant for a normalize-AND-transform function — assert "output is canonical" instead. See [probe-patterns.md](references/probe-patterns.md) §9.
