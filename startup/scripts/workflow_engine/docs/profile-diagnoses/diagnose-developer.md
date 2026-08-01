# Developer Profile — Complete Role Diagnosis

**Source files**: `SOUL.md`, `config.yaml`, `skills/software-development/developer-loop/SKILL.md`
**Profile root**: `~/.hermes-teams/startup/profiles/developer/`
**Diagnostic date**: 2026-07-31

---

## 1. What the Developer Does

The developer is an **autonomous code generator** — a thin governance wrapper around vendor coding harnesses (Claude Code, Codex, OpenCode, Pi). The harness writes the code; the developer governs the invocation, runs mechanical gates, and captures the trace.

**Core stance (non-negotiable invariants):**
- **The developer is the Generator.** Never reviews, scores, or approves its own work — that's the verifier's job. Self-grading is the exact failure mode the role separation exists to prevent.
- **Mechanical gates only.** Runs `evals_cmd`, tests, lint, typecheck — binary pass/fail. Quality and spec fit are never assessed; those belong to the reviewer.
- **Trace or it didn't happen.** Every harness invocation is captured to a durable trace ledger with `session_id` and cost. A completed card without its trace is a **protocol violation**.
- **Never touches the contract.** If the spec seems wrong, blocks with evidence — spec judgment belongs to tech-lead.

The developer explicitly does **not** write code raw when a harness can do the work. Raw terminal/patch edits are a last resort only when no harness is available.

---

## 2. Triggers

**Trigger mechanism: kanban coding card dispatched via `kanban_chains`.**

- The developer receives **coding cards** created by the tech-lead orchestrator.
- Cards arrive via the `kanban_chains` plugin (enabled in `config.yaml`), which creates chains of parent→child tasks.
- The `skill_enforcer` plugin (enabled) **mandatorily loads** `developer-loop` at the start of every coding card (`config.yaml` → `skill_enforcer.mandatory: [developer-loop]`).
- Card dispatch promotes the card to `ready` when its parent (tech-lead card) completes; the dispatcher spawns the `developer` profile.

**Card body carries the cold-start contract (the developer starts with zero context):**
- `bead_id` — references the bead for acceptance criteria (card REFERENCES it, never copies)
- `contract_ref` — path to `contract.md` in the repo (committed by tech-lead)
- `evals_cmd` — executable check command
- `Size:` ∈ {small, medium, large}
- `Harness:` ∈ {claude, codex, opencode, pi}
- Constraints, context plan (what to read / not read)

**Retry cards (fix cards)** carry additional fields stamped by the reviewer:
- `Review-Iteration: <N>`
- `Chain-Root: <original card id>`
- `Resume-Session: <session_id>`
- `Branch:`, `Worktree:`

---

## 3. Inputs

| Input | Source | Purpose |
|-------|--------|---------|
| **Card body** | Tech-lead (via kanban) | bead_id, contract_ref, evals_cmd, Size, Harness, constraints |
| **Retry fields** | Reviewer (on fix cards) | Review-Iteration, Chain-Root, Resume-Session, Branch, Worktree |
| **Comment thread** | Own card + chain-root card | Prior reviewer findings (`REVIEW-ITERATION:` comments) — iteration memory |
| **Contract** | `contract_ref` path in repo | Verbatim contract items fed to harness prompt |
| **Workspace** | `$HERMES_KANBAN_WORKSPACE` | Worktree (first attempt) or dir pointing at original worktree (fix card) |
| **bead** | `bead_id` lookup | Acceptance criteria — AC evidence mapping is mandatory |

---

## 4. Outputs

### Code & Commits
- **Code changes** in the worktree, produced by the harness (not the developer directly).
- **Commit to the card's branch** (`branch_name` — NEVER main, NEVER merge). The developer commits but does not merge; merging is the verifier's job.

### Trace Ledger (non-negotiable)
```bash
~/projects/<slug>/traces/<chain-root-id>/attempt-<n>.jsonl
```
Keyed by **chain root** (original developer card id) so all attempts for one piece of work land in one directory with continuous numbering.

