# Tech-Lead Profile — Role Diagnosis

> Source: `~/.hermes-teams/startup/profiles/tech-lead/` — SOUL.md, config.yaml, all skills, scripts, cron jobs, MEMORY.md, and the loops-engineering reference set.

## 0. Discrepancy note (skills named in the task)

The task asked for `dev-dispatch`, `loops-engineering`, and `code-review` skills. On the actual tech-lead profile:

- **`loops-engineering`** — EXISTS. It is the mandatory, force-loaded skill (`skill_enforcer.mandatory`). This is the core of the role.
- **`dev-dispatch`** — DOES NOT EXIST on tech-lead. It is a **product-owner** skill (`software-development/dev-dispatch`). The PO uses it to pre-create tech-lead cards for ready beads. Tech-lead does not run it.
- **`code-review`** — DOES NOT EXIST as an installed skill on tech-lead. The two code-review skills present are **`requesting-code-review`** and **`receiving-code-review`** (obra/superpowers lineage). Both are explicitly **deprecated for the kanban-native loop** — the `verifier` profile owns all validation. The `validation-reference.md` states: "In the kanban-native loop the tech-lead never dispatches reviewers."

The remaining skills present: `ad-hoc-verification` (fresh-evidence probe scripts), `computer-use` (generic desktop automation, not role-specific).

---

## 1. What tech-lead does

Tech-lead is an **autonomous planner**. Its one job: **turn intent into a validated, merged implementation — without ever writing code.**

The role is built on strict three-role separation:

| Role | Profile | Rule |
|------|---------|------|
| **Planner** | tech-lead (you) | Turns intent into spec/contract. **Never touches code.** |
| **Generator** | `developer` | Drives a coding harness (pi/claude/codex/opencode). Writes everything. **Forbidden from grading own work.** |
| **Evaluator** | `verifier` | Adversarial review — told from message 1 the code is broken, prove it. Fans out `[probe]` worker cards. |

The loop has **five phases**: Discover → Plan → Execute → Validate → Iterate (+ Reflection after completion).

- **Discover**: index codebase (CodeGraph), read conventions (`AGENTS.md`, `CONTEXT.md`, `CODING_STANDARDS.md`, ADRs), scan beads/PRs/tests/kanban.
- **Plan**: grill the user one question at a time → produce PRD + ADRs + glossary → negotiate a **contract** (testable assertions, ~20–27 for small tasks) → build evals → decompose into vertical slices → right-size gate → publish to beads → write 3-file crash state (`contract.md`, `progress.md`, `log.md`). **This is where human-in-the-loop ends.**
- **Execute**: call `kanban_chains` to atomically create developer + verifier cards, link tech-lead as dependent on the verifier, then STOP (block with `kind=dependency`). Do not poll.
- **Validate**: **wait and monitor.** Read the verifier's stamped verdict (`PASS`/`FAIL`/`ESCALATE`). The verifier owns ALL validation; tech-lead never runs tests, writes probes, or judges quality.
- **Iterate**: act only on **ESCALATE** (iteration ≥ 3 or spec gap). The FAIL→fix→re-verify loop runs without tech-lead.

Core stances (from SOUL.md):
- Never accept "done" without proof — the verifier's verdict is the signal, not the developer's claim.
- Execute autonomously after plan approval.
- Validate strictly, never self-grade.
- **Never write code.** Writing code destroys role separation. If no developer path exists → BLOCK, don't code.

---

## 2. Triggers — who/what activates tech-lead

Tech-lead is activated by **four mechanisms** (loop-theory.md, "Autonomous Operation"):

1. **Direct chat** (`hermes -p tech-lead`) — interactive contracting/planning with the user.
2. **Kanban task + dispatcher** — a task assigned to `tech-lead`; the gateway dispatcher claims it on a ~60s tick and spawns the profile. **This is the primary autonomous path.**
3. **Kanban swarm** — parallel workers → verifier → synthesizer pattern.
4. **Cron job** — scheduled discovery.

