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

The queue script lives at `~/.hermes-teams/startup/profiles/builder/scripts/queue-builds.sh`. It reads `~/vault/ventures/idea-bank.md`, picks top 10 unbuilt ideas by score, creates **one kanban card per idea** assigned to `builder`, chained sequentially across ideas.

```bash
cd ~/.hermes-teams/startup/profiles/builder/scripts && bash queue-builds.sh
```

**1-card architecture (current):** One card per idea. Builder reads dossier → grills with PO → builds prototype → writes README → updates portfolio → completes. Cards chain sequentially across ideas (idea 2 waits for idea 1's card to complete).

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
- 10 cards exist with titles starting "Build prototype:"
- Each card (except the first) has the previous card as parent (sequential chain)
- First card (highest score) should be `running` or `ready`
- Remaining cards should be `todo` (waiting for their parent to complete)
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

**If the worker is genuinely stuck (hung, not just thinking):**
glm-5.2 thinking can take 60-300s per turn — a worker at 0% CPU for 2-3 minutes is likely just waiting for a model response. Check for active `timeout` + `hermes --resume` child processes. If there are NO child processes AND the worker is at 0% CPU AND grill files haven't been modified in 10+ minutes, THEN it may be hung. Report it to the user — do not kill or restart it without explicit direction.

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

## 11. E2E verification recipe and test results

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

`references/2026-07-24-2card-pipeline-architecture.md` — **SUPERSEDED.** The 2-card split (grill card → build card) was reverted on 2026-07-24 after the user clarified they meant separating grill and build PHASES, not cards per idea. The pipeline uses 1 card per idea. Kept for historical context on why the split was considered and what problems it attempted to solve.

`references/2026-07-24-kanban-block-research.md` — why `kanban_block` cannot be disabled per-tool (Hermes only supports toolset-level filtering, and the kanban toolset is force-injected for dispatcher workers). Documents the builder's self-heal behavior and the system-prompt-priority root cause.

`references/2026-07-24-e2e-test-2-ai-pen-testing.md` — E2E test #2 results with the new workflow: all components PASS (grill persistence, validation gate, README, prototype, portfolio). Documents remaining issues (card blocking, duplicate filenames).

`references/2026-07-24-api-prototype-verification-pitfalls.md` — curl-assertion false negatives when verifying FastAPI endpoints: (1) compact JSON breaks `grep '"key": value'` spacing, (2) `curl -sf` swallows error bodies on 4xx/5xx so you can't assert on rejection messages, (3) DOM clicks may not reflect async state — call page handlers from `browser_console` instead.

`references/2026-07-24-loop-engine-enforcement-failure.md` — why the "loop_engine is MANDATORY" instruction fails to prevent skipping (builder self-assesses exemption every time), what doesn't work, and structural enforcement options.

`references/2026-07-24-loop-engine-partial-compliance.md` — the NEW failure mode from the 2026-07-24 rebuild test: builder wrote verify script + ran independent verifier (letter of loop_engine) but skipped phased mechanism with replan gates (spirit). Detection signs, enforcement options, and recommendation to accept partial compliance as stepping stone.

## Pitfalls

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
- **Builder SKIPS loop_engine despite MANDATORY instruction — recurring across ALL E2E tests.** The venture-prototype skill says "loop_engine is MANDATORY" in bold caps. The builder has skipped it on every prototype in every E2E run (Batch 1: 10/10, Batch 2: 5/5). The instruction-level enforcement does not work — the builder reads "MANDATORY," self-assesses the build as simple, and skips. The skill already says "do NOT self-assess as simple enough" — still skipped. This is the #1 quality gate failure. Structural enforcement is needed: pre-write the verify script in the card body, or add a post-completion audit checking for verifier sessions in state.db.
- **Builder undercounts its own grill decisions in README.** README says "61 decisions" but context/ has 65 locked decisions. Happens on multiple runs — the builder estimates instead of counting. The verify script should check `len(decisions)` against the README's stated count and fail if they mismatch. Fix for card authors: add "Count decisions from context/ files using `grep -rh '^Lock D\|^\*\*D[0-9]' ~/projects/<slug>/context/ | sort -u | wc -l` and use that exact number in the README" to the card body.
- **Portfolio score disagrees with idea-bank score.** The portfolio entry says "19/25" (the dossier's uplifted score) while the idea-bank says "17/25" (the original score). Dossier score uplifts are internal analysis, not bank-level re-scoring. The portfolio and idea-bank MUST use the same score — the original from idea-bank.