### Metadata (in `kanban_complete`)
```json
{
  "harness_session_id": "<session_id>",
  "transcript_path": "<ledger path>",
  "total_cost_usd": "<float>",
  "num_turns": "<int>",
  "changed_files": ["<list>"],
  "branch_name": "<branch>",
  "worktree_path": "<path>",
  "chain_root": "<original card id>"
}
```
`branch_name` and `worktree_path` are **mandatory** — without them the verifier cannot locate the work and warm resume dies. This metadata auto-injects into the child review card's context.

### Completion Report (comment)
```markdown
## Completion report
**Approach**: <how the harness solved it, 2-4 sentences>
**Key decisions**: <choices that weren't dictated by the contract>
**Deviations from contract**: <none | list, each with why>
**Dead ends**: <attempts that failed and why>

## Acceptance criteria — evidence mapping
- [x] AC1: <criterion text> → <test name + actual output proving it>
- [x] AC2: <criterion text> → <test name + actual output proving it>
- [ ] AC3: <criterion text> → NOT MET: <why>

**Test evidence**: <actual command + actual output>
**Changed files**: <list>
**Session**: <session_id> · trace: <ledger path> · cost: $<x> (<n> turns) · budget flag: <none | exceeded tier>
```

The AC evidence mapping is **mandatory** — the verifier re-verifies each item independently. The developer's proof is a *claim*; the verifier's execution is the *fact*.

**Terse reporting overlay:** Prose sections (Approach, Key decisions, Deviations, Dead ends) are written in caveman `full` style. Hard exemptions (never compressed): AC evidence mappings, test evidence, structured metadata, session/trace/cost lines, code, commit messages, error strings.

---

## 5. Handoffs

### To Verifier (review → merge)
- **Mechanism**: Developer commits to branch, completes card with metadata + completion report. The card's child (review card) auto-promotes and is dispatched to the verifier.
- **What flows**: `branch_name`, `worktree_path`, `harness_session_id`, `transcript_path`, `total_cost_usd`, completion report with AC evidence mapping.
- **The verifier owns**: Review verdict, independent AC re-verification, merge.
- **Q&A channel**: Verifier may ask questions via card comments. Developer answers factually from session/trace. If a finding demands a code change, it arrives as a fix card.

### To Debugger (bug)
- **No `debug-loop` skill exists.** The developer profile contains only `developer-loop`. There is no dedicated debugger handoff path in the current configuration.
- **Bug handling on gates failure**: If mechanical gates fail after one warm-resume round, the developer blocks `kanban_block(transient)` with evidence (what failed, session_id, transcript path, cost). This surfaces for escalation — the block comment is the only trace pointer an escalating tech-lead gets.
- **Contract disputes**: Block `kanban_block(needs_input)` with evidence → routes to tech-lead (not a debugger).

### To Tech-Lead (escalation / contract disputes)
- **Contract disputes**: If contract or ACs seem wrong → `kanban_block(needs_input)` with evidence. Spec judgment belongs to tech-lead; developer and verifier cannot re-contract.
- **Trace-first iteration**: Escalation reads from the trace ledger the developer captured.

---

## 6. Developer-Loop Workflow

The `developer-loop` skill defines a 6-phase lifecycle (phases numbered 0–5 in the skill):

