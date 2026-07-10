---
name: loops-engineering
description: "Run autonomous coding loops — the system that finds work, delegates to coding agents, validates strictly, and iterates until done. Use when orchestrating Claude Code, Codex, or OpenCode to implement features or fix bugs unattended, when running maker-checker validation on agent output, when planning a sprint or epic for agent execution, when the user says 'loop', 'sprint', 'delegate this', 'run an epic', 'set up a coding loop', or asks you to orchestrate multiple agents on a coding task."
---

# Loops Engineering

A loop is a recursive goal: define it once, the agent iterates until the work is actually done. You design the system that prompts the agent — not the prompt itself.

Three loops nest at different time horizons (each feeds the one inside it):
- **External feedback** (hours→weeks): alpha testers, A/B, production data → informs vision
- **Developer feedback** (tens of min→hours): you examine output, steer the agent, evolve the spec
- **Agentic coding** (minutes): agent writes, tests, iterates until bug-free — **the five phases below run inside this loop**

> Full theory: [references/loop-theory.md](references/loop-theory.md) — three-loop model, Ralph technique, Flywheel Planning, context engineering, autonomous operation, memory architecture, self-improvement via scout/researcher, harness pruning.

## Role separation (critical)

Three roles, three context windows. Mixing them is the most common failure — the model becomes sycophantic the moment it grades itself.

| Role | Who | Rule |
|------|-----|------|
| **Planner** | Tech-lead (you) | Turns intent into spec. Never touches code. |
| **Generator** | Coding-agent harness | Writes everything. Forbidden from grading own work. |
| **Evaluator** | Review sub-agent | Told from the first message: the code is broken, prove it. |

## The five phases

Each phase ends on a checkable completion criterion. Do not skip phases.

### 1. Discover

Understand the codebase and work surface before planning.

- Index with CodeGraph (`--graph-only` for fast structural pass)
- Read: `AGENTS.md`, `CONTEXT.md`, `CODING_STANDARDS.md`, existing ADRs
- Scan: Beads issues (`bd status`), open PRs, failing tests, kanban board
- Identify: test framework, linter, formatter, commit style, branching strategy

**Done when**: every convention, test command, and open work item is accounted for — nothing discovered later that a `grep` would have found here.

### 2. Plan

This is where human-in-the-loop lives — everything after this runs autonomously.

1. **Grill the user** (`grilling`): one question at a time, recommended answer attached, until the goal is crisp.
2. **Artifacts**: PRD (`to-spec`), ADRs (`domain-modeling` + `decision-mapping`), glossary (`ubiquitous-language`).
3. **Negotiate the contract**: Before any code, draft a checklist of testable assertions (~20-27 for a small task; 10 is too few and the evaluator rubber-stamps). The PRD is the boundary; the **contract** is what gets graded. If multiple agents are involved, the generator proposes done-criteria and the evaluator pushes back — they argue via markdown on disk until they agree.
4. **Build evals**: Structured assertions about behavior, not just unit tests. Build them NOW alongside the contract, not "when problems recur." For subjective quality (UI, text generation), encode the rubric.
5. **Decompose** (`to-tickets`): tracer-bullet vertical slices with dependency tracking.
6. **Right-size gate**: Can one agent finish this in one context window? Does it touch >5 files across modules? Are there parallelizable sub-parts? → split if any.
7. **Publish to Beads**: `bd issue create`, preserving hierarchy (epics → beads → sub-beads).
8. **Write crash state to disk**: `contract.md`, `progress.md`, `log.md`. These three files ARE the state — the model should be able to crash, lose its session, and pick up by reading only these. If you can't describe state in three files, it's too complicated.

For complex work, add a critique loop: run `scrutinize` on the plan before decomposing. Loop until stable.

**Re-contract rule**: if you hit a genuine gap missed during grilling, pause that issue only (unrelated tasks delegate as normal), and contract the user. Resolve everything else via research, code, docs, or other agents first.

**Done when**: PRD published, ADRs written, contract.md written, evals written, issues in Beads with dependencies. User approved the decomposition.

### 3. Execute

