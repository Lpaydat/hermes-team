# Verifier Profile — Complete Role Diagnosis

**Profile**: `verifier` (`~/.hermes-teams/startup/profiles/verifier/`)
**Sources read**: `SOUL.md`, `config.yaml`, `skills/software-development/adversarial-review/SKILL.md` (v6.0.0) + 3 references (`merge-protocol.md`, `verdict-routing.md`, `probe-patterns.md`), `skills/software-development/dod-verdict/SKILL.md` (v1.0.0)

---

## 1. What the verifier does

The verifier is a **specialist profile** that performs two distinct roles:

| Role | Skill | Domain |
|------|-------|--------|
| **Adversarial code verifier + merge-owner** | `adversarial-review` (mandatory, v6.0.0) | Software development: verify developer card output, gate merges to `main` |
| **DoD (definition-of-done) judge** | `dod-verdict` (v1.0.0) | `loop_engine` converge loops: evaluate design-doc / ADR drafts against a DoD |

### Core identity (from SOUL.md)
> "You are an **adversarial verifier** and the team's **merge-owner**. Your stance from the first message of every review: **the code is broken — prove it**. Every finding must carry evidence you personally verified. You are also the merge gate: nothing from a kanban card reaches main except through you, serialized, with tests re-run on the rebased candidate."

**Four load-bearing principles** (SOUL.md §Stance):
1. **Evidence or silence** — findings without verified evidence aren't filed.
2. **Trace-blind by default** — reviews OUTPUT, not developer reasoning. Opens transcript only on suspected test-tampering.
3. **Never merge without executing post-rebase** — reported green signals have burned production.
4. **Escalate, don't loop** — iteration ≥ 3 → block `needs_input` with `ESCALATE:` + verdict; spec gap → block for tech-lead.

---

## 2. Triggers (when this profile runs)

The verifier is **dispatched by the board**, not self-triggered. Two dispatch paths:

### Path A — Code verification card (adversarial-review)
- A **developer card** completes; its child **review card** (created by the orchestrator via `kanban_chains`) promotes to the verifier.
- The review card body carries: contract_ref, evals_cmd, base SHA, branch_name.
- On re-dispatch after fan-out: the card re-promotes when all `[probe]` worker cards complete (Stage 3 synthesis mode — detected by presence of completed `[probe]` results in context).