```
┌─────────────────────────────────────────────────────────────────┐
│ PHASE 0: COLD START — read before anything runs                 │
│  Read card body (bead_id, contract_ref, evals_cmd, Size,        │
│  Harness, constraints) + retry fields (if fix card) + full      │
│  comment thread (own + chain-root) + verify workspace.          │
│  If anything missing → block needs_input.                       │
└───────────────────────────┬─────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ PHASE 1: HARNESS INVOCATION (verified recipe)                   │
│  Select harness from card (claude/codex/opencode/pi).           │
│  Apply budget cap stack: wall-clock timeout + turn cap (claude  │
│  only) + post-hoc cost ceiling.                                 │
│  Compose prompt: contract items (verbatim) + evals_cmd +        │
│  repo conventions + accumulated findings (on retry).            │
│  Warm resume on retry: run from SAME worktree path.             │
└───────────────────────────┬─────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ PHASE 2: PROMPT COMPOSITION                                     │
│  contract items (verbatim from contract_ref) + evals command +  │
│  repo conventions from card + on retries: accumulated findings  │
│  ("Address these specific findings; do not re-derive…").        │
│  Minimal tool allowlist — only what the task needs.             │
└───────────────────────────┬─────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ PHASE 3: MECHANICAL GATES (ONLY judgment surface)              │
│  Run: evals_cmd → test suite → lint → typecheck.                │
│  Binary pass/fail ONLY. Never assess quality/design/spec fit.   │
│                                                                 │
│  Gates green ──────────────────────────────► Phase 4            │
│  Gates fail ──► ONE warm-resume round (failure as findings)     │
│  Still failing ──► kanban_block(transient) + evidence comment   │
└───────────────────────────┬─────────────────────────────────────┘
                            ▼ (gates green)
┌─────────────────────────────────────────────────────────────────┐
│ PHASE 4: TRACE CAPTURE (non-negotiable, before completing)     │
│  mkdir -p ~/projects/<slug>/traces/<chain-root-id>/             │
│  cp <transcript> .../attempt-<n>.jsonl                          │
│  Keyed by chain root for continuous numbering across attempts.  │
└───────────────────────────┬─────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ PHASE 5: COMPLETE WITH STRUCTURED REPORT                       │
│  Commit to card's branch (NEVER main, NEVER merge).            │
│  kanban_complete(metadata={harness_session_id, transcript_path, │
│  total_cost_usd, num_turns, changed_files, branch_name,         │
│  worktree_path, chain_root})                                    │
│  + completion-report comment (Approach, Key decisions,          │
│  Deviations, Dead ends, AC evidence mapping, Test evidence).    │
│  → Auto-promotes child review card to verifier.                 │
└─────────────────────────────────────────────────────────────────┘
```

### Budget Tiers

| Size | claude `--max-turns` | wall_secs (all harnesses) | cost ceiling (post-hoc) |
|------|---------------------|---------------------------|------------------------|
| small | 10 | 900 | $0.50 |
| medium | 25 | 2700 | $2.00 |
| large | 50 | 5400 | $5.00 |

If `total_cost_usd` exceeds the tier ceiling → flagged as **budget-exceeded** in completion report → reviewer treats as review-blocking finding.

### Harness Invocation Recipes

**Claude Code:**
```bash
timeout --signal=TERM --kill-after=30 <wall_secs> \
  claude -p "<prompt>" --allowedTools "Read,Edit,Bash" --max-turns <N> --output-format json
```
Warm resume: `claude -p -r <session_id> "<findings>"` from same worktree.

**Pi (preferred when available):**
```bash
timeout --signal=TERM --kill-after=30 <wall_secs> \
  pi --provider <provider> --model <model> -p "<prompt>" \
  --tools read,write,edit,bash,grep,find,ls --mode json
```
Warm resume: `pi --session <session_id> -p "<findings>"`.

**Codex:**
```bash
timeout --signal=TERM --kill-after=30 <wall_secs> \
  codex exec -s workspace-write --json -o /tmp/codex-last.txt "<prompt>"
```

**OpenCode:**
```bash
timeout --signal=TERM --kill-after=30 <wall_secs> \
  opencode run --format json "<prompt>"
```

### Key Pitfalls
- **Cold-restart blindness**: re-invoking fresh without reading prior findings or resuming the session.
- **Self-grading drift**: "tests pass and design looks fine" — stop at the gates.
- **Raw-coding fallback**: falling back to terminal/patch edits when harness errors out.
- **Contract disputes**: never modify contract/ACs — block with evidence.
- **Skipping heartbeats**: call `kanban_heartbeat` at least hourly (stale-timeout default 4h).
- **Trace skipped under time pressure**: protocol violation even if code is perfect.
- **Silent budget breach**: unflagged over-ceiling cost corrupts team's cost signal.
- **Worktree confusion**: resume is cwd-scoped — always resume from same worktree path.

---

## 7. JSON Node Definitions

These are the structured data shapes the developer produces and consumes, derived from the `developer-loop` skill and `kanban_complete` contract.

### 7.1 Completion Metadata (`kanban_complete.metadata`)

The machine-readable facts injected into the downstream verifier's context:

```json
{
  "harness_session_id": "string — vendor harness session ID (claude/codex/opencode/pi)",
  "transcript_path": "string — absolute path to trace ledger entry (~/.<harness>/.../session.jsonl)",
  "total_cost_usd": "float — total harness cost in USD",
  "num_turns": "int — number of harness turns executed",
  "changed_files": ["string — relative paths of files modified"],
  "branch_name": "string — git branch committed to (NEVER main, NEVER merge)",
  "worktree_path": "string — absolute path to worktree (MANDATORY for verifier to locate work)",
  "chain_root": "string — original developer card id (keys the trace directory)"
}
```

