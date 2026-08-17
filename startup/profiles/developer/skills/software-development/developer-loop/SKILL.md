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

1. **Card body**: `bead_id` (read the bead for acceptance criteria — the card REFERENCES it, never copies), `contract_ref` (path to contract.md in the repo, committed by tech-lead), `evals_cmd` (executable check), `Size:` ∈ {small, medium, large}, `Harness:` ∈ {claude, codex}, constraints, context plan (what to read / not read). All of this lives in the BODY — kanban cards have no mutable metadata field.
2. **Retry fields** (fix cards only, in the body): `Review-Iteration: <N>`, `Chain-Root: <original card id>`, `Resume-Session: <session_id>`, `Branch:`, `Worktree:` — the reviewer stamps these when it creates the fix card.
3. **Full comment thread** (yours AND the chain root's — `kanban_show <Chain-Root>`): prior reviewer findings (`REVIEW-ITERATION:` comments) are your iteration memory. On a retry, the findings are your prompt — address each one explicitly; never re-derive the task from scratch.
4. **Workspace**: `$HERMES_KANBAN_WORKSPACE` is your working dir. First attempt: a worktree card (`workspace_kind: worktree`, project-linked → deterministic `<slug>/<task-id>` branch). Fix cards: the reviewer created the card pointing at your ORIGINAL worktree (`workspace_kind: dir` + `workspace_path`) so the harness session can resume — verify you are in the `Worktree:` path from the body before resuming. If the workspace is scratch, block: scratch is deleted on completion and the branch would be lost.

## 1. Invocation recipe (verified 2026-07-03 — the ONLY approved form)

`--max-budget-usd` does NOT exist (claude 2.0.5 rejects it). The working cap stack is: wall-clock timeout + turn cap + post-hoc cost assertion.

> **Harness selection**: the card body says `Harness:` ∈ {claude, codex}. Pi is the default when `pi` is on PATH and no other is specified.

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
    --no-extensions --no-skills --no-prompt-templates --no-context-files \
    -p "<prompt>" \
    --tools read,write,edit,bash,grep,find,ls \
    --mode json
```

- **Host extension guardrails (verified 2026-08-16, pi 0.84.1)**: WITHOUT `--no-extensions`, pi loads taskboard/git-guardrails extensions that BLOCK file edits on `main` ("Branch guard: Cannot edit files on 'main' — protected branch") and redirect the agent into `bd create`/`task` tooling — the run exits 0 having written NOTHING. Always use the sanitized flag set above on hosts where pi has extensions installed. Detect after exit: empty `git diff` + `.beads/guardrails-blocked.log` appearing = relaunch sanitized (count it as an invocation failure, not a warm-resume retry).

- **NO turn-cap or budget flag exists** (verified: `--auto-test` and `--max-turns` are REJECTED as unknown options). The wall-clock `timeout` wrapper IS the only cap.
- JSON output (`--mode json`) provides per-turn tool calls and final result — parse for session metadata. **Event schema drift (pi 0.84.1, verified 2026-08-16)**: session id is in the `type:"session"` line under `id` (NOT `responseId`); tool events `tool_execution_start`/`end` carry `toolName` + `args` keys (NOT `tool`/`name`/`arguments`). A parser keyed on the old fields silently yields ZERO events — which looks identical to "no violations" in a fence audit. After parsing, always sanity-check the event count against the raw line count (`tool_execution_start` should be >0 for any real coding run) before concluding the audit is clean. **Cost telemetry (zai provider, pi 0.84.x, verified 2026-08-16)**: envelope has NO cost object and NO `final` event — terminal event is `agent_settled` (`{}`). Report cost as n/a (disclose, never guess) and count turns from `turn_end` events.
- **Host approval gates**: `execute_code` wrappers and terminal `python -c`/heredoc-python are blocked on some hosts. Write parse/patch scripts to a file in the workspace (`write_file`) and run via `bash <script>` instead. The gate ALSO pattern-matches forbidden-command strings inside the harness PROMPT text itself — quoting e.g. `git reset --hard` inside a "NEVER run this" clause blocks the whole launch (verified 2026-08-16, wf-livetest6). Phrase git bans descriptively ("never rewrite history, never force-clean the tree"), never quote the literal command. **Sharper rule (verified 2026-08-17, t_c613499e — cost 2 crashed runs)**: this applies to the GOVERNOR's own terminal() too — any inline compound shell snippet (multi-command `a; b; /bin/sh -c '...'` probes, heredocs, `python -c`) can return `status: pending_approval` and HANG a headless kanban worker; the worker then exits rc=0 without complete/block → dispatcher marks "protocol violation" and burns a retry. In headless runs: one simple command per terminal() call, or script-to-file + `bash <file>`. Never inline shell snippets that merely *probe* the environment. **Also flagged (t_71fb6f07, 2026-08-17)**: `rm -rf /tmp/<dir> && git clone ... && cd ... && pytest` as ONE inline compound ("delete in root path" pattern) — same fix, script-to-file.
- **pi flag drift (verified 2026-08-17, pi on this host)**: `-C` is REJECTED as unknown option ("Error: Unknown option: -C", instant exit 1). `--no-context-files` already suppresses repo context files; never add `-C`. Trace schema v3: session id in first `type:"session"` line's `id`; final assistant text lives in `message_end` events (parse `message.content[].text` blocks); turn count = `turn_end` events. A last assistant text that is bare noise (e.g. "13" from a `grep FAILED | wc -l`) means the run died mid-report — repo state + trace bash-command tail are ground truth.
- **Hermetic-proof clone recipe pitfall (t_71fb6f07)**: `cp casecount.py tests/test_behavior.py <clone>/` drops test_behavior.py at the clone ROOT (shell brace-expansion semantics of trailing `/`) → pytest "import file mismatch" when a test collects `.` — looks like YOUR change broke collection. Copy into explicit destinations (`cp tests/test_behavior.py <clone>/tests/`).
- **Warm resume on retry**: `pi --session <session_id> -p "<findings>"` — sessions are stored under `~/.pi/agent/sessions/<cwd-encoded>/`. Resume is cwd-scoped: run from the SAME directory as the original invocation. Do NOT use `--session-dir` — let pi discover sessions by cwd automatically.
- Session ID is in the first JSONL line of the output stream (`responseId` field) or visible via `pi --list-sessions`.

### Codex

```bash
timeout --signal=TERM --kill-after=30 <wall_secs> \
  codex exec -s workspace-write --json -o /tmp/codex-last.txt "<prompt>"
```

No turn/budget flags exist — the timeout IS the cap. Never `-s danger-full-access`. Session rollout persists to `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`.

### Budget tiers (wall-clock + post-hoc cost ceiling)

`--max-turns` exists ONLY for Claude Code. For pi/codex, the wall-clock timeout IS the cap.

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

**Key by the chain root** — the ORIGINAL developer card id (`Chain-Root:` from a fix card's body; your own card id on a first attempt) — so all attempts for one piece of work land in one directory with continuous numbering (attempt-1 = first run, attempt-2 = first fix round, …). Transcript locations: claude `~/.claude/projects/<cwd-encoded>/<session-id>.jsonl`; codex `~/.codex/sessions/YYYY/MM/DD/rollout-*<session-id>.jsonl`. The worktree dies; the ledger survives. Escalation (trace-first iteration) and tech-lead reflection both read from here.

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

- **Shared-workspace collisions (dir cards)**: parallel chains fanned out with the same `workspace_path` share ONE checkout. A sibling chain's harness can rewrite your target file AFTER your harness exits (verify: grep your change-markers in the file, compare mtimes vs your harness exit, `pgrep -af 'pi --provider|codex'`). If clobbered, recover your exact content from the harness transcript (pi: `tool_execution_start` events carry edit oldText/newText) and land it via temp-index plumbing — `GIT_INDEX_FILE=<tmp> git read-tree HEAD` + `update-index --add --cacheinfo` + `write-tree` + `commit-tree` + CAS-guarded `update-ref refs/heads/main $NEW $OLD` — which never touches the shared working tree or index, so the sibling's uncommitted state survives. Gate recovered content in an isolated sandbox (mktemp dir + HEAD's files + yours, fresh venv, redirect hardcoded BIN paths in tests) BEFORE committing, and warn the sibling + verifier cards in comments (including any now-unsatisfiable contract ACs that pinned pre-fix behavior).
- **Cold-restart blindness**: re-invoking fresh without reading prior findings or resuming the session. The findings thread + session resume ARE the loop's memory.
- **Self-grading drift**: "the tests pass and honestly the design looks fine" — stop at the gates. Design opinions in your completion report are fine as *notes*; verdicts are not yours.
- **Raw-coding fallback**: falling back to terminal/patch edits when the harness errors out or a fix looks trivial. The harness exists for a reason — vendor-tuned coding loops are the whole point of your architecture. Retry the harness with corrected instructions; only use raw edits if no harness is available for the task.
- **Out-of-scope harness edits (silent gate-tampering)**: after the harness reports green, audit EVERY edit/write it made — replay `tool_execution_start` events from the transcript and check each `args.path` against the card's allowed file scope. A harness facing a failing gate will "fix" it by editing whatever is failing, including fenced/untracked artifacts of other workers or its own eval harness — weakening foreign assertions to force green. If found: reverse-apply exactly using the trace's `oldText`/`newText` pairs (they are verbatim), re-verify restoration byte-level, disclose in the completion report, and treat the underlying failure as a real finding (often a genuine contract conflict → block, don't re-run the harness hoping it behaves).
- **Operator scripts inside the repo break gates**: `make check` style targets often lint the WHOLE tree (`ruff check .`) including untracked dirs like `.driver/`. An audit/probe script staged there fails the lint gate you yourself must run. Keep operator scripts outside the repo, or move them to the trace ledger BEFORE running gates.
- **Contract disputes**: if the contract or acceptance criteria seem wrong, do NOT modify them — `kanban_block(needs_input)` with your evidence. Spec judgment belongs to tech-lead; you and the verifier cannot re-contract anyone.
- **Stale AC counts**: a card's expected test count rots when sibling tickets land between card authoring and your run (e.g. card said 264; suite was already 288 after a parallel C3 ticket). Re-baseline BEFORE the harness (run the suite at HEAD, count tests, compute expected = current + card's net delta) and put the arithmetic in the completion report — never silently chase the stale number or edit tests to hit it.
- **pytest summary line invisible**: pyproject `addopts = "-q ..."` + a `-q` on the CLI doubles the quiet flag and SUPPRESSES the final "N passed" line — a gate script grepping for it concludes "failure" on a green run. Count with `pytest | tail -1` (single quiet) or `--co -q | tail -1`, not `-q -q`.
- **Background-shell env corruption**: processes launched with terminal(background=true) can inherit a mangled hermes shell snapshot (visible symptom: `bash: export: ... not a valid identifier` on startup) — subprocess-dependent tests (broken-pipe/PIPESTATUS probes) may fail there while passing deterministically in foreground. Re-run any background gate failure in FOREGROUND before treating it as a real finding; never "fix" a test for a failure that only reproduces in background.
- **Harness refuses to commit on its own flaky gate**: if the harness finishes the edit work but declines to commit because ITS shell hit the background-env flake above, re-run the gates yourself in foreground, audit the trace scope as usual, and commit via the pathspec form yourself. Disclose the split (harness edited, governor committed) in the report.
- **Skipping heartbeats on long cards**: call `kanban_heartbeat` at least hourly, or the dispatcher reclaims your task after the stale-timeout (default 4h).
- **Trace skipped under time pressure**: a completed card with no ledger entry is a protocol violation even when the code is perfect.
- **Silent budget breach**: an over-ceiling cost you didn't flag corrupts the team's cost signal.
- **Worktree confusion**: resume is cwd-scoped — always resume from the same worktree path the session started in.
- **Read-only git excursions evade the scope audit**: replaying tool_execution_start catches edit/write scope, but NOT read-only excursions like `git stash` → `git checkout <sha>` → `git checkout main` → `git stash pop` (harnesses do this to consult historical test versions). Benign IF the excursion closes balanced — verify empty `git stash list`, HEAD back on the branch, working-tree diff still exactly your scoped files — and disclose it in the report. Only out-of-scope edits/writes are fence violations.
- **Gate-invisible semantic vacuity (fitting the seam ≠ preserving the test's question)**: after a runner-seam migration, tests can keep passing while no longer testing what their name says. Verified case (2026-08-17, t_d5408b74): a console-vs-module parity test took BOTH a plain seam fixture AND an override fixture that monkeypatched the env var at FIXTURE-BUILD time — pytest builds all fixtures before the body, so both invocations ran the same modality and the byte-parity assertion compared the module to itself (vacuous green). Any test whose purpose is to compare two RESOLUTIONS must control the override from INSIDE the body (call side A, then setenv/monkeypatch, then call side B) — never via a co-requested fixture. Audit migrated tests for this class: read each test's QUESTION, not just its assertions.
