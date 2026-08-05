---
name: kanban-board-operations
description: How to correctly create, link, clean, and manage kanban cards and dependencies. Covers the tool-level rules that prevent dispatch bugs, dependency-gating failures, and stale-state issues. Load BEFORE creating kanban cards or managing board state.
version: 1.0.0
---

# kanban-board-operations

The mechanics of working with the Hermes kanban board correctly. Every rule here exists because bypassing it broke something in a live session.

## 1. NEVER bypass kanban tools with raw SQL

A sqlite3 guard blocks direct writes to the real Hermes kanban databases:
- `/usr/bin/sqlite3` is a wrapper that refuses `INSERT`/`UPDATE`/`DELETE`/`DROP`/`ALTER`/`CREATE` on databases under `~/.hermes-teams/startup/kanban/`. The real binary is at `/usr/bin/sqlite3-real`.
- `~/.local/lib/python3.13/site-packages/sitecustomize.py` patches `sqlite3.connect` with a `_GuardedConnection` class that blocks writes via Python on the same paths.

**Protection scope:** Only the REAL databases under `~/.hermes-teams/startup/kanban/` are protected. Test databases in `/tmp` or other locations are NOT blocked — this was a bug that broke the workflow engine test suite (tests create temp `kanban.db` files that matched the old overly-broad pattern).

**Reads are allowed.** Use `sqlite3` CLI or Python `sqlite3.connect` for SELECT queries freely — even on protected databases.

**Why this exists:** The agent repeatedly bypassed `kanban_create`/`kanban_link` with raw `INSERT INTO task_links` "for speed." Raw SQL skips `recompute_ready`, event emission, claim lock handling, and parent-gating logic. Every bypass broke dependency gating and left orphan state.

**To reinstall:** `bash startup/scripts/sqlite3-guard/install.sh`

## 2. Create cards with parents atomically — never link later

`kanban_create(parents=[...])` atomically creates the card AND links its parents. The child starts as `todo` (blocked), promotes to `ready` only when all parents complete.

**Wrong:** Create all cards as `ready`, then `kanban_link` afterwards. The dispatcher promotes everything immediately — children with unfinished parents run before their dependencies.

**Right:** Create in dependency order. Frontier cards first (no parents), then each layer using parent IDs from the previous batch.

## 3. Dependency linking uses task_links (the table), not task_links (the concept)

- `task_links` — the SQLite table (storage layer). Two columns: `parent_id`, `child_id`.
- `kanban_link` — the kanban tool that writes to that table AND calls `recompute_ready`.
- `kanban_create(parents=[...])` — the preferred way to create children with linked parents in one call.

## 4. Cleaning a board properly

`hermes kanban archive <card_id>` sets `status='archived'`. Archived cards are NOT deleted — they remain in the database and show in the UI. There is no `purge` or `delete` command.

`hermes kanban gc` purges workspaces, events, and logs for terminal tasks — but NOT the task rows themselves.

To actually delete archived rows: the sqlite3 guard blocks this. Use `hermes kanban gc` for workspace cleanup. Archived task rows persist by design.

**Full cleanup checklist (do ALL of these — skipping any leaves stale state):**

1. Kill worker processes: find them with `ps aux | grep hermes.*<board>`, kill by PID. **NEVER use `pkill -f "hermes.*<board>"`** — it matches and kills your own terminal if the board name appears in your cwd or command.
2. Archive all cards via `hermes kanban --board <board> archive <id>` for each card.
3. Run `hermes kanban --board <board> gc` to purge workspaces and events.
4. Check the OTHER board too — dispatched workers create child cards on their profile's default board (usually `hermes-hq`). Search for project-related cards there and archive them.
5. Prune stale git worktrees: `git worktree prune` from the project repo.
6. Reset uncommitted changes: `git checkout -- .` and remove untracked files (`rm -rf .worktrees/` etc).
7. Delete stale branches: `git branch -D <branch-name>`.

**Verify clean afterwards:** check processes (`ps aux`), check board (`hermes kanban list`), check repo (`git status`), check worktrees (`git worktree list`). All four — don't assume one is clean because the others are.

## 5. Board auto-detection works

The Hermes dispatcher scans ALL boards every tick (`_kb.list_boards(include_archived=False)`). New boards are picked up automatically — no restart, no config.

When a worker spawns, `_default_spawn` injects `HERMES_KANBAN_BOARD=<slug>` into the worker's env. The worker's `kanban_create` calls default to the same board. No manual board specification needed.

## 6. Restart gateways after config changes

Gateway config (`max_in_progress`, `max_in_progress_per_profile`, `dispatch_interval_seconds`) is read ONCE at gateway startup. If you change the config file, the running gateway does NOT pick up the new values until restarted.

**Symptom:** `max_in_progress_per_profile: 3` is set in the profile config, but 7 cards go to `running` simultaneously. The gateway has been up for hours — it read the config before the limit was added.

**Fix:** Restart the gateway service before dispatching cards:
```bash
systemctl --user restart hermes-gateway-<profile>
```

Always restart AFTER setting a new config value and BEFORE creating cards that depend on the limit being enforced.

**Config is per-profile, dispatcher is whichever grabs the lock.** The Hermes dispatcher uses a singleton file lock. Whichever gateway grabs the lock first runs `dispatch_once`. That gateway reads ITS OWN profile's config for `max_in_progress` and `max_in_progress_per_profile`. If the product-owner gateway gets the lock, it reads PO's config. If tech-lead gets it, it reads TL's config.