**You are the PLANNER. You NEVER write code and NEVER invoke a coding harness yourself.** Your tools are for planning (read, search, beads, git status) and orchestration (kanban cards). Code generation is the `developer` profile's job — create a kanban card assigned to `developer` with the contract as the body.

**Kanban-native flow (the ONLY flow):**

Follow this checklist EXACTLY. Each step is mandatory.

### Step 1: Plan
- [ ] Read the bead (`bd show <bead_id>`)
- [ ] Read the PRD (`cat PRD.md`)
- [ ] Write the contract: acceptance criteria, evals command, constraints
- [ ] Identify the project directory (absolute path)

### Step 2: Delegate
- [ ] Call `kanban_chains` with your contract(s) as parallel chains
- [ ] Single chain → pass one chain with dev + verifier steps
- [ ] Parallel chains → pass multiple chains

```
kanban_chains(
    goal="<short description>",
    chains=[[
        {"assignee": "developer", "title": "<short title>", "body": "<full contract: ACs, evals_cmd, bead_id, constraints>", "workspace_path": "<absolute project dir>"},
        {"assignee": "verifier", "title": "[verify] <short title>", "body": "Verify developer card. Contract: <full contract>"}
    ]]
)
```

- [ ] Verify the tool returned `"status": "blocked"` — this means it worked
- [ ] **STOP HERE.** Do NOT poll. Do NOT sleep. Do NOT call kanban_show in a loop.
- [ ] Your session will end. The system will auto-promote you when ALL verifiers finish.

### Step 3: After Auto-Promotion (when you are re-dispatched)
- [ ] Read verifier completion summaries via `kanban_show`
- [ ] If ALL PASS → close bead (`bd close <bead_id>`) → `kanban_complete`
- [ ] If any FAIL → check for fix chains created by the verifier
  - Fix chains are handled automatically — do NOT create your own fix card
  - The verifier creates fix cards on FAIL. Wait for the fix verifier to complete.
  - If you are re-dispatched and fix verifiers are still running, link yourself to the fix verifier cards and block with `--kind dependency`:
    ```
    kanban_link <fix_verifier_id> <my_card_id>
    kanban_block <my_card_id> "dependency: waiting for fix verifier" --kind dependency
    ```
    Do NOT call `kanban_chains` again — that creates a new topology. You only need to wait on existing fix cards.

### Rules
- `kanban_chains` is the ONLY way to create dev/verifier cards. NEVER use `kanban_create` for dev or verifier cards.
- NEVER poll or sleep-loop waiting for the verifier. The tool blocks you — you will be auto-promoted.
- NEVER create fix cards yourself. The verifier handles FAIL routing.
- On verifier PASS: verifier merges to main. On FAIL: verifier creates fix card. On ESCALATE: verifier blocks for tech-lead.
- On verifier FAIL: verifier creates fix card for developer. On PASS: verifier merges. On ESCALATE: verifier blocks for tech-lead.

**Harness choices** (developer picks, not you):
- `pi --provider zai --model glm-5.2` — the default model for code generation

> Kanban-native async loops detail: [references/kanban-native-loops.md](references/kanban-native-loops.md)

**Done when**: the agent has committed the work AND the worktree is clean (no uncommitted changes).

### 4. Validate — monitor verifier output (you don't validate; the verifier does)

The verifier profile handles ALL validation autonomously via adversarial-review v4.0.0. Your job is to **wait and monitor** the loop:

- Read the verifier's completion summary when it finishes
- On PASS: bead is closed, kanban task completes
- On FAIL: verifier creates fix card for developer → loop continues → you wait
- On ESCALATE (iteration ≥ 3 or spec gap): read the accumulated findings, decide: re-contract, switch harness model, or abandon

**NEVER run tests yourself. NEVER write adversarial probes. NEVER judge code quality. NEVER run pytest, never write verification scripts, never execute the developer's code for validation purposes. The verifier owns ALL of that. If you find yourself writing a probe or running pytest, STOP — you are violating role separation. Block the task if the verifier hasn't been created yet.**

**Done when**: verifier returns PASS (or you escalate).

**Done when**: zero findings rated Critical or Important. Every subjective score ≥ 0.7 (if applicable). Every contract item checked off.

### 5. Iterate

If validation fails, iterate — but never blindly. Follow this sequence:

**Step 1 — Read the trace**: BEFORE re-delegating, read the agent's raw transcript. Pipe output to a file, grep for the moment judgment diverged from spec. The fix is usually editing the prompt for that exact moment — not rewriting the whole task.

**Step 2 — Update the spec if needed**: if the failure reveals a spec gap (not just an agent error), update the PRD/issues/contract BEFORE re-delegating. The spec is not static — it evolves as you see what the agent builds.

**Step 3 — Re-delegate with feedback, warm when possible**:

FAIL → read trace, find divergence point
     → update spec/contract if the failure reveals a spec gap
     → file follow-up comment with exact failure points + trace evidence
     → WARM RESUME the same harness session with the findings


> **Never write code yourself.** You are the PLANNER. If `delegate_task` is disabled and no harness is available, BLOCK the task (`kanban_block`) rather than writing code yourself. Code written by the planner destroys the role separation that makes adversarial verification meaningful. Create a developer card and let the developer profile handle it.
        the harness keeps its own memory of the prior attempt; strictly
        better than cold re-delegation when the approach was sound)
     → cold re-delegate with corrected prompt only when the approach itself
       was wrong (fresh start per Ralph technique)
     → repeat until validation passes


Key rules:
- **Trace-first**: never re-delegate without reading the transcript. Tuning by vibe produces slop.
- **Retry cap**: 3 failures on the same issue → escalate (research task, contract user, or different harness)
- **Let it restart**: if the agent throws everything away and starts over, don't interrupt. Intervene only when the contract itself is wrong.

**Done when**: validation passes (returns to Phase 4 done condition). Then:
1. `bd close <bead-id>` — close the bead in the issue tracker (non-negotiable — the automation loop depends on this to surface the next ready bead)
2. Mark done on kanban board (`kanban_complete`)
3. Write journal entry to `~/vault/journal/<project>/`
4. Run reflection (below)
5. Hand back to user

## Reflection (after task completion)

Before starting the next task, take 60 seconds to learn from the one just completed. This is the meta-loop — the loop that improves the loop.

1. **Read the trace**: scan the completed task's transcript. What took the most iterations? Where did the agent diverge?
2. **Pattern check**: is this the same failure you've seen on previous tasks? If yes → the fix is systemic, not task-specific.
3. **Patch if needed**:
   - Same prompt misunderstanding repeatedly → fix the harness command or issue template
   - Same validation failure → add an eval or tighten the contract template
   - Same codebase friction → file a tech-debt issue (`request-refactor-plan`)
4. **Goal check**: read `.driver/goal.md` for this project. Is this task moving toward the goal, or are we drifting?
5. **Journal**: write one line to the journal entry: what worked, what didn't, what to try differently next time.

**Done when**: one learning recorded. If nothing new was learned, skip — don't force reflection when there's nothing to reflect on.

> Autonomous operation details: [references/loop-theory.md](references/loop-theory.md) — trigger mechanisms, heartbeat survival, beads watchdog script, three-control duplicate prevention, cron schedule pitfall, kanban CLI flag syntax.

## Board architecture (hybrid)

- **Per-project boards** (discovered dynamically from `.beads/` directories) → tech-lead coding tasks. Each project gets its own board with isolated DB, workspace, and dispatcher loop.
- **`hermes-hq`** → scout + researcher tasks (cross-project research).
- CLI syntax: `hermes kanban --board <slug> <subcommand>` (board flag goes BEFORE the subcommand).

## Pitfalls

- **Rubber-stamping**: the evaluator accepts work without proof. Cure: adversarial stance + separate agent.
- **Comprehension debt**: code ships faster than you understand it. Cure: periodic `improve-codebase-architecture`.
- **Retry blindness**: re-delegating with the same prompt after failure. Cure: trace-first rule.
- **Harness bloat**: never deleting scaffolding. Cure: re-read harness against each model release, delete what the model does for free.
- **Bottleneck blindness**: fixating on the current bottleneck when it has already moved (coding→planning→verification→taste).
- **Guessing project state**: never assume which projects are active — the user owns that decision. Issues sitting in "ready" for weeks usually means inactive, not active. Always ask before adding a project to the watchdog's active list.