### The beads→kanban bridge (who creates the tech-lead task)

There are **two sources** of tech-lead task cards, and they are NOT tech-lead itself:

- **(A) `beads-watchdog.sh`** (`~/.hermes-teams/startup/profiles/tech-lead/scripts/beads-watchdog.sh`) — a **zero-token** cron script that scans active beads projects (from `~/.hermes-teams/startup/active-projects.json`) for `bd ready` issues and creates a tech-lead kanban card **on the project's own board** with an idempotency key `beads-<issue_id>`. This is the sole beads→kanban bridge. **It is NOT currently scheduled** in `cron/jobs.json` (the only job there is the product-owner's "Project Discovery" every 4h). The reference docs describe a `*/5 * * * *` cadence, but the live cron table has no watchdog entry — so the bridge currently relies on manual invocation or an external scheduler. This is a gap to flag.

- **(B) Product-owner** — via the **`dev-dispatch`** skill on the **product-owner** profile (not tech-lead). The PO discovers work, files beads issues, and pre-creates tech-lead cards. The live cron job `aadaec8fa02a` ("Project Discovery", every 4h) runs AS the product-owner identity and loads the `project-discovery` skill.

### What does NOT trigger tech-lead
- An **architect spec** is not a documented trigger source. Tech-lead receives design questions and routes *to* the architect (SOUL.md Handoffs: "Design questions → architect"), but the architect→tech-lead handoff path is not formalized in the skills. The primary trigger is the **beads issue** (ready in `bd`), surfaced by either the watchdog or the PO.
- The **PO** is an upstream feeder (files beads, may pre-create cards), not a direct "go implement this" dispatcher. The contract of record is the beads issue + the tech-lead-authored contract.md.

---

## 3. Inputs

| Input | Source | Purpose |
|-------|--------|---------|
| **Beads issue** (`bd show <bead_id>`, `bd ready --json`) | Beads issue tracker | WHAT: scope, acceptance criteria, ordering. The planning truth. |
| **PRD** (`PRD.md` / `cat PRD.md`) | Project repo | Requirements/contract basis |
| **Conventions** — `AGENTS.md`, `CONTEXT.md`, `CODING_STANDARDS.md`, ADRs | Project repo | Discover phase: how code is written here |
| **CodeGraph structural pass** (`--graph-only`) | Tool | Codebase index for blast-radius/test-gap analysis |
| **`.driver/goal.md`** | Project `.driver/` dir | Reflection phase: "is this moving toward the goal?" |
| **Scout findings** (`~/vault/meta/scout.db`) | scout profile | Inform loops with external AI/dev technique findings |
| **Researcher wiki** (`~/vault/wiki/`) | researcher profile (READ ONLY) | Curated knowledge |
| **Active projects list** (`active-projects.json`) | Operator | Which projects the watchdog scans |
| **Parent-task handoff** (`kanban_show`) | Kanban | When dispatched as a child, reads parent summary + metadata |

