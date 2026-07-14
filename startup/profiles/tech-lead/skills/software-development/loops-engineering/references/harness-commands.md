# Harness Commands — Reference

Quick CLI reference for the three coding-agent harnesses. Load when selecting a harness or writing delegation commands.

## Claude Code (`claude`)

Preferred for most tasks. v2.x.

### Print mode (non-interactive — preferred for loops)
```bash
terminal(command="timeout --signal=TERM --kill-after=30 900 claude -p 'task description' --allowedTools 'Read,Edit,Bash' --max-turns 10 --output-format json", workdir="/project", timeout=960)
```
- Skips all interactive dialogs. Ideal for automation. The `timeout` wrapper + `--output-format json` are part of the approved form (Budget safety below) — not optional extras.
- The JSON envelope returns `session_id`, `num_turns`, `total_cost_usd`, `subtype` (success/error_max_turns/error_during_execution).
- `--resume <session_id>` to continue a previous session (cwd-scoped).

### Interactive PTY (for multi-turn sessions)
```bash
# Start tmux session
terminal(command="tmux new-session -d -s claude-work -x 140 -y 40")
terminal(command="tmux send-keys -t claude-work 'cd /project && claude' Enter")
# Monitor
terminal(command="sleep 15 && tmux capture-pane -t claude-work -p -S -50")
# Send follow-up
terminal(command="tmux send-keys -t claude-work 'next task' Enter")
```

### Key flags
| Flag | Effect |
|------|--------|
| `-p, --print` | Non-interactive one-shot (exits when done) |
| `--max-turns <n>` | Limit agentic loops — WORKS but is absent from `--help` (verified live on 2.0.5); re-verify on every CLI upgrade |
| `--allowedTools <tools>` | Whitelist specific tools |
| `--dangerously-skip-permissions` | Auto-approve all tool use |
| `--model <alias>` | Model selection: sonnet, opus, haiku |
| `--append-system-prompt <text>` | Add to system prompt |
| `-r, --resume <session_id>` | Resume a prior session (cwd-scoped — run from the same directory) |

> ⚠️ `--max-budget-usd` DOES NOT EXIST (verified: claude 2.0.5 rejects it as unknown option). There is no per-invocation dollar cap. Cost control = turn cap + wall-clock timeout + post-hoc cost assertion from the JSON envelope (see Budget safety below).

### Trace persistence (the trace ledger)

Every `claude -p` run writes its FULL transcript (thinking, tool_use, tool_result) to `~/.claude/projects/<cwd-encoded>/<session-id>.jsonl` by default, resumable by a separate process. After every invocation, copy it to the durable ledger:

```bash
mkdir -p ~/vault/traces/<project-or-board>/<bead-or-card-id>/
cp ~/.claude/projects/<cwd-encoded>/<session-id>.jsonl \
   ~/vault/traces/<project-or-board>/<bead-or-card-id>/attempt-<n>.jsonl
```

Worktrees die; the ledger survives. Trace-first iteration, escalation, and reflection all read from here.

## Codex (`codex`)

OpenAI's autonomous coding agent CLI. Requires git repository.

```bash
# Headless (preferred for loops) — codex exec works non-interactively
terminal(command="timeout --signal=TERM --kill-after=30 2700 codex exec -s workspace-write --json -o /tmp/codex-last.txt '<task>'", workdir="/project", timeout=2760)
```

- NO turn or budget flags exist (verified 0.139.0) — the `timeout` wrapper IS the cap
- Sandbox: always `-s read-only` or `-s workspace-write`; never `danger-full-access`
- Session rollout persists to `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` by default — copy to the trace ledger
- Auth: `OPENAI_API_KEY` or Codex OAuth (`~/.codex/auth.json`); requires git repo
- Interactive PTY mode still available for exploratory sessions

## OpenCode (`opencode`)

Provider-agnostic, open-source. Good for parallel worktrees.

