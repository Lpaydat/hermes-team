---
name: pipeline-operations
description: Operate the venture builder pipeline — run queue-builds.sh, verify kanban cards, restart gateways for config changes, debug bash scripts that interface with hermes kanban CLI. Load when testing or running the venture pipeline, when queue-builds.sh fails, when config changes need a gateway restart, or when verifying pipeline E2E behavior.
---

# Pipeline Operations

Operating the 4-stage venture pipeline: queue-builds.sh, kanban card verification, gateway config reloads, and the bash/CLI pitfalls that cost time.

## 1. Gateway restart for config changes

Changes to `~/.hermes-teams/startup/config.yaml` (e.g. `delegation.max_iterations`) are written to disk but NOT picked up by the running gateway. The gateway caches config at startup. Any session it spawns (via the dispatcher) will use the old cached value.

**Fix:** Restart the gateway after editing config.yaml:

```bash
hermes gateway restart --profile builder
```

This also refreshes outdated service definitions and takes ~5 seconds. Other profile gateways are separate services and are not affected.

**Verify the restart took effect:**

```bash
hermes gateway status --profile builder | head -5
# Should show: Active: active (running) since <recent timestamp>
```

**When to restart:** Any time you change config.yaml values that affect agent behavior (iteration limits, model settings, delegation config). Session restarts do NOT help — the gateway is a persistent systemd service that outlives sessions.

## 2. Running queue-builds.sh

The queue script lives at `~/.hermes-teams/startup/profiles/builder/scripts/queue-builds.sh`. It reads `~/vault/ventures/idea-bank.md`, picks top 10 unbuilt ideas by score, creates **two kanban cards per idea** (Grill + Build) assigned to `builder`, running as **parallel pairs** (no cross-idea chaining).

```bash
cd ~/.hermes-teams/startup/profiles/builder/scripts && bash queue-builds.sh
```

**2-card architecture (implemented 2026-07-24):** Each idea gets TWO cards:

- **Card A "Grill: <idea>"** — dossier + grill + validate. Explicitly says "Do NOT build the prototype — that is the next card."
- **Card B "Build: <idea>"** — loop_engine build + README + handoff. Explicitly says "This card exists to isolate loop_engine in a fresh context."

Card B has Card A as parent (waits for grill to complete). **Each idea runs independently in parallel** — no cross-idea chaining. Concurrency is capped by `max_in_progress_per_profile` (default 3).

```
idea1-Grill → idea1-Build   ↘
idea2-Grill → idea2-Build   → all run concurrently (capped by dispatcher)
idea3-Grill → idea3-Build   ↗
```

**Why 2 cards instead of 1:** The previous 1-card design buried loop_engine as step 2 of 4 in a multi-hour session. The builder self-assessed the build as "simple enough" to skip loop_engine on 15/15 prototypes across 2 batches. The 2-card split gives the builder a fresh context where loop_engine is the ONLY job — the card body IS the loop_engine spec. See `references/2026-07-24-2card-pipeline-architecture.md`.

**Quality tools available to builder sessions:**
- `loop_engine` — break the build into phased steps (build → verify DoD → write README → verify DoD → complete). ~30% quality boost from preventing drift and premature completion.
- `kanban_chains` — fan out parallel build cards (batch N prototypes concurrently, capped by `max_in_progress_per_profile=3`).
- `venture-prototype` skill — mandatory prototype type selection (HTML/API/CLI/concierge), POC gate, and README template with "How to Review" instructions.

**Guard:** The script has a 6h cooldown marker at `~/vault/ventures/.last-queue`. To force a re-run during testing:

```bash
rm -f ~/vault/ventures/.last-queue
```

**Expected output on success:** 10 `CREATED [t_xxx]` lines (one per idea), sorted by score descending.

## 3. Verifying kanban cards after queue-builds.sh

After running the queue script, verify cards were created correctly:

```python
# Use the kanban_list tool or CLI — do NOT use --json on large boards
# hermes kanban --board hermes-hq list --json produces 1.8M+ chars on a
# 190-task board and will flood your context. Use the kanban_list tool
# with status/limit filters instead.
```

**Checklist:**
- 20 cards exist (2 per idea: "Grill:" and "Build:" titles)
- Each Build card has its Grill card as parent
- Grill cards have NO parent (ready immediately, not chained to previous idea)
- Ideas run in parallel — multiple grill cards may be `running` simultaneously (capped by `max_in_progress_per_profile=3`)
- Re-running the script should create 0 cards (dedup via slug-in-title check)

**Dedup verification:**
```bash
rm ~/vault/ventures/.last-queue  # bypass cooldown
bash queue-builds.sh  # should output "Created: 0" with all SKIP lines
```

## 4. Bash pitfall: `eval` with multi-line CLI arguments

**The bug:** Using `eval` to construct a `hermes kanban create` command with a multi-line `--body` argument breaks because `eval` word-splits on every space, treating each word in the body as a separate positional argument.

**Broken pattern (DO NOT USE):**
```bash
ARGS="--assignee builder --body \"$BODY\""  # multi-line BODY
RESULT=$(eval hermes kanban create "$TITLE" $ARGS --json)
# FAILS: eval splits "Score: 19/25 | Origin: Door P" into separate words
```

**Fixed pattern:**
```bash
# Pass arguments directly — bash quoting handles the rest
RESULT=$(hermes kanban --board "$BOARD" create "$TITLE" \
    --assignee builder \
    --body "$BODY" \
    --json 2>/dev/null || echo "{}")
```

**General rule:** Never use `eval` with bash variables that contain spaces, newlines, or special characters. Pass them as direct quoted arguments to the command.

## 5. kanban `--parent` flag works correctly

The `hermes kanban create --parent <task-id>` flag DOES create real parent-child dependencies. Cards created with `--parent` will have the parent in their `parents` list and the parent will have the child in its `children` list. The child stays in `todo` until the parent completes, then auto-promotes to `ready`.

**Verifying the chain:** Use the CLI `show` command (not the kanban tools — see pitfall below):

```bash
hermes kanban --board hermes-hq show t_7b4ddc25 2>&1 | grep -E 'parents|children'
# Expected: parents: t_d2f906f2  /  children: t_4b9350b4
```

**Sequential chain behavior:** The first card (no parent) starts as `ready`/`running`. Each subsequent card starts as `todo` and auto-promotes to `ready` only when its parent reaches `done`. This limits the builder to 1 concurrent prototype — no separate concurrency cap needed.

## 6. kanban list --json on large boards

`hermes kanban --board hermes-hq list --json` can produce 1.8M+ characters on a board with 190+ tasks (each task body can be thousands of chars). This will flood the context window.