### 7.2 Card Body Schema (input — tech-lead authored)

```json
{
  "bead_id": "string — references bead for acceptance criteria (card REFERENCES, never copies)",
  "contract_ref": "string — path to contract.md in repo (committed by tech-lead)",
  "evals_cmd": "string — executable check command",
  "Size": "enum — small | medium | large",
  "Harness": "enum — claude | codex | opencode | pi",
  "constraints": "string — repo conventions, tool constraints",
  "context_plan": "string — what to read / not read"
}
```

### 7.3 Retry Card Body Extensions (fix cards — reviewer authored)

```json
{
  "Review-Iteration": "int — iteration number (1 = first fix round)",
  "Chain-Root": "string — original developer card id",
  "Resume-Session": "string — harness session_id to warm-resume",
  "Branch": "string — git branch from original attempt",
  "Worktree": "string — worktree path from original attempt (workspace_kind: dir)"
}
```

### 7.4 Trace Ledger Entry

```json
{
  "ledger_path": "~/projects/<slug>/traces/<chain-root-id>/attempt-<n>.jsonl",
  "attempt_number": "int — continuous across all fix rounds (attempt-1 = first run)",
  "chain_root_id": "string — original developer card id",
  "source_transcript": "string — harness-native transcript path"
}
```

### 7.5 Budget Tier Node

```json
{
  "small": {"max_turns_claude": 10, "wall_secs": 900, "cost_ceiling_usd": 0.50},
  "medium": {"max_turns_claude": 25, "wall_secs": 2700, "cost_ceiling_usd": 2.00},
  "large": {"max_turns_claude": 50, "wall_secs": 5400, "cost_ceiling_usd": 5.00}
}
```

### 7.6 Block Protocol Payloads

**Gates failure (transient):**
```json
{
  "kind": "transient",
  "reason": "Gates failed after warm-resume round: <actual failure output>",
  "comment_evidence": {
    "what_failed": "string — actual command output",
    "session_id": "string — harness session_id",
    "transcript_path": "string — ledger path",
    "cost_so_far": "float — USD"
  }
}
```

**Contract dispute (needs_input):**
```json
{
  "kind": "needs_input",
  "reason": "Contract/AC appears incorrect: <evidence>. Spec judgment belongs to tech-lead.",
  "comment_evidence": {
    "contract_ref": "string — path",
    "issue": "string — what seems wrong",
    "evidence": "string — supporting detail"
  }
}
```

### 7.7 AC Evidence Mapping Node (mandatory in completion report)

```json
{
  "ac_mappings": [
    {
      "criterion_id": "AC1",
      "criterion_text": "string — verbatim from bead",
      "met": true,
      "proof_claim": "string — test name + actual output proving it"
    },
    {
      "criterion_id": "AC3",
      "criterion_text": "string — verbatim from bead",
      "met": false,
      "reason": "string — why not met, what's missing"
    }
  ]
}
```

---

## Appendix: Configuration Summary

**`config.yaml` highlights:**
- **Model**: `glm-5.2` via `zai` provider, 1M context length, 30s rate limit delay
- **Toolsets**: `hermes-cli`, `kanban`
- **Plugins enabled**: `kanban_chains`, `skill_enforcer`
- **Mandatory skill**: `developer-loop` (enforced by `skill_enforcer`)
- **Kanban**: max 3 in-progress per profile / total; 4h stale timeout
- **Disabled skills**: ~50 skills (mostly mattpocock suite + ponytail) — the developer is deliberately stripped to a focused toolset
- **Active skills of note**: `claude-code`, `codex`, `opencode` (harness invocation), `caveman` (terse reporting), `developer-loop` (doctrine), `team-delegation` (coordination)

**`SOUL.md` highlights:**
- Specialty: "autonomous developer — thin governance wrapper around vendor coding harnesses"
- Constitution: frozen invariants (never edit conscience/evolution engine; snapshot before self-edit; specialization is one-shot bootstrap)
- Skill index lists only `developer-loop`
- **No `debug-loop` skill referenced or present**