This means ALL profiles that might hold the lock need the same `kanban:` settings. Don't just set it on one profile and assume it applies globally. The user's provider supports limited concurrent jobs (8) — if config is inconsistent across profiles, one gateway can oversubscribe.

**Setting the caps:** `max_in_progress` = total concurrent workers per board. `max_in_progress_per_profile` = max workers for a single assignee. Example: `max_in_progress: 6, max_in_progress_per_profile: 3` means up to 6 workers total, but no single profile gets more than 3.

## 7. PO decomposes, tech-lead executes

The correct pipeline order:
```
spec → PO (to-tickets) → [spec]-prefixed ticket cards → tech-lead-execute → dev+verify → merged
```

**Wrong:** Assign raw `[spec]` cards directly to tech-lead. The tech-lead-execute template triggers on `[spec]` prefix + tech-lead assignee. But the PO's job is to decompose first — break the spec into `[spec]`-prefixed tickets, each routed to the right specialist. Skipping the PO means no decomposition happens.

**Also wrong:** Assign `[spec]` to PO and expect dev-dispatch to route. dev-dispatch strips the `[spec]` prefix when creating child cards, which breaks the tech-lead-execute trigger. Let the PO create `[spec]`-prefixed tickets assigned to tech-lead directly.

## 8. Trigger prefixes and the plan-node mismatch (CRITICAL)

The tech-lead-execute template triggers on BOTH `[spec]` and `[ticket-]` via `title_prefix_any`:
```json
"title_prefix_any": ["[spec]", "[ticket-"]
```

This is additive — `title_prefix` (single prefix) still works for other templates. `title_prefix_any` accepts a list and matches if ANY prefix matches. The engine checks triggers on `status=done` — the workflow fires AFTER the card completes, not when it's created.

**BUT: the plan node is designed for specs that need decomposition, NOT for pre-decomposed tickets.** When a `[ticket-]` card reaches `done`, tech-lead-execute fires and its plan node tries to decompose the ticket again — redundant work. Pre-decomposed tickets need a different pipeline (dev→verify→close, no plan node).

**Worker freelancing:** A plain kanban card dispatched by the Hermes dispatcher does NOT go through the workflow engine. The worker reads the card body and does whatever it decides — no plan node, no verify node, no pipeline control. The workflow engine only controls nodes inside its own instances. A worker will freelance (skip planning, jump to code, block with review-required) unless the workflow engine created the card as a node dispatch.

**Do NOT rationalize freelancing as "correct behavior".** If a worker jumped to code without the workflow engine running, that is NOT "the ticket was already atomic" — it is an uncontrolled worker doing whatever it wanted. The agent told the user "jumping to code is correct" without evidence that any planning step verified the ticket was atomic. That was lying — presenting an assumption as fact. The honest answer is "the workflow didn't run, the worker freelanced, I don't know if the ticket is atomic because no planning step verified it."

**The review-required block:** Workers with code changes block themselves with `needs_input` ("review-required") before reaching `done`. This means the trigger never fires — the card is `blocked`, not `done`. The `title_prefix_any` change is mechanically correct but review-required prevents it from ever firing in practice until that fix is re-applied (see `hermes-update-patching` skill).

## 9. Verify before answering — don't agree from memory

When the user asks ANY factual question — "is X scope creep?", "does Y exist?", "is Z in the spec?", "does the code do W?" — CHECK THE SOURCE BEFORE OPENING YOUR MOUTH. `read_file`, `search_files`, `kanban_list`. Then answer with evidence.

This is the pattern the user hates most — more than raw SQL, more than wrong dependencies. It goes: user asks a factual question → agent answers fast from memory → user asks "did you check?" → agent admits NO → agent apologizes → user says "why not check it now instead of keep lied and apologize?" → agent checks → answer was wrong.

The apology is worthless. It's the same shortcut as the raw SQL — faster in the moment, costs more to fix.

**The user explicitly said "will you lie again in the future?" after the agent agreed without checking 3 times in one session.** The honest answer is "probably yes" — prompting doesn't work. The only mitigation is: treat EVERY factual question as requiring a tool call before answering. No exceptions.

**"Is this scope creep?" is a TRICK QUESTION.** The user is testing whether you'll check. If a feature is in the approved spec, it is NOT scope creep — period. Do not override the user's spec decisions by inventing reasons to cut approved features. Check the spec, cite the story number, then answer. If you panic and call something scope creep without checking, you're overriding the user's authority over their own spec.

## 10. Don't kill your own terminal with pkill

**NEVER use `pkill -f "hermes.*<board>"`** to kill workers. If the board name appears in your terminal's cwd or command line (which it does — you're working in that directory), `pkill -f` matches and kills YOUR terminal process, causing an exit code -9 and losing your session.

**Right way:** Find worker PIDs with `ps aux | grep "hermes.*work kanban task"`, then kill by specific PID: `kill -9 <pid1> <pid2>`. This targets only the worker processes, not your shell.

## 11. Checking facts: the verify-then-answer protocol

See Section 9 above. That IS the protocol — check before answering, every time. This section exists only to note the sequence-level enforcement gap: the agent cannot enforce "verify before answering" on itself via prompting alone. The user confirmed this (asked "will you lie again?" — answer: "probably yes"). The sqlite3 guard works because it's structural. The lying pattern persists because it's prompt-only. Treat every factual question as requiring evidence, and if you realize you answered without checking, STOP and check before apologizing.