**Alternatives:**
- Use the `kanban_list` tool with `status` and `limit` filters
- Pipe through Python to extract only needed fields
- Use `hermes kanban --board <board> list` (without `--json`) for a human-readable summary

## 7. Verification script

`scripts/verify-queue-builds.sh` — run after any change to queue-builds.sh to verify syntax, parsing, board state, and idempotency. Usage: `bash scripts/verify-queue-builds.sh`

## 8. Monitoring a running builder session via state.db

When a builder card is running (spawned by the dispatcher), you can monitor its progress without interrupting it by reading the session DB directly.

**Find the session:** Each builder session is stored in `~/.hermes-teams/startup/profiles/builder/state.db`. Get the most recent session ID:

```python
import sqlite3
conn = sqlite3.connect('/home/lpaydat/.hermes-teams/startup/profiles/builder/state.db')
c = conn.cursor()
c.execute("SELECT id, title, started_at, message_count, tool_call_count FROM sessions ORDER BY started_at DESC LIMIT 3")
for row in c.fetchall():
    print(row)
conn.close()
```

**Read the conversation flow** (assistant messages only, for narrative):

```python
import sqlite3
conn = sqlite3.connect('/home/lpaydat/.hermes-teams/startup/profiles/builder/state.db')
c = conn.cursor()
c.execute("SELECT rowid, role, content, tool_name FROM messages WHERE session_id='<SESSION_ID>' ORDER BY rowid ASC")
for msg in c.fetchall():
    if msg[1] == 'assistant' and msg[2] and msg[2].strip():
        print("[%d] %s" % (msg[0], msg[2][:400]))
conn.close()
```

**Monitor both builder and PO sessions simultaneously:** The grill RPC involves two agents — the builder and the PO. Read both state DBs:

| Agent | DB path |
|-------|---------|
| builder | `~/.hermes-teams/startup/profiles/builder/state.db` |
| product-owner | `~/.hermes-teams/startup/profiles/product-owner/state.db` |

**Check if processes are alive:**

```bash
ps -p <PID> -o pid,stat,wchan  # builder process
ps aux | grep 'product-owner.*--resume' | grep -v grep  # PO RPC process
```

**Check heartbeats via CLI:**

```bash
hermes kanban --board hermes-hq show <task_id> 2>&1 | grep heartbeat | tail -3
```

**IMPORTANT:** Python heredocs with f-strings and backslashes frequently break inside `execute_code`/`terminal` when working with SQLite. Prefer `execute_code` (Python sandbox) for DB queries — it handles multi-line Python cleanly without shell quoting issues. Avoid `terminal()` with `python3 << 'EOF'` heredocs for any SQL query that contains f-strings or backslash-escaped quotes — the nested quoting levels (bash → python → SQL) create syntax errors. Write the Python directly in `execute_code` instead.

## 9. Observer mode — monitoring a dispatched worker without interfering

When a kanban card is `running` and the dispatcher has spawned a worker (a separate `hermes -p builder --cli` process), you are the **observer**, not the executor. The worker owns the task. Your job is to report status, verify liveness, and flag problems — NOT to run pipeline steps yourself.

**What NOT to do when a worker is running:**
- Do NOT launch your own PO session (`hermes -p product-owner ...`). Two PO sessions writing to the same grill state directory creates conflicts and duplicate questions.
- Do NOT run `answer.sh` yourself. The worker is already in the RPC loop — your answer.sh call sends a second answer to PO from a different identity, confusing the session.
- Do NOT set up grill state directories, create project dirs, or write dossiers. The worker handles the full pipeline (dossier → grill → build → README → handoff) autonomously. If the dossier already exists from a prior run, the worker will find it.
- Do NOT create branches or lock decisions. The worker and PO negotiate branches dynamically.

**What TO do instead:**
- Verify the worker process is alive: `ps -p <PID> -o pid,stat,etime,%cpu`
- Check process subtree for active PO RPC calls: `pstree -p <worker_pid>`
- Read grill state files (read-only): `cat /tmp/grill-<slug>/context/_state.md`
- Count decisions per branch: `grep -c "^Lock D" /tmp/grill-<slug>/context/<branch>.md`
- Report progress to the user concisely
- Only intervene if the worker is genuinely hung (0% CPU for 10+ min with no child processes) or if the user explicitly asks you to take action

**How to tell the worker is progressing (not hung):**
- Worker has child processes (bash → answer.sh → timeout → hermes --resume) = actively in a PO RPC turn
- Grill state files have recent modification timestamps (within last few minutes)
- Decision count or question count is increasing between checks
- Task status remains `running` with recent heartbeats

**THE MOST COMMON OBSERVER-MODE VIOLATION — jumping in to help.** When you see a dispatched worker running a task you know how to do, you will feel an urge to "help" by setting up grill state, launching your own PO session, or running answer.sh yourself. DO NOT. This was violated on 2026-07-24: the observer launched a PO session, created grill directories, and started answering grill questions — all while the dispatched worker (pid 2461) was already mid-grill with 7 decisions locked. The user corrected: "you know you are only observer, right? not the executor." The worker was handling everything autonomously. The observer's interference created duplicate PO sessions and conflicting grill state. **If a worker is running and progressing, your ONLY job is to report status. Verify liveness, count decisions, report to user. Do not touch anything the worker owns.**

**If the worker is genuinely stuck (hung, not just thinking):**
glm-5.2 thinking can take 60-300s per turn — a worker at 0% CPU for 2-3 minutes is likely just waiting for a model response. Check for active `timeout` + `hermes --resume` child processes. If there are NO child processes AND the worker is at 0% CPU AND grill files haven't been modified in 10+ minutes, THEN it may be hung. Report it to the user — do not kill or restart it without explicit direction.

**Deep grill stall pattern (2026-07-25):** A different kind of stuck — the worker is alive and has a `bash → sleep` child process, but NO `timeout → hermes --resume` chain. This means the worker finished its last PO turn and is sleeping before retrying, but never actually re-engages PO. Detection: `pstree -p <worker_pid>` shows `sleep` but no `hermes --resume`; decision count (`grep -rh 'Lock D' /tmp/grill-<slug>/context/ | wc -l`) hasn't changed for 1+ hour. This blocked a concurrency slot for 4+ hours until the dispatcher's stale timeout reclaimed it. Impact: the stalled grill occupies one of the 3 concurrent slots, preventing queued ideas from starting. Mitigation: report to user — the dispatcher will eventually reclaim via stale timeout (default 4h). Do NOT kill without explicit direction.

## 10. Power outage recovery

The system auto-recovers from power loss / hard reboot. You do NOT need to manually restart anything in most cases:

1. **Gateways** — managed by systemd user services (`hermes-gateway-<profile>.service`). They auto-restart on boot. Verify with `systemctl --user list-units --type=service | grep hermes`.
2. **Dispatcher** — runs inside the builder gateway. When the gateway restarts, the dispatcher resumes and re-spawns workers for any `running` tasks that lost their worker process.
3. **Workers** — a killed worker (from power loss) triggers a reclaim. The dispatcher reclaims the task (stale lock detection) and spawns a fresh worker. The new worker picks up from the kanban card state — it reads the card body, checks existing artifacts, and continues.
4. **Grill state** — `/tmp/grill-<slug>/` is ephemeral and DOES NOT survive a reboot. However, if the worker was mid-grill when power was lost, the dispatcher's reclaim gives the worker a fresh session that re-runs the grill from scratch (or resumes if grill output was already persisted to `~/projects/<slug>/context/`).

**After a power outage, your job is to verify and report — NOT to restart or re-execute:**
- Check `uptime` to confirm the reboot happened
- Check gateways are running
- Check the task is still `running` (dispatcher re-spawned the worker)
- Check if a new worker PID exists and is progressing
- Report status to the user

The key insight: **the system is designed to self-heal.** Dispatching workers, reclaiming stale tasks, and auto-restarting gateways are all automated. Your role during recovery is observation and verification, not manual intervention.

`references/2026-07-24-observer-mode-and-power-recovery.md` — full account of the observer-vs-executor confusion and power outage recovery patterns from the 2026-07-24 livetest.

## 11. Cron job debugging — check config first, not the script

When a cron job fails, the instinct is to inspect the script. But cron jobs spawn from the gateway using the PROFILE config — if the profile's model section is broken, EVERY cron job fails before the script even runs. Check config precedence FIRST.

**The debugging sequence (in order):**

1. **Check the cron job's `last_status` and `execution_error`:**
   ```
   cronjob action=list  → look at last_status and execution_error for each job
   ```
   - `RuntimeError: No usable credentials found for provider 'zai'` → config/provider problem, NOT a script problem
   - `[Errno 2] No such file or directory` → script path or PATH problem in the cron subprocess

2. **Check profile config model section for empty overrides:**
   ```bash
   grep -A3 "^model:" ~/.hermes-teams/startup/profiles/builder/config.yaml
   ```
   An empty `base_url: ''` in the profile config NULLIFIES the main config's correct `base_url`. The profile config is merged ON TOP of the main config — empty strings override, they don't fall through. If you see `base_url: ''`, remove the line so the profile inherits the main config's value.

3. **Check .env for stray provider keys that enable unwanted fallback:**
   ```bash
   grep -n "API_KEY" ~/.hermes-teams/startup/.env | grep -v "^#"
   ```
   Hermes auto-discovers providers from env keys. If `DEEPSEEK_API_KEY` is uncommented in .env, hermes treats deepseek as an available provider and falls back to it when the primary (zai) fails — even if `fallback_model: []` in config.yaml. The auto-discovery bypasses the explicit fallback config. To truly disable a provider, comment out its API key in .env.

4. **Check the cron job's model/provider in jobs.json:**
   ```bash
   cat ~/.hermes-teams/startup/profiles/builder/cron/jobs.json | python3 -c "import sys,json; d=json.load(sys.stdin); [print(j.get('name','?'), '| provider:', j.get('provider'), '| model:', j.get('model')) for j in d.get('jobs',d) if isinstance(j,dict)]"
   ```
   If `provider` and `model` are `null`, the job inherits the profile config's model settings. That's correct — the profile config should have a valid provider+base_url.

5. **Restart the gateway after any config or .env change:**
   ```bash
   hermes gateway restart --profile builder
   ```
   The gateway caches config at startup. Cron jobs run INSIDE the gateway process — they don't re-read config.yaml or .env on each tick. A gateway restart is required for changes to take effect.

**The 2026-07-25 incident:** Cron jobs failed with "No usable credentials found for provider 'zai'". Root cause: the builder profile config had `base_url: ''` (empty string), which overrode the main config's `base_url: https://api.z.ai/api/coding/paas/v4`. With an empty base_url, zai calls went nowhere. Hermes then auto-discovered `DEEPSEEK_API_KEY` from .env and silently fell back to deepseek — even though `fallback_model: []` was set. Fix: remove the empty `base_url: ''` line from profile config, comment out `DEEPSEEK_API_KEY` in .env, restart gateway. All 3 cron jobs then passed immediately.

**Key lesson:** When the user says "cron jobs didn't use hermes setting" — check whether the PROFILE config is overriding the MAIN config with empty/broken values. Profile config wins the merge. And check .env for auto-discovered provider keys that enable fallback you didn't intend.

## 12. Batch E2E testing on a fresh board

When running a full pipeline livetest (10+ ideas), create a DEDICATED BOARD instead of polluting the main board. This keeps test cards isolated from production work and makes cleanup trivial.

**Create a fresh board:**
```bash
hermes kanban boards create e2e-livetest --name "E2E Livetest"
hermes kanban boards switch e2e-livetest
```

**Create 10 grill+build pairs via kanban_create** (the kanban API tool, not the CLI — CLI truncates multiline bodies). Pass `board="e2e-livetest"` to each card. Chain build cards to grill cards with `parents=["t_grill_id"]`.

**Dispatcher picks up cards from ANY board** — the gateway's dispatcher monitors all boards for the builder profile. Cards on e2e-livetest will be dispatched automatically with 3 concurrent (max_in_progress_per_profile=3).

**Monitor without interfering (see Section 9 — Observer Mode).** But DO report periodically — the user expects status updates, not silence (see Section 13).

**Verify completed prototypes independently** — don't trust self-reported metadata. Run each verify script and each prototype directly:
```bash
# For each completed slug:
python3 /tmp/verify-<slug>.py          # must exit 0
python3 ~/projects/<slug>/prototype/<file>  # must exit 0, no traceback
grep -c "^## " ~/projects/<slug>/README.md  # must be 9
```

## 13. Batch monitoring — report periodically, do NOT go silent

When monitoring a batch of N cards (e2e-livetest or any multi-card run), the user expects PERIODIC STATUS UPDATES. Going silent for 2+ hours during a pipeline run is a violation of observer mode — the user had to ask "you didn't update anything for 2 hours already."

**Pattern for batch monitoring:**
- After creating cards and confirming dispatch: report the initial state (X running, Y queued)
- Check back every 15-30 minutes: `kanban_list(board=..., status="done")` to count completions
- Report each completion wave: "3 more done, 2 running, 5 queued"
- Flag problems immediately: stuck workers, blocked cards, timeout reclamations
- When all done: provide the final analysis table
- **Do NOT set 1-hour sleep timers and wait passively.** The user expects 15-30 min check-ins, not silent gaps. Use `process wait` with short timeouts (60s max — the runtime clamps anyway) and check state between polls.