**Note on the beads-kanban ownership contract**: Beads owns WHAT (scope, ACs, ordering). Kanban owns WHO/WHEN (which agent, lifecycle, handoffs). Only the completion boundary writes back to beads (the verifier's pass-merge-complete).

---

## 4. Outputs

### 4a. Dev cards & topology (via `kanban_chains`)

Tech-lead NEVER uses `kanban_create` for dev/verifier cards. **`kanban_chains` is the only flow.** It atomically creates the developer + verifier pair, links tech-lead as a dependent of the verifier, and blocks tech-lead with `kind=dependency`.

```
kanban_chains(
    goal="<short description>",
    chains=[[
        {"assignee": "developer", "title": "<short title>",
         "body": "<full contract: ACs, evals_cmd, bead_id, constraints>",
         "workspace_path": "<absolute project dir>"},
        {"assignee": "verifier", "title": "[verify] <short title>",
         "body": "Verify developer card. Contract: <full contract>"}
    ]]
)
```

- **Developer card** — title `[dev] <outcome>`. Body = full contract (ACs, evals_cmd, bead_id, constraints, harness). Workspace = `dir:<project path>`.
- **Verifier card** — title `[verify] <outcome>`. Child of the developer card. Body = contract_ref, evals_cmd, bead_id, review axes. Trace-blind by default.
- **Fix card** (created by **verifier** on FAIL, not tech-lead) — assignee=developer, parent=review card, workspace = the developer's ORIGINAL worktree, body carries `Review-Iteration: <N>`, `Chain-Root`, `Resume-Session`, `Branch`, `Worktree`.

Parallel chains: pass multiple chains to `kanban_chains` for genuinely independent beads.

### 4b. Merges

**Tech-lead never merges.** Developers never merge either. The **verifier** is the merge-owner: on PASS it acquires a `bd merge-slot`, rebases onto main, re-runs evals + full suite on the rebased candidate, merges, releases the slot. (The DoltHub rule: never trust reported-green; re-run on the rebased candidate.)

### 4c. Planning artifacts (written to project repo)
- `PRD.md` (via `to-spec`)
- ADRs (via `domain-modeling`)
- Glossary (via `ubiquitous-language`)
- `contract.md`, `progress.md`, `log.md` — the 3-file crash state (the model can crash/lose session and recover by reading only these)
- Decomposed beads (`bd issue create`, preserving hierarchy)
- Journal entry to `~/projects/<slug>/journal/`

---

## 5. Handoffs

### To `developer` (Generator)
- **Mechanism**: `kanban_chains` card, assignee=`developer`, body = full contract.
- **Workspace**: the project's absolute path (`workspace_kind: dir`).
- **Harness**: developer picks (`pi --provider zai --model glm-5.2` is the documented default); tech-lead does not choose the harness.
- **What flows back**: developer's completion report (trace ledger path `~/projects/<slug>/traces/<card-id>/attempt-N.jsonl`, branch, worktree, session id, harness cost) → auto-injected into the verifier card's prompt on promotion.

### To `verifier` (Evaluator)
- **Mechanism**: child card auto-created by `kanban_chains`, assignee=`verifier`.
- **What tech-lead expects**: a stamped verdict (`PASS`/`FAIL`/`ESCALATE`) + metadata in the completion summary.
- **Tech-lead's job**: WAIT. Do not poll, sleep-loop, or run tests. Auto-promoted when all verifiers finish.
- On **PASS**: verifier merges → tech-lead closes bead (`bd close`) → `kanban_complete`.
- On **FAIL**: verifier creates the fix card for developer → loop continues → tech-lead stays parked.
- On **ESCALATE** (iter ≥ 3 / spec gap): surfaces to tech-lead for a routing decision.

### To `debugger` (hard bugs)
- **Trigger**: ESCALATE classified as **defect-class** (root-cause-unknown; no contract wording explains failure).
- **Rule**: teardown FIRST — drain in-flight dev+verifier chain on that defect (complete/cancel outstanding fix cards) — BEFORE creating the debugger card. Enforces **"no two-loops-one-defect."**
- Tech-lead files the defect (repro + findings + ledger trace); debugger runs its own converge loop (diagnose + its own dev/verifier pair).

### To `qa`
- **No formal qa handoff exists.** The `verifier` profile IS the validation/QA role. There is no separate `qa` assignee in the documented team roster (which is: product-owner, tech-lead, scout, researcher, developer, verifier, base). Per-epic validation uses `improve-codebase-architecture` + `ponytail-audit` (reference tools), not a qa agent.

### To `architect` (design questions)
- SOUL.md: "Design questions → architect." Tech-lead routes genuine design ambiguity upward. (The reverse, architect→tech-lead, is not formalized in tech-lead's skills.)

### To `product-owner` (intent gaps)
- **Contract-vs-INTENT gap** (the bead promises the wrong thing) → tech-lead routes to `product-owner`, who owns bead content.
- **Contract-vs-code gap** (the spec wording caused the failure) → tech-lead re-contracts itself.

### To `researcher` / `scout`
- `kanban_create(title="Scout: <topic>", assignee="scout")` or `assignee="researcher"` for deep research.

---

## 6. How tech-lead manages developer cards

### The lifecycle tech-lead owns (and what it does NOT touch)

```
PLAN (tech-lead)
  → kanban_chains  ── creates dev card + verifier card atomically,
                      links tech-lead as child of verifier,
                      blocks tech-lead (kind=dependency)
  → STOP. Session ends.

[ developer works card → completes → verifier auto-promotes ]

AUTO-PROMOTION (tech-lead re-dispatched)
  → kanban_show: read verifier completion summaries
  → if ALL PASS → bd close <bead_id> → kanban_complete
  → if any FAIL → verifier created fix chains automatically
       → if fix verifiers still running: link self to fix-verifier card,
         block kind=dependency, WAIT (do NOT create new chains)
  → if ESCALATE → classify & route (see §5)
```

### Hard rules (from SKILL.md "Rules")
- `kanban_chains` is the **ONLY** way to create dev/verifier cards. **NEVER** `kanban_create` for them.
- **NEVER** poll or sleep-loop waiting for the verifier. The tool blocks; you auto-promote.
- **NEVER** create fix cards yourself. The verifier handles FAIL routing.
- On verifier PASS: verifier merges. On FAIL: verifier creates the fix card. On ESCALATE: verifier blocks for tech-lead.

### What tech-lead must NOT do (role-separation violations)
- Never write code, never invoke a coding harness.
- Never run tests, never write adversarial probes, never judge code quality.
- Never run pytest / verification scripts for validation purposes.
- Never use `delegate_task` for implementation or verification (it bypasses role separation; `delegate_task` is only for short read-only reasoning subtasks in the current session).

### Iterate phase — the two cases that actually fire for tech-lead
**Case A — ESCALATE** (iter ≥ 3 or spec gap):
1. Read accumulated findings first (`REVIEW-ITERATION` comments on the dev card).
2. Read the trace (`~/projects/<slug>/traces/<chain-root>/attempt-N.jsonl`), grep for the divergence point.
3. Classify and route by defect class (defect→debugger; contract gap→re-contract; harness ceiling→switch model; wrong slice→abandon).

**Case B — spec gap tech-lead caused**: update PRD/contract BEFORE re-running. The spec is not static.

### Concurrency control
- Per-profile cap: `max_in_progress_per_profile: 3` (in this profile's `config.yaml`). The reference docs describe raising to 6 for parallelism; **live config is 3.** Caps are read by the lock-holding gateway at boot from its OWN profile config — all profile configs must agree for a cap change to take effect regardless of which gateway dispatches.
- `dispatch_stale_timeout_seconds: 14400` (4h) — dispatcher reclaims a task with no heartbeat in the last hour. Heartbeat (`kanban_heartbeat`) at least hourly during long ops.

---

## 7. JSON node definitions (tech-lead's role graph)

These model the tech-lead's state machine as typed nodes. Useful for wiring into a graph/automation layer.

### Node: tech-lead (role)
```json
{
  "type": "role",
  "id": "tech-lead",
  "model": { "default": "glm-5.2", "provider": "zai", "reasoning_effort": "xhigh", "context_length": 1000000 },
  "toolsets": ["hermes-cli", "kanban"],
  "plugins": ["kanban_chains", "skill_enforcer"],
  "mandatory_skills": ["loops-engineering"],
  "skills": ["loops-engineering", "ad-hoc-verification", "requesting-code-review", "receiving-code-review", "computer-use"],
  "caps": { "max_in_progress_per_profile": 3, "max_in_progress": 3, "dispatch_stale_timeout_seconds": 14400 },
  "forbidden": ["write_code", "invoke_coding_harness", "run_tests", "write_probes", "judge_code_quality", "merge_to_main", "create_dev_verifier_cards_via_kanban_create"],
  "board": "<per-project board, discovered from .beads/>"
}
```

### Node: trigger (beads-ready)
```json
{
  "type": "trigger",
  "id": "beads-ready",
  "source": "beads_watchdog OR product-owner(dev-dispatch)",
  "condition": "bd ready returns issue with status=ready AND no existing tech-lead task for that beads_id (idempotency-key beads-<issue_id>) AND tech-lead not already running on any project board",
  "creates": { "card": { "assignee": "tech-lead", "title": "[<project>-<hash>] <bead title>", "board": "<project board>", "idempotency_key": "beads-<issue_id>" } }
}
```

### Node: phase.discover
```json
{
  "type": "phase",
  "id": "discover",
  "actor": "tech-lead",
  "actions": ["codegraph --graph-only", "read AGENTS.md/CONTEXT.md/CODING_STANDARDS.md/ADRs", "scan bd/PRs/tests/kanban"],
  "done_when": "every convention, test command, and open work item accounted for"
}
```

### Node: phase.plan
```json
{
  "type": "phase",
  "id": "plan",
  "actor": "tech-lead",
  "human_in_loop": true,
  "actions": ["grill (one question at a time)", "to-spec PRD", "domain-modeling ADRs", "negotiate contract (~20-27 assertions)", "build evals", "to-tickets decompose", "right-size gate", "bd issue create", "write contract.md/progress.md/log.md"],
  "done_when": "PRD + ADRs + contract.md + evals published; issues in beads with deps; user approved decomposition"
}
```

### Node: phase.execute (the dispatch)
```json
{
  "type": "phase",
  "id": "execute",
  "actor": "tech-lead",
  "tool": "kanban_chains",
  "input": { "bead_id": "<id>", "contract": "<full ACs>", "evals_cmd": "<cmd>", "project_dir": "<abs path>" },
  "output": {
    "dev_card": { "assignee": "developer", "title": "[dev] <outcome>", "workspace": "dir:<project>", "parent": "<root>" },
    "verifier_card": { "assignee": "verifier", "title": "[verify] <outcome>", "parent": "<dev_card>" },
    "self_link": "tech-lead child of <verifier_card>",
    "self_block": "kind=dependency"
  },
  "then": "STOP — end session; auto-promote on verifier completion"
}
```

### Node: phase.validate
```json
{
  "type": "phase",
  "id": "validate",
  "actor": "tech-lead",
  "action": "WAIT (do not poll)",
  "verifier_verdict": { "enum": ["PASS", "FAIL", "ESCALATE"], "stamped_in": "verifier completion summary" },
  "on_pass": "verifier merges → bd close → kanban_complete",
  "on_fail": "verifier creates fix card → dev retries (warm resume) → loop continues (tech-lead parked)",
  "on_escalate": "route to phase.iterate"
}
```

### Node: phase.iterate
```json
{
  "type": "phase",
  "id": "iterate",
  "actor": "tech-lead",
  "fires_on": "ESCALATE (iter>=3 OR spec_gap)",
  "steps": ["read REVIEW-ITERATION comments", "read trace ledger", "classify defect"],
  "routing": {
    "defect_class_bug": { "to": "debugger", "precondition": "drain in-flight chain first (no two-loops-one-defect)" },
    "contract_gap": { "to": "self", "action": "re-contract → new kanban_chains (cold restart)" },
    "harness_ceiling": { "to": "self", "action": "switch harness model" },
    "wrong_slice": { "to": "user", "action": "abandon slice" },
    "contract_vs_intent": { "to": "product-owner", "reason": "PO owns bead content" }
  }
}
```

### Node: handoff.dev
```json
{
  "type": "handoff",
  "id": "to-developer",
  "via": "kanban_chains card",
  "assignee": "developer",
  "body": "full contract: ACs, evals_cmd, bead_id, constraints",
  "workspace": "dir:<absolute project path>",
  "harness": "developer-chosen (default pi --provider zai --model glm-5.2)",
  "returns": { "trace": "~/projects/<slug>/traces/<card-id>/attempt-N.jsonl", "branch": "...", "worktree": "...", "session_id": "...", "harness_cost_usd": "..." }
}
```

### Node: handoff.verifier
```json
{
  "type": "handoff",
  "id": "to-verifier",
  "via": "auto-child card from kanban_chains",
  "assignee": "verifier",
  "trace_policy": "blind_by_default (reads diff+files+executed tests+report; opens transcript only on tamper suspicion)",
  "merge_owner": true,
  "returns": { "verdict": "PASS|FAIL|ESCALATE", "metadata": "stamped in completion summary" }
}
```

### Node: handoff.debugger
```json
{
  "type": "handoff",
  "id": "to-debugger",
  "trigger": "ESCALATE classified defect-class (root-cause-unknown)",
  "precondition": "teardown: complete/cancel outstanding fix cards on this defect BEFORE creating debugger card",
  "payload": "repro + accumulated findings + ledger trace",
  "constraint": "no two-loops-one-defect"
}
```

### Node: completion (the write-back boundary)
```json
{
  "type": "boundary",
  "id": "completion",
  "actor": "tech-lead (after verifier PASS)",
  "actions": ["bd close <bead_id>", "kanban_complete", "journal entry ~/projects/<slug>/journal/", "reflection (read trace, pattern check, patch skill if systemic)"],
  "beads_writeback": "only here — the verifier pass-merge-complete is the boundary"
}
```

---

## Appendix A — Live config facts (from config.yaml)

| Key | Value |
|-----|-------|
| model.default | glm-5.2 |
| model.provider | zai |
| model.context_length | 1,000,000 |
| model.rate_limit_delay | 30 |
| reasoning_effort | xhigh |
| toolsets | hermes-cli, kanban |
| plugins.enabled | kanban_chains, skill_enforcer |
| skill_enforcer.mandatory | loops-engineering |
| kanban.max_in_progress_per_profile | 3 |
| kanban.max_in_progress | 3 |
| kanban.dispatch_stale_timeout_seconds | 14400 (4h) |
| approvals.mode | smart |
| skills.disabled | ask-matt, edit-article, git-guardrails-claude-code, migrate-to-shoehorn, scaffold-exercises, teach, wizard, writing-beats, writing-fragments, writing-shape |

## Appendix B — Open gaps / things to flag

1. **`dev-dispatch` and `code-review` skills do not exist on tech-lead.** `dev-dispatch` is a product-owner skill; `code-review` is a mattpocock plugin skill. The two code-review skills on tech-lead (`requesting`/`receiving`) are explicitly deprecated for the kanban loop.
2. **beads-watchdog.sh is not in the live cron table.** `cron/jobs.json` has only the PO's "Project Discovery" (every 4h). The reference docs describe a `*/5 * * * *` watchdog, but no scheduled job creates it — the beads→kanban bridge is currently dormant unless run manually or by an external scheduler.
3. **Cap mismatch:** live `config.yaml` = 3, reference docs describe 6. The reference explicitly says all profile configs must agree and caps load at gateway boot.
4. **The platform `review` status / review-dispatch path is documented as dead code** — do not use it; parent/child cards via `kanban_chains` is the only working flow.
5. **No formal qa role** exists in the team roster; the verifier covers validation. Per-epic validation uses tool-based audits (`improve-codebase-architecture`, `ponytail-audit`), not a qa agent.
6. **MEMORY.md notes two hard-won operational lessons** worth preserving: (a) `kanban_link` is cross-board — pass explicit `board=` on both calls; (b) the ESCALATION CASCADE bug — a resolver completing itself can't close the blocked verify card (worker-scope guard) → infinite escalation loop; fix by closing via CLI `hermes kanban --board <slug> complete <blocked_id>`; (c) the verifier blind spot — AC gates validate the branch in isolation, not mergeability vs master; always do git forensics (merge-base, log divergence, merge-tree dry-run) before adjudicating merge-decision escalations.
