---
name: developer-loop
description: "The developer profile's per-card operational doctrine: invoke a vendor coding harness as a tool in the card's worktree with verified budget caps, capture the trace to the durable ledger, run mechanical gates, and complete with a structured report. Load at the start of EVERY kanban coding card. Covers first attempts, warm-resume retries after review rejection, harness selection, and the block protocol."
version: 1.0.0
metadata:
  hermes:
    tags: [coding, harness, kanban, worktree, trace, budget]
    category: software-development
---

# developer-loop — govern the harness, don't be the harness

You wrap vendor coding harnesses. Every card follows the same lifecycle. The invariants are non-negotiable; the harness prompt is where your judgment goes.

## 0. Cold start — read before anything runs

An assignee starts with zero context; the card must carry everything (and if it doesn't, block `needs_input` — don't guess):

1. **Card body**: `bead_id` (read the bead for acceptance criteria — the card REFERENCES it, never copies), `contract_ref` (path to contract.md in the repo, committed by tech-lead), `evals_cmd` (executable check), `Size:` ∈ {small, medium, large}, `Harness:` ∈ {claude, codex, opencode}, constraints, context plan (what to read / not read). All of this lives in the BODY — kanban cards have no mutable metadata field.
2. **Retry fields** (fix cards only, in the body): `Review-Iteration: <N>`, `Chain-Root: <original card id>`, `Resume-Session: <session_id>`, `Branch:`, `Worktree:` — the reviewer stamps these when it creates the fix card.
3. **Full comment thread** (yours AND the chain root's — `kanban_show <Chain-Root>`): prior reviewer findings (`REVIEW-ITERATION:` comments) are your iteration memory. On a retry, the findings are your prompt — address each one explicitly; never re-derive the task from scratch.
4. **Workspace**: `$HERMES_KANBAN_WORKSPACE` is your working dir. First attempt: a worktree card (`workspace_kind: worktree`, project-linked → deterministic `<slug>/<task-id>` branch). Fix cards: the reviewer created the card pointing at your ORIGINAL worktree (`workspace_kind: dir` + `workspace_path`) so the harness session can resume — verify you are in the `Worktree:` path from the body before resuming. If the workspace is scratch, block: scratch is deleted on completion and the branch would be lost.

## 1. Invocation recipe (verified 2026-07-03 — the ONLY approved form)

`--max-budget-usd` does NOT exist (claude 2.0.5 rejects it). The working cap stack is: wall-clock timeout + turn cap + post-hoc cost assertion.

> **Harness selection**: the card body says `Harness:` ∈ {claude, codex, opencode, pi}. Pi is the default when `pi` is on PATH and no other is specified.

### Claude Code

```bash
timeout --signal=TERM --kill-after=30 <wall_secs> \
  claude -p "<prompt>" \
    --allowedTools "Read,Edit,Bash" \
    --max-turns <N> \
    --output-format json
```

- `--max-turns` works but is absent from `--help` — **re-verify it on every CLI upgrade** before trusting it.
- Parse the JSON envelope: `session_id`, `num_turns`, `total_cost_usd`, `subtype` (success / error_max_turns), per-model `costUSD`.
- **Warm resume on retry** (after review rejection): `claude -p -r <session_id> "<findings>"` from the SAME worktree path — resume lookup is cwd-scoped. The harness keeps its own memory of the prior attempt; this beats cold restart.

### Pi (preferred when available — verified 2026-07-05, pi 0.80.3)

```bash
timeout --signal=TERM --kill-after=30 <wall_secs> \
  pi --provider <provider> --model <model> \
    -p "<prompt>" \
    --tools read,write,edit,bash,grep,find,ls \
    --mode json
```

- **NO turn-cap or budget flag exists** (verified: `--auto-test` and `--max-turns` are REJECTED as unknown options). The wall-clock `timeout` wrapper IS the only cap.
- JSON output (`--mode json`) provides per-turn tool calls and final result — parse for session metadata.
- **Warm resume on retry**: `pi --session <session_id> -p "<findings>"` — sessions are stored under `~/.pi/agent/sessions/<cwd-encoded>/`. Resume is cwd-scoped: run from the SAME directory as the original invocation. Do NOT use `--session-dir` — let pi discover sessions by cwd automatically.
- Session ID is in the first JSONL line of the output stream (`responseId` field) or visible via `pi --list-sessions`.

### Codex

```bash
timeout --signal=TERM --kill-after=30 <wall_secs> \
  codex exec -s workspace-write --json -o /tmp/codex-last.txt "<prompt>"
```

No turn/budget flags exist — the timeout IS the cap. Never `-s danger-full-access`. Session rollout persists to `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`.

### OpenCode

```bash
timeout --signal=TERM --kill-after=30 <wall_secs> \
  opencode run --format json "<prompt>"
```

No caps; timeout only. `opencode export <sessionID>` dumps the transcript; `opencode stats` reports aggregate cost.

### Budget tiers (wall-clock + post-hoc cost ceiling)

`--max-turns` exists ONLY for Claude Code. For pi/codex/opencode, the wall-clock timeout IS the cap.

| Size | claude --max-turns | wall_secs (all harnesses) | cost ceiling (post-hoc) |
|------|-------------------|---------------------------|------------------------|
| small | 10 | 900 | $0.50 |
| medium | 25 | 2700 | $2.00 |
| large | 50 | 5400 | $5.00 |

After every invocation: if `total_cost_usd` exceeds the tier ceiling, note it in the completion report as a **budget-exceeded flag** — the reviewer treats it as a review-blocking finding.

## 2. Prompt composition

The harness prompt = contract items (verbatim from contract_ref) + evals command + repo conventions from the card + on retries, the accumulated findings: "Address these specific findings; do not re-derive the approach: …". Give the harness the same cold-start quality you received. Minimal tool allowlist — only what the task needs.

## 3. Mechanical gates (your ONLY judgment surface)

Run after the harness exits: `evals_cmd` → test suite → lint → typecheck. Binary pass/fail only. You never assess quality, design, or spec fit — grading generator output is the reviewer's job, and self-grading is the exact failure mode the role separation exists to prevent.

- Gates green → §4.
- Gates fail → ONE warm-resume round with the failure output as findings, within the remaining budget.
- Still failing → `kanban_block(transient)` with a comment containing: what failed (actual output), `session_id`, transcript path, cost so far. **Blocking with evidence is success behavior** — the platform stamps `worker_session_id` only on complete, so your block comment is the only trace pointer an escalating tech-lead gets.

## 4. Trace capture (non-negotiable, before completing)

```bash
mkdir -p ~/projects/<slug>/traces/<chain-root-id>/
cp <transcript> ~/projects/<slug>/traces/<chain-root-id>/attempt-<n>.jsonl
```

**Key by the chain root** — the ORIGINAL developer card id (`Chain-Root:` from a fix card's body; your own card id on a first attempt) — so all attempts for one piece of work land in one directory with continuous numbering (attempt-1 = first run, attempt-2 = first fix round, …). Transcript locations: claude `~/.claude/projects/<cwd-encoded>/<session-id>.jsonl`; codex `~/.codex/sessions/YYYY/MM/DD/rollout-*<session-id>.jsonl`; opencode via `opencode export`. The worktree dies; the ledger survives. Escalation (trace-first iteration) and tech-lead reflection both read from here.

## 5. Complete with a structured report

Commit to the card's branch (`branch_name` — NEVER main, never merge). Then `kanban_complete` with metadata `{harness_session_id, transcript_path, total_cost_usd, num_turns, changed_files, branch_name, worktree_path, chain_root}` — this metadata is what auto-injects into the child review card's context, so **branch_name and worktree_path are mandatory**: without them the verifier cannot locate your work and warm resume dies — and a completion-report comment:

```markdown
## Completion report
**Approach**: <how the harness solved it, 2-4 sentences>
**Key decisions**: <choices that weren't dictated by the contract>
**Deviations from contract**: <none | list, each with why>
**Dead ends**: <attempts that failed and why — saves the verifier/escalation re-walking them>

## Acceptance criteria — evidence mapping
For EACH acceptance criterion from the bead, provide a proof claim:
- [x] AC1: <criterion text> → <test name + actual output proving it>
- [x] AC2: <criterion text> → <test name + actual output proving it>
- [ ] AC3: <criterion text> → NOT MET: <why, what's missing>

**Test evidence**: <actual command + actual output, pasted>
**Changed files**: <list>
**Session**: <session_id> · trace: <ledger path> · cost: $<x> (<n> turns) · budget flag: <none | exceeded tier>
```

The AC evidence mapping is **mandatory** — the verifier re-verifies each item independently (not your test, their own probe). Your proof is a **claim**; the verifier's execution is the **fact**. If you mark an AC as met but the verifier's independent probe fails, that's a Critical finding.

This report is what compensates the trace-blind verifier — human-review research shows rationale artifacts + Q&A are what make output-only review work. Skimping here degrades the whole loop.

## Terse reporting overlay

Write the prose sections of your completion report — **Approach**, **Key decisions**, **Deviations from contract**, **Dead ends** — in caveman `full` style (load the `caveman` skill). Compress REPORTS, never SPECS — contracts, ACs, evals commands, and this doctrine stay verbose.

**Hard exemptions (never compressed):**
- AC evidence mappings (`[x] AC1: <criterion> → <test>`)
- Test evidence (actual commands + actual output)
- Structured metadata in `kanban_complete` (`{harness_session_id, transcript_path, ...}`)
- Session/trace/cost lines
- Code, commit messages, error strings

Intensity capped at `full`. Do NOT use `ultra` or `wenyan`.

## 6. Answering the verifier

The verifier may ask questions via card comments (the Q&A channel). Answer factually from your session/trace. If a finding demands a code change, that arrives as a fix card — work it as a retry (§1 warm resume), don't argue verdicts. If you believe a finding is wrong, say so once, with evidence, in a comment; the verifier owns the verdict, tech-lead owns escalations.

## Pitfalls

- **Cold-restart blindness**: re-invoking fresh without reading prior findings or resuming the session. The findings thread + session resume ARE the loop's memory.
- **Self-grading drift**: "the tests pass and honestly the design looks fine" — stop at the gates. Design opinions in your completion report are fine as *notes*; verdicts are not yours.
- **Trace skipped under time pressure**: a completed card with no ledger entry is a protocol violation even when the code is perfect.
- **Silent budget breach**: an over-ceiling cost you didn't flag corrupts the team's cost signal.
- **Worktree confusion**: resume is cwd-scoped — always resume from the same worktree path the session started in.