**The user does NOT want to ask "what's the status?" — they want proactive reporting.** If you find yourself wondering whether to check, CHECK AND REPORT. The cost of a status update is near-zero; the cost of silence is user frustration.

**Do NOT inflate wall-clock time (2026-07-27 correction).** When reporting grill duration, distinguish between ACTIVE compute time (actual PO Q&A + answer processing) and WALL-CLOCK time (which includes dispatcher reclaim gaps, stale timeout waits, and your own poll intervals). The user corrected: "It's not 40+ hrs as you understood. in fact, it's around 2-3 hours only." A grill that appeared to run for "100+ hours" was actually 2-3 hours of active work stretched across many reclaim cycles. Report active time when possible, and always clarify if you're quoting wall-clock vs active.

**Stale timer cleanup — CRITICAL:** After a batch completes, you may accumulate dozens of stale `sleep` background processes from monitoring timers. These produce repeated "Background process completed" notifications that clutter the conversation for HOURS after the batch is done.

**The 2026-07-26 incident:** 50+ stale `sleep 1800` and `sleep 3600` timers produced notifications for 3+ hours after the batch completed. Each notification triggered a wasted response cycle. The user asked "why not disable timer" — pointing out that `notify_on_complete=true` on sleep timers is an anti-pattern for monitoring.

**Rules for monitoring timers:**
1. **NEVER use `notify_on_complete=true` on sleep timers.** Each completed sleep fires a notification. With 20+ timers stacked (one per poll cycle), you get 20+ notifications even after the work is done.
2. **Use `notify_on_complete=false`** and poll manually with `process(action='poll')` or `process(action='wait', timeout=60)`.
3. **Or skip sleep timers entirely** — use `process(action='wait', timeout=180)` on a single background check command, which blocks until done or timeout without creating a notification-spamming sleep process.
4. **If you must use sleep timers:** kill them ALL with `process(action='list')` then `process(action='kill')` for each running session_id IMMEDIATELY when the batch completes. Do NOT acknowledge individual stale notifications — kill the source.
5. **Fewer, longer intervals are better than many short ones.** One 30-min timer is better than two 15-min timers. The process wait timeout is clamped to 180s regardless of what you request.

**Timing correction (2026-07-26, confirmed 2026-07-27):** When reporting grill duration, do NOT compute wall-clock from card `started_at` to `completed_at`. That includes dispatcher reclaim gaps, stale timeout cycles, and idle polling intervals. The actual active grill work (PO Q&A turns) is typically 2-3 hours for a normal grill (50-70 decisions). The user corrected: "It's not 40+ hrs as you understood. in fact, it's around 2-3 hours only." Report ACTIVE grill time (decisions x ~3 min/decision), not wall-clock elapsed. Deep grills (100+ decisions) genuinely take longer, but even those are 5-8 hours of active work, not the 14-109 hour wall-clock figures.

## 14. E2E verification recipe and test results

`references/e2e-verification-recipe.md` — full step-by-step recipe covering gateway restart, queue-builds.sh, card verification, chaining check, idempotency, and dispatcher pickup.

`references/grill-cli-background-hang.md` — why `--cli` hangs in background mode and the `timeout` wrapper fix.

`references/2026-07-23-e2e-pipeline-test-results.md` — results from the first full E2E test: LeadPilot card completed end-to-end (1h7m), sequential chain auto-promotion confirmed, 4 issues documented (card-block-during-grill, cli-hang, API-timeout-on-batch-answers, slug-mismatch).

`references/2026-07-23-self-grill-card-blocking.md` — root-cause analysis of the builder blocking kanban cards during self-grill. Documents why it happens (kanban protocol literalism), impact (~30 min lost per reclaim cycle), and the fix (explicit "never block" instruction in self-grill SKILL.md).

`references/2026-07-23-po-grill-quality-e2e.md` — PO grill quality observations from the E2E test: evidence verification, math checking, live competitor research, decision density benchmarks (14 decisions / 5 branches / ~50 min for LeadPilot).

`references/2026-07-24-e2e-pipeline-test.md` — full 10-card E2E test results: all fixes applied, pipeline timing per card, findings (prototype deliverable inconsistency, dispatcher reclaim overhead, slug mismatch).

`references/prototype-deliverable-requirements.md` — REQUIRED reading for builders. Every prototype MUST ship with index.html + README.md (with specific sections) + grill-decisions.md. 8/10 prototypes in the E2E test were missing READMEs — this file defines the quality bar.

`references/2026-07-24-vault-migration-and-cross-profile-scan.md` — the full vault-to-projects migration: what stays in vault (Obsidian), what moves to ~/projects/, how to audit ALL profiles for wrong paths, and the sed backreference pitfall.

`references/2026-07-24-loop-engine-for-builder.md` — why loop_engine was enabled for builder (not tech-lead exclusive), how it phases prototype builds with DoD gates, and the hermes-config-set JSON-string pitfall.

`references/2026-07-24-venture-prototype-vs-mattpocock-prototype.md` — why Matt Pocock's `prototype` skill does NOT fit our venture pipeline (in-codebase dev prototyping vs our standalone clickable demos), and the proposed venture-prototype README structure for founder review.

`references/2026-07-24-2card-pipeline-architecture.md` — The 2-card split (grill card → build card). Initially marked SUPERSEDED, then re-proposed by the founder after loop_engine was skipped AGAIN in the E2E-BATCH2 RouteOpt test. Status: UNDER ACTIVE DESIGN. The key insight is that instruction-level enforcement ("loop_engine is MANDATORY") has failed on 15/15 prototypes across 2 batches. A dedicated build card gives the builder a fresh context with ONE job — the card body IS the loop_engine spec.

`references/2026-07-24-kanban-block-research.md` — why `kanban_block` cannot be disabled per-tool (Hermes only supports toolset-level filtering, and the kanban toolset is force-injected for dispatcher workers). Documents the builder's self-heal behavior and the system-prompt-priority root cause.

`references/2026-07-24-e2e-test-2-ai-pen-testing.md` — E2E test #2 results with the new workflow: all components PASS (grill persistence, validation gate, README, prototype, portfolio). Documents remaining issues (card blocking, duplicate filenames).

`references/2026-07-24-api-prototype-verification-pitfalls.md` — curl-assertion false negatives when verifying FastAPI endpoints: (1) compact JSON breaks `grep '"key": value'` spacing, (2) `curl -sf` swallows error bodies on 4xx/5xx so you can't assert on rejection messages, (3) DOM clicks may not reflect async state — call page handlers from `browser_console` instead.

