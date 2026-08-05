# tech-lead-execute Workflow — Full Reference

## Trigger

```
Source: card_completed
Conditions:
  - assignee = tech-lead
  - status = done
  - title starts with [spec] OR [ticket-]
```

When a card assigned to tech-lead completes (status=done) and its title
starts with `[spec]` or `[ticket-`, this workflow fires.

## Nodes (5)

### plan
- **Profile:** tech-lead
- **Skill:** loops-engineering
- **Depends on:** nothing (entry node)
- **Title:** `[tl-b] Plan: ${trigger.title}`

Reads the trigger card body. Loads `to-tickets` skill. Decomposes the
spec/ticket into atomic tasks.

Calls `loop_engine` with one phase per atomic task. Each phase has:
- `execution`: `[task]` card → developer builds
- `verifier`: `[verify]` card → verifier checks
- `max_iterations`: 5 per task

loop_engine handles ALL card creation internally. It parks the plan card
until all phases converge (advance/replan/escalate per phase).

**Output metadata:**
```json
{"plan_complete": true, "task_count": N, "phases_converged": N,
 "sizing_summary": "small:N medium:N large:N"}
```

### verify
- **Profile:** verifier
- **Skill:** adversarial-review
- **Depends on:** plan (edge: `plan_complete exists`)
- **Title:** `[verify-b] Integration: ${trigger.title}`

**Phase 1:** Extract EVERY spec requirement. Write behavior tests against
the public interface (CLI, API, library calls). Not implementation details.

**Phase 2:** Attack own tests using 5 principles:
1. Honesty check — does input match what docstring claims?
2. Adversarial thinking — worst input a hostile user provides?
3. Independence — test spec requirements, not assumptions
4. Completeness — every code path tested?
5. Deployment readiness — test fixtures mask deployment-only failures?