```bash
# Headless
terminal(command="timeout --signal=TERM --kill-after=30 2700 opencode run --format json '<task>'", workdir="/project", timeout=2760)
```

- NO turn or budget flags (verified 1.17.10) — `timeout` wrapper is the cap
- `opencode export <sessionID>` dumps the full transcript (→ trace ledger); `opencode stats` reports aggregate token/cost totals (the only harness with built-in cumulative cost reporting)
- Auth: `opencode auth login` or provider env vars (OPENROUTER_API_KEY, etc.)

## Worktree pattern (all harnesses)

Parallel agents need isolation to avoid file conflicts:

```bash
git worktree add ../project-task-A feature/task-a
git worktree add ../project-task-B feature/task-b
# Each harness runs in its own worktree directory
```

(No `--worktree` flag exists in claude 2.0.5 — verified; create worktrees manually as above, or let a project-linked kanban card provision one.)

## Kanban CLI flag syntax (critical)

The `--board` flag goes BEFORE the subcommand, not after. Getting this wrong causes silent failures.

```bash
# CORRECT — board flag before subcommand (use the project's board slug)
hermes kanban --board <project-slug> create "[issue] title" --assignee tech-lead
hermes kanban --board <project-slug> list --assignee tech-lead --json
hermes kanban --board <project-slug> archive t_abc123

# WRONG — board flag after subcommand (silently ignored or error)
hermes kanban create "[issue] title" --board <project-slug> --assignee tech-lead
```

When a script creates tasks across multiple boards, pass the board per-command. The current board (set via `hermes kanban boards switch <slug>`) is the fallback when `--board` is omitted.

**Duplicate prevention (3 controls):**
1. Check `hermes kanban --board <slug> list --assignee <profile> --json` before creating — match beads IDs in task titles
2. Use `--idempotency-key "beads-<issue-id>"` on every create call
3. Set `max_in_progress_per_profile` in each profile's `config.yaml` to bound same-profile concurrency (at the current cap of 6, up to 6 run at once — so controls 1+2 are the real duplicate guard)

## Budget safety (verified recipe — 2026-07-03)

There is NO per-invocation dollar cap in any installed harness. The working cap stack is three layers:

1. **Wall-clock timeout** (all harnesses): `timeout --signal=TERM --kill-after=30 <wall_secs> <harness ...>`
2. **Turn cap** (claude only): `--max-turns <N>`
3. **Post-hoc cost assertion**: parse the claude JSON envelope — `jq -r '.total_cost_usd, .num_turns, .subtype, .session_id'` — and treat `total_cost_usd` over the tier ceiling as a review-blocking flag on the task. The envelope's `session_id` also enables the budget loop: kill at the turn cap, inspect, resume with `-r`.

| Tier | --max-turns | wall_secs | cost ceiling (post-hoc) |
|------|------------|-----------|------------------------|
| Small (bug fix, small feature) | 10 | 900 | $0.50 |
| Medium (refactor, integration) | 25 | 2700 | $2.00 |
| Large (full feature) | 50 | 5400 | $5.00 |

Hermes-side backstops (set these; they exist in code but default OFF): per-task `max_runtime_seconds` at card creation (dispatcher SIGTERM→SIGKILL→timed_out requeue), and the `kanban:` block in each profile's `startup/profiles/<profile>/config.yaml` — the dispatcher reads the **lock-holding gateway's OWN profile config** (the `kanban:` block of whichever gateway holds `startup/kanban/.dispatcher.lock`), NOT the global `startup/config.yaml` and NOT `~/.hermes/config.yaml`. The lock-holder is non-deterministic, so **all profile configs must agree** on caps for a change to take effect regardless of which gateway dispatches; caps load at gateway boot (restart to apply).

Aggregate spend: per-profile `state.db` tracks per-session token totals (queryable via SQL sum); harness-child spend is invisible to Hermes unless the invoker writes the JSON-envelope cost back to the task — which is why the completion report requires it.