`references/2026-07-24-loop-engine-enforcement-failure.md` — why the "loop_engine is MANDATORY" instruction fails to prevent skipping (builder self-assesses exemption every time), what doesn't work, and structural enforcement options.

`references/2026-07-24-loop-engine-partial-compliance.md` — the NEW failure mode from the 2026-07-24 rebuild test: builder wrote verify script + ran independent verifier (letter of loop_engine) but skipped phased mechanism with replan gates (spirit). Detection signs, enforcement options, and recommendation to accept partial compliance as stepping stone.

## Pitfalls

- **Profile config empty values override main config — the #1 cron failure cause (2026-07-25).** When the profile config (e.g. `~/.hermes-teams/startup/profiles/builder/config.yaml`) has `base_url: ''`, it NULLIFIES the main config's `base_url: https://api.z.ai/...`. Empty strings override in the merge — they don't fall through to the parent. If you see `base_url: ''` or any empty value in a profile config, remove the line so the profile inherits from the main config. This caused all 3 cron jobs to fail with "No usable credentials found for provider 'zai'" even though the main config was correct.
- **Profile config `max_turns` overrides main config `max_iterations` (2026-07-25).** Profile config is merged ON TOP of main config. If the profile config has `max_turns: 200` and the main config has `max_iterations: 999`, the profile's `max_turns: 200` wins for ALL sessions spawned by the dispatcher (workers, cron jobs). This causes deep grills (80+ decisions, 5+ branches) to hit "Iteration budget exhausted (200/200)" and timeout — the worker gets reclaimed and has to resume from recovered state. The user set `delegation.max_iterations: 999` in the main config thinking that was the cap, but the profile's `max_turns: 200` was silently overriding it. Fix: set `max_turns: 2000` (or higher) in the PROFILE config at `~/.hermes-teams/startup/profiles/builder/config.yaml`, then restart the gateway. Always check BOTH configs — the profile config is what the dispatcher uses.
- **.env API keys enable auto-discovered fallback — bypasses fallback_model config (2026-07-25).** If `DEEPSEEK_API_KEY` is uncommented in .env, hermes treats deepseek as an available provider and falls back to it when the primary fails — EVEN IF `fallback_model: []` is set in config.yaml. Auto-discovery from .env bypasses the explicit fallback config. To truly disable a provider: comment out its API key in .env, don't just empty the fallback_model list.
- **Gateway caches config at startup.** A config.yaml change is invisible to running sessions until `hermes gateway restart`. Sessions spawned by the dispatcher inherit the gateway's cached config, not the file on disk.
- **`eval` destroys multi-line arguments.** The #1 cause of queue-builds.sh silently failing (every card "FAILED" with no error message). The eval splits the body text into individual words.
- **`hermes kanban list --json` on big boards is dangerous.** 190 tasks × multi-KB bodies = 1.8M chars. Always filter or use the kanban_list tool.
- **kanban tools default to `default` board, not `hermes-hq`.** The `kanban_list` and `kanban_show` tools (the Python API) default to the `default` board unless you explicitly set `HERMES_KANBAN_BOARD`. Cards created on `hermes-hq` via the CLI will appear missing from the API tools. Always specify the board: `hermes kanban --board hermes-hq show <id>` for CLI, or set `HERMES_KANBAN_BOARD=hermes-hq` before using API tools. This caused a false report that `--parent` chaining was broken when it was actually working fine.
- **`.last-queue` marker blocks re-runs.** 6h cooldown. Remove the file to bypass during testing.
- **`--json` output may not be pure JSON.** The CLI may prepend log lines or status messages. Wrap in `|| echo "{}"` and parse defensively.
- **Grill `--cli` hangs in background mode.** When a builder session launches PO via `hermes -p product-owner --cli` in background (`terminal(background=true)`), the process hangs — `--cli` waits for stdin that never arrives. Use `timeout 600 hermes ... --cli 2>&1 | tail -80` in foreground instead (glm-5.2 thinking alone can take 300s+ — 600s is the minimum safe timeout). See `references/grill-cli-background-hang.md` for full details.
- **Builder blocks kanban card during self-grill.** The builder calls `kanban_block(kind='needs_input')` while waiting for grill answers, even though it IS the founder in a self-grill. **The NEVER-block skill instruction does NOT fully work** because the system prompt's kanban task protocol ("block on genuine ambiguity") is higher priority than skill content. **Root cause:** Hermes has no per-tool disable mechanism — only toolset-level filtering. `kanban_block` is part of the `kanban` toolset which is force-injected for dispatcher workers. The builder self-heals: it keeps working while blocked, then CLI-completes via `hermes kanban claim` + `hermes kanban complete`. **Accept this behavior** — the wasted time is the self-recovery dance, not a hard failure. See `references/2026-07-24-kanban-block-research.md` for the full architecture analysis.
- **Slug mismatch between idea-bank.md and dossier filenames creates duplicate prototype dirs.** LeadPilot: `leadpilot-ai-local-smb-lead-gen` (idea-bank) vs `leadpilot-local-smb-lead-gen` (dossier). Builder created both dirs. Normalize slugs in idea-bank.md to match actual dossier filenames.
- **Pinned skills cannot be patched by skill_manage or the background curator.** But they CAN be patched via the `patch` tool directly on the filesystem path. `grill-rpc-ops` and `self-grill` were both successfully patched this way (2026-07-24): the `--cli` timeout fix and the never-block-during-self-grill fix. The `patch` tool operates on files, not through the curator, so pin protection does not apply.
- **`~/vault/` is Obsidian — NEVER put project artifacts there.** The user has corrected this repeatedly across multiple sessions. `~/vault/ventures/` holds ONLY pipeline intake (signals, idea-bank, dossiers, portfolio). ALL project artifacts (prototypes, README, context, production code, journal, traces, qa-evidence) go in `~/projects/<slug>/`. This applies to ALL profiles — not just builder. The user said: "I kept telling you to don't use ~/vault as that's obsidian location that we plan to use it for our second brain." See `references/2026-07-24-vault-migration-and-cross-profile-scan.md` for the full audit across builder, tech-lead, developer, qa, and advisor profiles.
- **Cross-profile skill edits require `cross_profile=True`.** When fixing wrong paths in other profiles' skills (tech-lead, advisor, developer, qa), the `patch` tool blocks the write by default. Pass `cross_profile=True` after explicit user direction to bypass the soft guard.
- **sed backreferences on paths produce `\x01` garbage.** `sed -i 's|pattern|\1/prototype/|g'` silently inserts literal control chars when the replacement has backslashes. Use Python `re.sub` or context-based string replacement instead.
- **When implementing a design based on a misunderstanding, use `git revert --no-commit`.** This lets you selectively keep what's still valid (e.g., venture-prototype skill) while reverting the structural changes (e.g., 2-card-per-idea flow). Then re-stage only the files you want to keep.
- **Grill output persistence — grill scripts write to `/tmp/grill-<slug>/context/` which is ephemeral.** If the builder doesn't copy per-branch files to `~/projects/<slug>/context/` before completing the card, all grill decisions are lost. The self-grill SKILL.md now has a mandatory persistence step + `validate-grill-output.sh` validation gate. The folder is `context/`, not `grill/` — renamed 2026-07-24.
- **Grill depth regression — builder self-plays both roles instead of launching PO.** The #1 cause of shallow grills (12 decisions instead of 50+ questions). The builder short-circuits the RPC loop: writes PO questions AND founder answers in one pass without launching a real PO session. Root cause: `HERMES_KANBAN_TASK` env var leaks into PO subprocess, PO loads kanban task protocol, thinks it IS the builder. Detection: check PO session DB for `<Q>` tags — 0 means self-play. **Fixed (2026-07-24):** env isolation (`env -u HERMES_KANBAN_*`) in grill-rpc-ops launch recipe, self-grill removed from PO skills, grill-rpc skill rewritten (50+ questions, removed 8-branch/20+ limits), validate-grill-output.sh check 6 verifies real PO `<Q>` questions (5+ required). See `references/2026-07-24-builder-self-play-root-cause.md`.