**Phase 3:** Run ALL tests (dev's + behavior + attack).

**Phase 4:** Do NOT edit developer's code. Only write tests against it.

**Output metadata:**
```json
{"verdict": "PASS|FAIL|ESCALATE",
 "findings_count": N,
 "behavior_tests_total": N,
 "behavior_tests_passed": N,
 "behavior_test_file": "path",
 "production_mode_tested": true}
```

### fix
- **Profile:** developer
- **Skill:** (none)
- **Depends on:** nothing (reached via conditional edge from verify/re-verify)
- **Title:** `[fix-b] Behavior findings: ${trigger.title}`

Reads the behavior test file from verify output. Fixes HIS code so ALL
tests pass. Does NOT modify verifier's tests. Runs ALL tests.

**Output metadata:**
```json
{"fixed": true, "findings_fixed": N,
 "all_tests_pass": N, "total_tests": N}
```

### re-verify
- **Profile:** verifier
- **Skill:** adversarial-review
- **Depends on:** nothing (reached via edge from fix)
- **Title:** `[re-verify-b] Integration: ${trigger.title}`

**Phase 1:** Re-run all behavior tests from the first verify. Every
previously-failing test must now PASS.

**Phase 2:** Attack AGAIN using same 5 principles, but checks for NEW
bugs introduced by the fix. Did the fix close one door but open another?

**Phase 3:** Run ALL tests (old + new).

**Phase 4:** Do NOT edit code.

**Output metadata:** Same schema as verify.

### close
- **Profile:** tech-lead
- **Skill:** loops-engineering
- **Depends on:** nothing (reached via conditional edge from verify/re-verify)
- **Title:** `[tl-b] Close: ${trigger.title}`

Reads both verify and re-verify verdicts.
- PASS → verdict=merged
- ESCALATE → verdict=escalated

**Output metadata:**
```json
{"verdict": "merged|escalated",
 "tasks_planned": N, "tasks_completed": N,
 "escalate_reason": ""}
```

## Edges (6)

| From | To | Condition | Max Iterations |
|------|----|-----------|----------------|
| plan | verify | `${nodes.plan.output.plan_complete}` exists | — |
| verify | close | `${nodes.verify.output.verdict}` == 'PASS' OR == 'ESCALATE' | — |
| verify | fix | `${nodes.verify.output.verdict}` == 'FAIL' | 10 |
| fix | re-verify | (none — always fires when fix completes) | 10 |
| re-verify | close | `${nodes.re-verify.output.verdict}` == 'PASS' OR == 'ESCALATE' | — |
| re-verify | fix | `${nodes.re-verify.output.verdict}` == 'FAIL' | 10 |

## ASCII Diagram

```
TRIGGER: card_completed
         assignee=tech-lead, status=done
         title starts with [spec] OR [ticket-]
                        │
                        ▼
              ┌─────────────────────────────┐
              │  PLAN                       │
              │  profile: tech-lead         │
              │  skill: loops-engineering   │
              │                             │
              │  Reads trigger card body.   │
              │  Loads to-tickets skill.    │
              │  Decomposes spec/ticket     │
              │  into atomic tasks.         │
              │                             │
              │  Calls loop_engine with:    │
              │  ┌─────────────────────┐    │
              │  │ loop_engine         │    │
              │  │                     │    │
              │  │ For EACH task:      │    │
              │  │  creates dev card   │    │
              │  │  creates verify card│    │
              │  │  developer builds   │    │
              │  │  verifier checks    │    │
              │  │  advance → next     │    │
              │  │  replan → re-execute│    │
              │  │  escalate → stop    │    │
              │  │  max_iterations: 5  │    │
              │  │                     │    │
              │  │ Parks plan card     │    │
              │  │ until ALL phases    │    │
              │  │ converge            │    │
              │  └─────────────────────┘    │
              │                             │
              │  Completes with:            │
              │  {plan_complete: true,      │
              │   task_count: N,            │
              │   phases_converged: N}      │
              └──────────┬──────────────────┘
                         │
                    condition:
              plan_complete exists?
                         │
                         ▼
              ┌─────────────────────────────┐
              │  VERIFY                     │
              │  profile: verifier          │
              │  skill: adversarial-review  │
              │                             │
              │  Phase 1: Extract EVERY     │
              │  spec requirement → write   │
              │  behavior tests against     │
              │  public interface.          │
              │                             │
              │  Phase 2: Attack own tests  │
              │  using 5 PRINCIPLES:        │
              │  1. Honesty check           │
              │     (does input match       │
              │      what docstring claims?) │
              │  2. Adversarial thinking    │
              │     (worst input?)          │
              │  3. Independence            │
              │     (test spec, not          │
              │      assumptions)           │
              │  4. Completeness            │
              │     (every code path?)      │
              │  5. Deployment readiness     │
              │     (fixtures mask prod      │
              │      failures?)             │
              │                             │
              │  Phase 3: Run ALL tests     │
              │  (dev's + behavior + attack)│
              │                             │
              │  Phase 4: Do NOT edit code  │
              │                             │
              │  Output:                    │
              │  {verdict: PASS|FAIL|ESCALATE,│
              │   findings_count: N,        │
              │   behavior_tests_total: N,  │
              │   behavior_tests_passed: N, │
              │   production_mode_tested: T}│
              └──────┬──────────────┬───────┘
                     │              │
        verdict=PASS │              │ verdict=FAIL
        or ESCALATE  │              │ (max 10 iterations)
                     ▼              ▼
           ┌──────────────┐  ┌─────────────────────┐
           │  CLOSE       │  │  FIX                │
           │  profile:    │  │  profile: developer │
           │  tech-lead   │  │  skill: (none)      │
           │  skill:      │  │                     │
           │  loops-eng   │  │  Reads behavior     │
           │              │  │  test file from     │
           │  Reads both  │  │  verify output.     │
           │  verify +    │  │                     │
           │  re-verify   │  │  Fixes HIS code so  │
           │  verdicts.   │  │  ALL tests pass.    │
           │              │  │  Does NOT modify    │
           │  PASS →      │  │  verifier tests.    │
           │   merged     │  │                     │
           │  ESCALATE →  │  │  Runs ALL tests.    │
           │   escalated  │  │                     │
           │              │  │  Output:            │
           │  Output:     │  │  {fixed: true,      │
           │  {verdict:   │  │   findings_fixed:N, │
           │   "merged"|  │  │   all_tests_pass:N, │
           │   "escalated"│  │   total_tests:N}    │
           │  }           │  └─────────┬───────────┘
           └──────────────┘            │
                                 (no condition)
                                       ▼
                           ┌─────────────────────────┐
                           │  RE-VERIFY              │
                           │  profile: verifier      │
                           │  skill: adversarial-    │
                           │         review          │
                           │                         │
                           │  Phase 1: Re-run all    │
                           │  behavior tests from    │
                           │  first verify.          │
                           │                         │
                           │  Phase 2: Attack AGAIN  │
                           │  Same 5 principles but  │
                           │  checks for NEW bugs    │
                           │  introduced by the fix. │
                           │  Did fix open a new     │
                           │  door while closing?    │
                           │                         │
                           │  Phase 3: Run ALL tests │
                           │                         │
                           │  Phase 4: Do NOT edit   │
                           │                         │
                           │  Output: same schema    │
                           │  as verify.             │
                           └─────┬────────────┬──────┘
                                 │            │
                   PASS or       │            │ FAIL
                   ESCALATE      │            │ (back to FIX,
                                 │            │  max 10 iters)
                                 │            │
                                 ▼            ▼
                          ┌──────────┐   ┌────────┐
                          │  CLOSE   │◄──┤  FIX   │
                          │ (above)  │   │ (loop) │
                          └──────────┘   └────────┘
```

## Loop Behavior

- `verify → fix → re-verify → fix → re-verify → ...` until PASS/ESCALATE
  or 10 iterations exhausted
- Each FIX back-edge is capped at max_iterations=10
- The loop exits on PASS (goes to CLOSE as merged) or ESCALATE (goes to
  CLOSE as escalated)

## Inside loop_engine (plan node)

loop_engine is called by the plan node. For each atomic task:

1. Creates `[task]` card (assignee=developer) with the task body
2. Creates `[verify]` card (assignee=verifier) with verification criteria
3. Developer builds → verifier checks
4. Outcomes per phase:
   - advance → next task
   - replan → re-execute same task (developer gets another try)
   - escalate → stop, tech-lead intervenes
5. max 5 iterations per task
6. Plan card stays parked (todo status) until ALL tasks converge

loop_engine handles ALL card creation internally. The plan node body
explicitly says: "DO NOT call kanban_chains. DO NOT call kanban_create."