### Path B — DoD evaluation card (dod-verdict)
- A `loop_engine` converge loop dispatches the verifier as the independent judge for a design/ADR phase output.
- Triggered by an execution card whose DoD must be checked (card body or `design-council`'s `dod-contract.md`).

### Self-triggered sub-cards
- The verifier dispatches its OWN worker cards (`assignee: "verifier"`) via `kanban_chains` during Stage 2 fan-out — these are `[probe]` cards it later re-promotes from.

---

## 3. Inputs

### 3a. Code verification (adversarial-review)

**Auto-injected from parent developer card completion metadata:**
| Field | Source |
|-------|--------|
| `branch_name` | developer card's git branch |
| `worktree_path` | developer's git worktree (cwd-scoped for session resume) |
| `harness_session_id` | developer's resume session (for fix-card warm resume) |
| `changed_files` | files modified in the diff |

**From the review card body:**
- `contract_ref` — the contract / spec reference
- `evals_cmd` — command to run the test/eval suite
- Base SHA + branch (for delta computation)
- Bead ACs (acceptance criteria) — via `bd show <bead-id>`

**Constraints on worker card bodies (fresh-eyes worker):**
The fresh-eyes AC prover body contains ONLY: contract text + bead ACs + branch/worktree + evals_cmd.
**Forbidden in fresh-eyes body**: prior findings, developer's completion report, trace ledger paths, developer card id — and an explicit ban: *"Do NOT read the developer card, review cards, or their comment threads (`kanban_show` on them is forbidden)."*

### 3b. DoD evaluation (dod-verdict)

| Field | Source |
|-------|--------|
| Phase output to evaluate | execution card's `run.metadata` (direct parent) |
| DoD for the phase | card body, or `design-council`'s `dod-contract.md` |
| `## Loop protocol` footer | names the shared root blackboard card |
| Source brief + ADR draft | for extracting behaviors |

---

## 4. Outputs

### 4a. Verdict (three-state, both skills)

| Verdict | Code verification trigger | DoD equivalent |
|---------|--------------------------|----------------|
| **PASS** | Zero findings at ANY severity AND all ACs verified independently | `dod_met: true` (every item `pass`, every trace `traced`) |
| **FAIL** | Any finding at any severity (incl. bugs the tests miss) | `dod_met: false` (any `latent_defect` / failing item / fabricated cite) |
| **ESCALATE** | Iteration ≥ 3 OR spec gap | `recommendation: "escalate"` |

### 4b. Findings (code verification)

Each finding carries:
- **Severity**: Critical > Important > Minor > Note
- `file:line` anchor
- Evidence: pasted actual test/eval output, OR a repro command, OR a line-anchored contract violation (file:line + quoted contract item)
- The contract item violated
- Header line: `REVIEW-ITERATION: <N>` (the iteration counter lives in this comment line — there is no mutable metadata field)

**Finding severities and their mechanical triggers:**
| Severity | Auto-trigger (mechanical) | Example |
|----------|--------------------------|---------|
| Critical | Failing evals/tests/build; stubs (`TODO/FIXME/pass/NotImplementedError`); mutation not caught; RESOLVED-BY-SKIP; ADR-tamper | "Stub at file:line — function X has no implementation body." |
| Important | `ponytail:` deferred-work; uncaught error-path crash; over-engineering; schema-violating-but-parseable JSON crash | "Deferred work: file:line — marked for later." |
| Note | Uncovered function (no AC references it); minor issues | "Uncovered function: X — not referenced by any AC." |

### 4c. Merge metadata (code verification — completion stamp)

The `kanban_complete` **summary** begins with `PASS`/`FAIL` + one-line evidence digest.

The `kanban_complete` **metadata** carries (minimum):
```json
{
  "verdict": "PASS|FAIL",
  "findings_count": <int>,
  "acs_verified": <int>,
  "dev_tests": "<pass|fail|...>",
  "iteration": <int>,
  "adr_conformance": {
    "status": "violated|clean|skipped",
    "ids": ["ADR-NNN", "..."],          // when violated
    "checked": <int>,                   // when clean
    "reason": "no-docs-adr"             // exactly this token when skipped
  }
}
```

**ESCALATE stamp** (blocked card → no completion): the `kanban_block` reason MUST begin `ESCALATE:` and the block comment carries the verdict fields + session id (block paths record no run metadata; the comment is the durable record).

### 4d. DoD verdict (structured output — dod-verdict)

```json
{
  "dod_verdict": {
    "behaviors": [{"behavior": "...", "brief_citation": "..."}],
    "defect_traces": [{
      "behavior": "...",
      "citation": "...",
      "failure_implication": "CITE + GAP + FAILURE",
      "status": "traced|latent_defect",
      "fabricated": false
    }],
    "dod_met": <bool>,
    "score": <0..1>,
    "design_version_ref": "<slug>",
    "items": {
      "defect_coverage": "pass|fail",
      "mechanism_accuracy": "pass|fail",
      "highest_stakes_depth": "pass|fail",
      "alternatives_steelmanned": "pass|fail",
      "failure_modes_explicit": "pass|fail",
      "consequences_complete": "pass|fail"
    },
    "gaps": [{"item":"...", "issue":"...", "citation":"...", "failure":"...", "severity":"critical|important|minor"}],
    "evidence": [{"text": "<material claim>", "citations": [{"artifact_type": "adr_doc|file_line|probe_result", "locator": "...", "quote?": "..."}], "material": true}],
    "recommendation": "advance|replan|escalate"
  }
}
```
**Constraints**: `recommendation` MUST NOT be `"advance"` unless `dod_met` is true. The engine validates artifact shape — a `latent_defect` blocks advance regardless of `dod_met`. Missing `dod_verdict` key → engine reads `verdict=None`, re-evaluates, escalates after 3 attempts.

---

## 5. Handoffs

### 5a. PASS → (QA) / merge

**Code verification**: PASS does NOT hand off to a "QA" profile by name. The PASS path **merges directly** (the verifier IS the merge gate). After merge, `kanban_complete` closes the review card — the completion boundary is the **kanban→beads writeback** (the verifier is the completion boundary that closes the bead).

*Note on "QA" routing*: The SOUL.md and adversarial-review skill do not name a downstream "QA" consumer. The PASS verdict's consumer is the **bead/kanban system** (writeback) and the **board** (dashboards/audits read completion metadata). If a QA consumer exists, it consumes via board monitoring, not a direct card handoff.

### 5b. FAIL → debugger / developer

The FAIL path creates a **fix card** assigned to `developer`:
```
kanban_create(
  assignee="developer",
  parents=[<your review card>],
  workspace_kind="dir",
  workspace_path=<developer's worktree_path>,
  body="Review-Iteration: <N+1>, Chain-Root: <original dev card id>,
        Resume-Session: <harness_session_id>, Branch: <branch_name>,
        Worktree: <worktree_path>, <pointer to findings comment>,
        <same contract_ref/evals_cmd>"
)
```
- A **fresh review card** is created as the fix card's child (the next verification iteration).
- The explicit `workspace_path` makes the developer's warm resume reachable (resume is cwd-scoped).

### 5c. ESCALATE → tech-lead

- Block own review card `needs_input` with reason beginning `ESCALATE:`.
- Create a **tech-lead escalation card** linking the chain root + all review cards.
- Tech-lead reads accumulated comments, then the trace ledger (trace-first), and re-contracts, switches harness, or abandons.
- Spec gap variant: if contract-vs-INTENT (bead promises wrong thing), tech-lead routes to **product-owner** (who owns bead content). Verifier never re-contracts/amends beads/edits contracts.

---

## 6. Merge protocol

Source: `references/merge-protocol.md`

**Principle**: Nothing from a kanban card reaches `main` except through the verifier. The verifier is the serialized merge gate.

**One-time setup per project**: `bd merge-slot create` (acquire fails with "slot not found" until the slot bead exists).

**Sequence** (non-negotiable):
```bash
bd merge-slot acquire --holder verifier --wait    # exclusive; --wait queues behind current holder
git fetch origin && git rebase origin/main        # rebase card branch in the card's worktree
# conflicts? → release slot, FAIL review, fix card to developer ("rebase + resolve conflicts")
#              conflict resolution is code-writing; verifier never writes code
<run evals_cmd + FULL test suite on rebased candidate>   # NON-NEGOTIABLE
# green → merge (per repo convention: merge/squash to main), push
bd merge-slot release --holder verifier           # ALWAYS release — success or failure
```

**Key rules**:
- Pass `--holder verifier` explicitly (default holder comes from `$BEADS_ACTOR`/git identity — same OS user for every profile).
- Post-rebase execution is the **DoltHub rule**: never trust a green you didn't run yourself on the exact candidate being merged.
- Skip bisection — serialization is the whole strategy at ≤3 concurrent developers.
- Harness-direct work stays governed by tech-lead + user approval (outside verifier scope).

---

## 7. Verdict routing

Source: `references/verdict-routing.md` + SKILL.md §Verdict

```
                    ┌─ Stage 1 fast-fail (Critical) ──┐
                    │                                  ▼
  review card ──────┤                          FAIL → fix card → developer
  promotes          │                                  │
                    ├─ Stage 2 fan-out (swarm) ────────┤
                    │                                  │
                    └─ Stage 3 synthesis ─────┬────────┘
                                              │
                    ┌─────────────────────────┴─────────────────────────┐
                    ▼                         ▼                          ▼
                 PASS                     FAIL                      ESCALATE
            (zero findings,            (any finding,           (iter ≥ 3 OR
             all ACs verified)          any severity)            spec gap)
                │                           │                          │
                ▼                           ▼                          ▼
            MERGE via                  fix card →              block needs_input
          merge-protocol              developer +             (ESCALATE:) +
          (slot/rebase/rerun/         fresh review card       tech-lead card
           merge/push)                                         (PO if intent gap)
                │
                ▼
          kanban_complete →
          bead closed (writeback)
```

**Routing decision logic:**
- **PASS**: zero findings at any severity (Critical/Important/Minor/Note) AND every AC verified independently → merge.
- **FAIL**: any finding at any severity, including edge cases not covered by ACs. "A bug the tests miss is still a bug." → fix card + fresh review card.
- **ESCALATE — iteration cap**: `REVIEW-ITERATION ≥ 3`. Fast-fail iterations DON'T count — at least one full fan-out review must run before escalating. Block own card.
- **ESCALATE — spec gap**: code matches contract but contract is wrong. Block immediately. If contract-vs-INTENT → tech-lead routes to product-owner.

---

## 8. JSON node definitions

### 8a. Code-verification verdict metadata (adversarial-review)

```json
// kanban_complete(summary="PASS/FAIL <digest>", metadata=<below>)
{
  "verdict": "PASS|FAIL|ESCALATE",
  "findings_count": 0,
  "acs_verified": 12,
  "dev_tests": "pass|fail",
  "iteration": 1,
  "adr_conformance": {
    // exactly one of these shapes:
    "status": "violated",
    "ids": ["ADR-001", "ADR-007"]
  }
  // OR
  , {
    "status": "clean",
    "checked": 5
  }
  // OR
  , {
    "status": "skipped",
    "reason": "no-docs-adr"   // exactly this token, not free prose
  }
}
```

**Per-finding structure** (filed in findings comment, `REVIEW-ITERATION: <N>` header):
```json
{
  "severity": "critical|important|minor|note",
  "file": "path/to/file.py",
  "line": 42,
  "evidence": "<pasted actual output | repro command | contract quote>",
  "contract_item": "<quoted contract line violated>",
  "probe_type": "fresh-eyes|static|delta|mutation|synthesis-gap"
}
```

### 8b. DoD verdict (dod-verdict)

See §4d above. Key node:
```json
{
  "dod_verdict": {
    "behaviors": [{"behavior": "<string>", "brief_citation": "<string>"}],
    "defect_traces": [{
      "behavior": "<string>",
      "citation": "<exact source passage>",
      "failure_implication": "CITE + GAP + FAILURE",
      "status": "traced|latent_defect",
      "fabricated": false
    }],
    "dod_met": true,
    "score": 0.85,
    "design_version_ref": "<slug>",
    "items": {
      "defect_coverage": "pass|fail",
      "mechanism_accuracy": "pass|fail",
      "highest_stakes_depth": "pass|fail",
      "alternatives_steelmanned": "pass|fail",
      "failure_modes_explicit": "pass|fail",
      "consequences_complete": "pass|fail"
    },
    "gaps": [{
      "item": "<dod item name>",
      "issue": "<string>",
      "citation": "<string>",
      "failure": "<concrete failure chain>",
      "severity": "critical|important|minor"
    }],
    "evidence": [{
      "text": "<material claim>",
      "citations": [{
        "artifact_type": "adr_doc|file_line|probe_result",
        "locator": "<path:line | id>",
        "quote": "<optional quoted text>"
      }],
      "material": true
    }],
    "recommendation": "advance|replan|escalate"
  }
}
```

### 8c. Kanban_chains fan-out topology (adversarial-review Stage 2)

```json
{
  "goal": "verify <review-card-id>: <one-line contract summary>",
  "chains": [
    [{"assignee": "verifier", "title": "[probe] fresh-eyes AC verification <review-card>"}],
    [{"assignee": "verifier", "title": "[probe] static review <review-card>"}],
    [{"assignee": "verifier", "title": "[probe] delta check iteration <N> <review-card>"}]
  ]
  // NO "after" — verifier IS the synthesizer
  // delta chain present ONLY when iteration ≥ 2
}
```

### 8d. Fix card (adversarial-review FAIL → developer)

```json
{
  "assignee": "developer",
  "parents": ["<review-card-id>"],
  "workspace_kind": "dir",
  "workspace_path": "<developer worktree_path>",
  "body": "Review-Iteration: <N+1>, Chain-Root: <original-dev-card-id>, Resume-Session: <harness_session_id>, Branch: <branch_name>, Worktree: <worktree_path>, <findings-comment-pointer>, <contract_ref>, <evals_cmd>"
}
```

---

## Appendix: The three-stage pipeline (adversarial-review)

```
Stage 1 — INLINE, fast-fail:
  execute (evals_cmd → tests → build → lint/typecheck) + completeness gate
  (stub scan, ponytail-debt, uncovered-function scan)
  → any Critical → verdict FAIL immediately, skip fan-out

Stage 2 — FAN OUT (kanban_chains):
  fresh-eyes AC prover  ∥  static reviewer  ∥  delta checker (iter≥2)
  verifier dependency-parks, STOPs, auto-promotes on worker completion

Stage 3 — SYNTHESIS (on re-dispatch):
  3a. dedupe + detect regressions + repair coverage holes
  3b. probe synthesis gaps (verifier's own judgment — the seams)
  3c. mutation check (3 mutations max, orchestrator-only, restore+re-verify)
  3d. verify-findings gate (re-run repro for EVERY finding; self-verify probes)
  3e. AC checklist gate (re-execute FAILs + 2 passing ACs at minimum)
  → verdict
```

**Sizing gate**: Solo review (single session) allowed ONLY when ALL hold — iteration 1, diff ≤ 2 files / ≤ ~150 lines, no concurrency/IO/trust-boundary surface. Iteration ≥ 2 ALWAYS fans out (independence guarantee).

**Independence principle**: every iteration runs BOTH a delta check AND a fresh-eyes pass from scratch as **separate kanban worker cards with separate contexts** — never one blended session (confirmation bias is the #1 failure mode; ref: Huang et al., "LLMs Cannot Self-Correct Reasoning Yet").

---

## Appendix: probe-patterns.md catalog (9 patterns)

| # | Pattern | Defect class caught |
|---|---------|---------------------|
| 1 | Self-verify before filing | Probe's own expectation is wrong (typo, off-by-one) |
| 2 | Torn-read / non-atomic detection | Two-lock window in concurrent code |
| 3 | Eviction-count verification (set-difference) | Count disagrees with actual removals |
| 4 | Skip-as-fix detection | `@skip`/`xfail`/deletion masking unfixed defects |
| 5 | Fake-binary-on-PATH | Unhandled malformed subprocess output (KeyError on schema-violating JSON) |
| 6 | Normalization-variant probing | Case/whitespace/unicode key-mismatch bugs |
| 7 | Precondition-violating input | Unhashable-value TypeError (probe bug, not code bug) |
| 8 | Probe-input contamination | Shared builder's pad char smuggles in excluded property |
| 9 | Purity-probe self-contamination | `locals()`/`globals()` diff captures probe's own vars |

---

## Appendix: config.yaml highlights

| Setting | Value |
|---------|-------|
| `model.default` | `glm-5.2` (provider: `zai`) |
| `context_length` | 1,000,000 |
| `toolsets` | `hermes-cli`, `kanban`, `kanban_chains` |
| `plugins.enabled` | `kanban_chains`, `skill_enforcer` |
| `skill_enforcer.mandatory` | `adversarial-review` (always loaded) |
| `kanban.max_in_progress_per_profile` | 3 |
| `dispatch_stale_timeout_seconds` | 14400 (4 hours) |
| `rate_limit_delay` | 30 |

**Disabled skills** (37): a large block of general-purpose skills disabled to keep the profile focused — including `qa`, `tdd`, `implement`, `codex`, `domain-modeling`, all `mattpocock/*` skills, etc. The profile is intentionally narrow: verification + merge + DoD judgment only.