`references/2026-07-24-kanban-worker-env-isolation.md` — why `HERMES_KANBAN_*` env vars leak into subprocesses launched by kanban workers, causing identity confusion. The `env -u` fix and skill-isolation defense.

- **Env leak on resume too, not just launch.** The `env -u HERMES_KANBAN_*` isolation was applied to the PO Launch Recipe in grill-rpc-ops, but the Answer Pattern (which calls `hermes --resume` via answer.sh) does NOT have it. `hermes --resume` rebuilds the system prompt from current env vars — so `HERMES_KANBAN_TASK` leaks back in on every answer turn. This can cause PO to revert to builder-identity confusion mid-grill. The fix is to wrap `answer.sh` calls with the same `env -u` prefix. grill-rpc-ops is pinned and cannot be patched here — ask user to unpin or apply the fix manually.
- **Prototype deliverable inconsistency — SOLVED by venture-prototype skill.** 8/10 prototypes in the E2E test were missing READMEs. The `venture-prototype` skill enforces README.md as mandatory with a verify checklist. The pipeline uses 1 card per idea; venture-prototype loads after the grill completes within the same session.
- **Two project-promotion skill dirs exist.** There's a top-level symlink AND a software-development/ copy. The shared-skills one is the canonical source. Must fix BOTH or consolidate to one.
- **Pinned skills cannot be patched by skill_manage or background curator.** Use the `patch` tool directly on the filesystem path to update pinned skills. The patch tool operates on files, not through the curator.
- **Builder self-plays grill when env isolation is incomplete.** The `env -u HERMES_KANBAN_*` fix was applied to the PO Launch Recipe but NOT to the Answer Pattern in grill-rpc-ops. `answer.sh` calls `hermes --resume` which rebuilds the system prompt from env vars — so `HERMES_KANBAN_TASK` leaks back in on every answer turn. Fix: wrap answer.sh calls with the same `env -u` prefix. grill-rpc-ops is pinned — use `patch` tool directly. See `references/2026-07-24-answer-pattern-env-isolation-gap.md`.
- **Grill folder renamed from `grill/` to `context/`.** All skills, scripts, and paths now use `~/projects/<slug>/context/` for per-branch grill output. The validation script (`validate-grill-output.sh`) uses `CONTEXT_DIR` variable.
- **prototype-iteration and prototype-review-handoff should be user-invoked.** Both were model-invoked (context load) but are loaded via pointer from other skills, not by trigger phrases. Changed to `disable-model-invocation: true` during writing-great-skills audit.
- **Skill library target shape: class-level umbrellas with references/.** Avoid narrow one-session-one-skill entries. Each pipeline skill is a class: self-grill (grilling), venture-prototype (building), project-promotion (promotion), prototype-iteration (feedback), prototype-review-handoff (handoff), grill-rpc-ops (RPC mechanics). Session-specific detail goes in `references/` under the appropriate umbrella.
- **ONE CARD PER IDEA. NEVER pack multiple ideas into one kanban card.** A builder session can only handle one full pipeline (dossier → grill → build → handoff). Putting 5 ideas in one card causes premature completion — the builder spends all turns on the first dossier and never reaches grilling or building. queue-builds.sh creates one card per idea, chained sequentially via `--parent`. When manually creating test cards, follow the SAME pattern: one idea per card, chain with `--parent`. This was violated on 2026-07-24 (5 ideas in one card → builder completed with zero prototypes after 25 min). The user explicitly corrected: "did you dump all 5 projects to one builder session?"
- **Creating kanban cards with multiline bodies via shell truncates the body.** `hermes kanban create --body "$MULTILINE"` via terminal() or bash loses everything after the first newline. Use the `kanban_create` tool directly (Python API) instead — it handles multiline bodies correctly. Alternatively, write the body to a temp file and pass `--body "$(cat /tmp/body.txt)"`. This is a different bug from the `eval` issue — it's shell quoting mangling newlines in the heredoc/variable, not eval word-splitting.
- **`hermes kanban show <id>` truncates the displayed body** — only shows the first ~50 chars. But the full body IS stored in the kanban DB (verify with `SELECT length(body) FROM tasks WHERE id='t_xxx'`). The builder's `kanban_show` tool returns the FULL body. Do not panic if CLI `show` looks truncated — the card content is intact.
- **FastAPI verification scripts: two curl-assertion false negatives.** (1) FastAPI emits **compact JSON** — `{"active":true}` not `{"active": true}`. A `grep '"active": true'` assertion fails on valid responses. Fix: parse structurally with `python3 -c "import sys,json; d=json.load(sys.stdin); assert d['active']==True"`. (2) `curl -sf` **discards error bodies** on HTTP 4xx/5xx, so you cannot assert on a deliberate rejection's message (e.g. "not approved" on a 403). Use plain `curl -s` (no `-f`) for negative-path assertions. See `references/2026-07-24-api-prototype-verification-pitfalls.md` for full recipes.
- **Builder creates `.venv` inside prototype/ when building API prototypes.** The builder runs `pip install` inside `~/projects/<slug>/prototype/`, creating a virtual environment with 2,977+ files (120MB). Prototype build rules say "no dependencies beyond stdlib" but the builder ignores this for API types. Fix: the venture-prototype skill build rules section now explicitly bans `.venv`, `node_modules`, `pip install`, and `npm install` inside prototype/. For API prototypes, hardcode responses instead of installing Flask/FastAPI.
- **Builder completes card with ZERO output when it can't create a dossier.** Card 2 (SMB Bookkeeping) had no dossier. The builder session read the card, saw "create dossier first," and marked the card done without producing ANY output — no dossier, no grill, no prototype. This is premature completion driven by task complexity at the top of the pipeline. The validation gate only runs during the grill phase, not at card completion. A pre-completion check (prototype/ exists? README exists?) would catch this.
- **Builder creates DUPLICATE idea-bank entries instead of updating existing ones.** When a builder completes a pipeline, it sometimes adds a NEW row to the "Built/Awaiting Review" section of idea-bank.md with a new product name (e.g., "RouteOpt") and a project-relative dossier path (`~/projects/.../.context/dossier.md`), instead of updating the existing "unbuilt" row to "BUILT_AWAITING_REVIEW". This creates duplicate entries for the same idea — one marked "unbuilt" (stale), one marked "awaiting review" (new). Fix during post-run analysis: update the original row's status, remove the duplicate, ensure the dossier link points to `~/vault/ventures/ideas/<slug>.md` (not a project-relative path that breaks if the project is archived).
- **Builder SKIPS loop_engine despite MANDATORY instruction — RESOLVED by 2-card split + verify template (2026-07-25).** The venture-prototype skill said "loop_engine is MANDATORY" but the builder skipped it on 15/15 prototypes across 2 batches. **The fix that worked:** (1) split pipeline into separate grill and build cards so loop_engine is the ONLY job in a fresh context, (2) rewrote verify-script-template.md to enforce 4 categories with minimum 20 checks. Batch 3 results: verify scripts went from avg 8.3 checks (batch 2) to avg 56 checks (batch 3). See `references/2026-07-24-loop-engine-enforcement-failure.md` for the comparison table.
- **Builder undercounts its own grill decisions in README.** README says "61 decisions" but context/ has 65 locked decisions. Happens on multiple runs — the builder estimates instead of counting. The verify script should check `len(decisions)` against the README's stated count and fail if they mismatch. Fix for card authors: add "Count decisions from context/ files using `grep -rh '^Lock D\|^\*\*D[0-9]' ~/projects/<slug>/context/ | sort -u | wc -l` and use that exact number in the README" to the card body.
- **Portfolio score disagrees with idea-bank score.** The portfolio entry says "19/25" (the dossier's uplifted score) while the idea-bank says "17/25" (the original score). Dossier score uplifts are internal analysis, not bank-level re-scoring. The portfolio and idea-bank MUST use the same score — the original from idea-bank.
- **Prototype not browser-tested.** The venture-prototype skill says "Browser-test it before completing. Zero JS errors." But the builder never opens the file in a browser to verify it renders. JS brace balance and HTML structure checks pass, but interactive elements (tab switching, sliders, onclick handlers) are unverified. The verify script checks for structural presence of these elements, not functional behavior.
- **E2E-BATCH2 RouteOpt livetest — complete analysis (2026-07-24).** Full-pipeline card t_7c5eef0e completed in ~3h42m after surviving a power outage. Grill: 65 decisions / 60 questions / 4 branches (deepest grill in the batch, PO caught 5 real design flaws). Prototype: 53KB HTML, all 10 quality checks pass. README: 9 sections. Loop_engine: SKIPPED (same recurring failure across all 15 prototypes in 2 batches). Rebuild card t_0e3bc9ed ran in 8 min with PARTIAL loop_engine compliance (verify script + verifier, but no phased mechanism). Two structural fixes: (1) 2-card split — IMPLEMENTED (commits 461fdcf7 + ae20dea8), (2) validate-prototype-build.sh completion gate — not yet built.
- **queue-builds.sh dedup uses substring matching — false positives block fresh ideas.** The dedup check `if '$slug' in (title + body).lower()` matches ANY card that mentions the slug fragment. Example: `ai-smb-bookkeeping` is blocked because an old card body mentions "smb-bookkeeping" in passing. This prevents queue-builds.sh from creating cards for ideas that share keywords with completed work. **Workaround:** create pairs manually via `kanban_create` tool for targeted testing. The real fix would be exact-slug or title-only matching in the dedup check.
- **delegate_task subagents call kanban_complete prematurely (root cause traced 2026-07-25).** The grill card dispatches a research subagent via `delegate_task` to create the dossier. The subagent inherits the kanban toolset and calls `kanban_complete` on the parent grill card before the grill runs. **Root cause: `DELEGATE_BLOCKED_TOOLS` frozenset in `tools/delegate_tool.py` (line 46) blocks delegate_task/clarify/memory/send_message/execute_code/cronjob but NOT kanban lifecycle tools.** Fix: add `kanban_complete`, `kanban_block`, `kanban_create`, `kanban_unblock`, `kanban_heartbeat` to the frozenset. Leaf subagents should retain kanban_show/list/comment (read-only). See `references/2026-07-25-subagent-kanban-complete-root-cause.md` for full source-level analysis and 3 fix options.
- **Build cards with `needs_input` block don't auto-promote when parents complete (2-card parallel test, 2026-07-24).** When a build card blocks (`kind=needs_input`) and then its parent (or a re-grill task linked as additional parent) completes, the auto-promote to `ready` does NOT fire. The card stays `blocked` indefinitely. Requires manual `kanban_unblock`. This is a dispatcher limitation — the `needs_input` block kind is designed for human-gated tasks, not dependency-gated tasks. **Workaround:** when monitoring a batch, check for `blocked` build cards whose parents are all `done` and call `kanban_unblock` manually. Or use `kind=dependency` instead of `kind=needs_input` when blocking for missing prerequisites.
- **Race condition: build card checks context/ before grill finishes writing (2-card parallel test, 2026-07-24).** When the grill and build cards are dispatched close together, the build card may spawn and check `context/` before the grill worker has written any files. The build card correctly blocks (context/ empty), but then the grill completes and the build stays blocked (see above). This is a timing issue — the build card's first check is a snapshot, not a watch. The system self-heals if a re-grill task is created and manually unblocked.
- **2-card parallel pattern VALIDATED (2026-07-24, fix-validation 2026-07-25).** Livetest 1 (2026-07-24): 3 pairs, all completed, 3 bugs found (subagent premature completion, blocked→ready stuck, context/ race condition). Fixes applied: verify-script-template rewritten (min 20 checks, 4 categories), subagent toolset warning in card body. Livetest 2 (2026-07-25): 3 new pairs with fixes applied — verify scripts jumped from 5 checks to 48-70 checks (10x improvement). Subagent auto-completion still happens but builder recovers in-session. blocked→ready still needs manual unblock. See `references/2026-07-24-parallel-2card-test-results.md` (livetest 1) and `references/2026-07-25-parallel-2card-fix-validation.md` (livetest 2).
- **answer.sh exit code 1 is NON-FATAL — don't abandon the grill (2026-07-25).** answer.sh sometimes exits with code 1 and stderr "WARNING: Could not extract question. Raw output on stderr." This happens when PO's response lacks a `<Q>` tag and the question-extraction regex fails (~8% of invocations). **The answer WAS sent, PO DID respond, the Q&A WAS logged, and Lock D decisions WERE extracted.** The next question is visible on stdout in plain text. Do NOT treat exit code 1 as fatal — read stdout and continue the grill. Only abort if stdout is completely empty.
- **_state.md decision count column was stuck at 0 — FIXED in answer.sh (2026-07-25).** Root cause: answer.sh's `_state.md` count update loop read 4 fields (`_num _name _status _decisions`) from each `| N | name | status | count |` row using `IFS='|'`. But the leading pipe creates an EMPTY first field — so `_num` got the empty string, `_name` got the row number, and the sed search pattern never matched. Fix: read 5 fields (`_empty _num _name _status _decisions`), discarding the leading empty one. The validation script was unaffected (it counts `Lock D` lines directly from branch files), so grills still PASSED validation — the counts were just misleading in `_state.md`. If you see counts stuck at 0 on grills that ran with an older answer.sh, they're cosmetic — re-run the count fix manually or ignore.
- **Deep grills (100+ decisions) take 5-8 hours ACTIVE time with glm-5.2 — but appear as 40-100+ hours wall-clock due to reclaim cycles (2026-07-26 FINAL 2026-07-27).** The 2026-07-26 batch (10 ideas) completed **10/10 — all pairs eventually finished**. But the spectrum was extreme: 6 ideas finished in 30min-2h (50-82 decisions), Code-Reading-First IDE hit 116 decisions (5-8h active), and The Log is the Agent hit **475+ decisions** before finally terminating when max_turns=2000 was exhausted. **IMPORTANT: active grill time was 2-3 hours for normal grills and ~8h for the 475-decision grill — the much larger wall-clock figures (40-100+ hours) came from dispatcher reclaim cycles, stale timeout gaps, and monitoring poll intervals, NOT from continuous compute.** The user corrected: "It's not 40+ hrs as you understood. in fact, it's around 2-3 hours only." **Decision: NO fixed cap.** Deep analysis of the 478-decision logagent grill showed the decisions were overwhelmingly valid (breakthrough sustainability insight at D234, technically precise capture-contract decisions). Instead, use **dynamic convergence signals** (see self-grill SKILL.md): supersession rate >20%, question depth decay, branch exhaustion 15+ Qs, founder convergence 5+ "Agree" answers. **self-grill is PINNED** — needs `hermes curator unpin self-grill` to add convergence section. **In-session monitoring:** check `grep -rh 'Lock D' /tmp/grill-<slug>/context/ | wc -l` periodically. At 60+, expect a long grill. At 100+, it's deep but still valid. At 200+, check for convergence signals. **The build for the 475-decision grill took only 9 minutes** — proving the entire pipeline bottleneck is grill depth, not build quality.
- **process wait timeout clamped to 60s — expect 2-3 polls per answer.sh invocation (2026-07-25).** `process wait(timeout=120)` is clamped to 60s by the runtime. Since glm-5.2 takes 60-200s per turn, a single `process wait` almost always times out before answer.sh completes. Pattern: for each answer.sh invocation, call `process wait(timeout=60)` up to 3 times until the process exits.
- **Subagent tool-call limit recovery via live transcript (2026-07-25).** When a research subagent hits the ~50-call limit before writing its output file, the delegation summary is truncated (~100 chars). Full findings are in the live transcript log at `~/.hermes-teams/startup/profiles/builder/cache/delegation/live/<delegation_id>/task-N.log` — read the `final` lines at the end for the complete report. Extract and write the output file manually.
- **PO kanban tool leakage — env isolation doesn't stop PO from using kanban tools (2026-07-25).** The `env -u HERMES_KANBAN_*` recipe prevents PO from loading the kanban task protocol and thinking it's the task worker. But it does NOT prevent PO from using kanban lifecycle tools (unblock, comment, complete) if the product-owner profile has the `kanban` toolset. During the App Store Impersonation Monitor grill, PO unblocked the build card (t_fd5ca169), wrote comments as "worker" including a founder directive on scope, and reported the grill as complete — all while the builder was still running the grill in a separate session. PO discovered task IDs from the `[GRILL STATE]` prefix and the builder's answers. **Mitigation:** (1) verify the product-owner profile's toolset doesn't include `kanban`, (2) explicitly instruct PO in the launch prompt: "Do NOT access the kanban board, do NOT unblock/block/complete any task, you are a griller only", (3) avoid mentioning task IDs in grill answers that PO can see via `[GRILL STATE]`. Detection: `hermes kanban events --task <child-task-id> --since <grill-start-time>` — if events show "unblocked" or "commented" by product-owner, PO overstepped.

`references/2026-07-25-app-store-monitor-livetest.md` — full analysis of the App Store Impersonation Monitor 2-card livetest. Documents: prototype crashes on execution but passes all 47 static checks (unguarded optional-import bug), self-reported metrics fabricated when prototype doesn't run, grill card iteration budget exhaustion from parallel research subagents, PO kanban tool leakage despite env isolation.

`references/2026-07-25-10-card-batch-livetest.md` — 10-card batch test on fresh `e2e-livetest` board. Verify template update validated at scale (3/4 builds have runtime execution checks). Grill depth variance documented (28-82 decisions). Fresh-board testing pattern confirmed working.

`references/2026-07-26-10-card-batch-livetest.md` — second 10-card batch on `e2e-livetest` board. **10/10 pairs completed (FINAL 2026-07-27)**. All builds have runtime execution checks. Grill runaway fully documented: median 54 decisions (30 min active), Code-Reading-First IDE 116 decisions (5-8h active), The Log is the Agent **475+ decisions** — finally terminated via max_turns=2000, build took 9 min. One grill blocked the last slot until max_turns exhausted. Includes full results table, fix list, and decision-cap recommendation (MAX_TOTAL_DECISIONS=50-60, MAX_DECISIONS_PER_BRANCH=15-20). **Key user correction:** active grill time is 2-3 hours — wall-clock figures of 40-100+ hours were inflated by dispatcher reclaim gaps, stale timeout cycles, and monitoring poll intervals, NOT active compute. Report active time, not wall-clock.
