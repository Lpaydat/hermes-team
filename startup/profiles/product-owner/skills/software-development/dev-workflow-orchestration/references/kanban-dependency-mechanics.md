# Kanban Dependency Mechanics — how parent-child, dependency blocks, and recompute_ready actually work

Source: `hermes_cli/kanban_db.py` (read Jul 2026).

## How parent-child links work

### `kanban_link(parent, child)`
- Inserts row into `task_links(parent_id, child_id)`.
- If child is `ready` and parent is NOT `done`, demotes child to `todo` (line 2834).
- **Does NOT affect `running` tasks** — only demotes `ready → todo`.

### `recompute_ready()`
- Runs after EVERY kanban state change (claim, complete, block, link, unblock).
- Checks tasks in `todo` or `blocked` status ONLY.
- For each, checks if ALL parents (via `task_links`) are `done` or `archived`.
- If yes → promotes to `ready`. **Fully automatic — no cron, no scanner.**
- `dependency` block_kind tasks in `todo` are included in promotion checks.
- Does NOT touch `running` tasks.

### `block_task(kind="dependency")`
- Moves task from `running/ready → todo` (NOT `blocked`).
- Sets `block_kind = "dependency"`.
- Emits `dependency_wait` event.
- The task sits in `todo` until `recompute_ready` promotes it.
- **No cron, no scanner, no human needed** — `recompute_ready` handles it.

## Why tech-lead → dev parent-child DOESN'T WORK (deadlock)

```
tech-lead (parent) → dev (child)
  dev stays in `todo` until tech-lead is `done`
  tech-lead can't be `done` until dev completes
  = DEADLOCK
```

`recompute_ready` only promotes tasks whose parents are ALL `done`. If tech-lead is the parent, dev can't start until tech-lead finishes. But tech-lead finishes by calling `kanban_complete` — which requires the work to be done. Circular.

## Why tech-lead blocks on verifier but gets unblocked prematurely (without a link)

```
tech-lead calls kanban_block(kind="dependency", reason="waiting for verifier t_X")
  → tech-lead moves to `todo`
recompute_ready checks: parents of tech-lead in task_links
  → tech-lead has NO parents (it's a root card)
  → "all parents done" = vacuously true → promotes immediately
```

The `reason` text is informational — `recompute_ready` only checks `task_links`, not the reason string. You MUST create a task_link for the dependency gate to work.

## The solution: reverse dependency link + block (delegate-wait pattern)

```
Step 1: Tech-lead creates dev card (orphan — no parent link)
Step 2: Tech-lead creates verifier card (parented on dev card: dev → ver)
Step 3: Tech-lead links ITSELF as CHILD of the verifier:
        kanban_link(parent=verifier_id, child=tech-lead_id)
Step 4: Tech-lead blocks itself:
        kanban_block(kind="dependency")
        → task moves to 'todo', block_kind='dependency'

── auto-pilot ──

Step 5: Dispatcher claims dev → developer builds → dev completes
Step 6: Verifier promotes (dev parent done) → verifier runs → verifier completes
Step 7: recompute_ready fires after verifier completion:
        → tech-lead is in 'todo', block_kind='dependency'
        → check parents: [verifier] → status='done'
        → ALL parents done → promote tech-lead to 'ready'
Step 8: Dispatcher re-dispatches tech-lead
Step 9: Tech-lead reads verifier verdict → kanban_complete
```

### Multiple parallel verifiers (PROVEN Jul 2026)

`delegate-wait.sh --link-only <self_id> <ver1> <ver2> <ver3>`

Creates 3 task_links rows (ver1→self, ver2→self, ver3→self).
`recompute_ready` requires ALL parents done before promoting.

**PROVEN:** 3 parallel dev→verifier chains. Tech-lead stayed in `todo` for 14min 19sec
while verifiers completed one by one. Auto-promoted when the LAST verifier done.
66 tests on main, zero audit violations.

### The bundled approach: `delegate_and_wait` tool (PLUGIN, Jul 2026)

**⚠️ CRITICAL: A bash script (`delegate-wait.sh`) was the first attempt. Tech-lead IGNORED it.**

The script was placed in `~/.hermes-teams/startup/profiles/tech-lead/scripts/delegate-wait.sh`
and referenced in the skill text. Tech-lead skipped it entirely — it created
dev/verifier cards and immediately called `kanban_complete` without running the
script. The model does not reliably follow embedded bash commands buried in
long skill prose. This was caught during C1 battle test R1 (Jul 2026).

**The fix**: a real Hermes plugin tool that appears in tech-lead's tool list.

```
Plugin location: ~/.hermes-teams/startup/profiles/<profile>/plugins/dev_workflow/
Files: plugin.yaml, __init__.py, schemas.py, tools.py
Tool name: delegate_and_wait
Toolset: dev_workflow
```

The tool description makes the purpose self-evident:
"Create developer + verifier cards and block yourself until the verifier
completes. Use this AFTER you have written a contract and are ready to
delegate implementation."

The model sees it in the tool list alongside `kanban_create`, `kanban_block`,
etc. It's a first-class tool call, not prose to interpret.

**Plugin discovery path**: `get_hermes_home()` returns the PROFILE directory
(`~/.hermes-teams/startup/profiles/<profile>/`), NOT `~/.hermes/`. So plugins
go in `<profile-dir>/plugins/<name>/`, not the global `~/.hermes/plugins/`.
Enable per-profile via `hermes plugins enable <name> --profile <profile>`.

Usage in skill (loops-engineering):
```
delegate_and_wait(contracts=[{
  "title": "<short title>",
  "body": "<full contract: ACs, evals_cmd, bead_id, constraints>",
  "workspace_path": "<absolute project dir>"
}])
```

For parallel chains: pass multiple contracts in the array. The tool creates
N dev→verifier pairs and blocks on ALL verifiers.

### How this affects bead-sync

bead-sync needs **zero changes**. `todo` status (dependency block) is not in
`STATUS_MAP`, so bead stays `in_progress` during the wait. When tech-lead
completes after auto-promotion, `card done → bead closed` fires at the
CORRECT time.

### Edge case: FAIL → fix chain → new verifier

If verifier FAILs, it creates a fix card + new verifier. Tech-lead unblocks
(verifier done) and sees FAIL. Skill instructs tech-lead to re-block on the
NEW verifier card (loops-engineering step 7).

**UNTESTED (Jul 2026)**: whether tech-lead actually does this correctly is
agent judgment, not a mechanical guarantee. If tech-lead calls
`kanban_complete` instead of re-blocking, the bead closes prematurely while
the fix chain is still running. This is test case C9 in the battle test plan.

### auto-dispatch label filter gap

`auto-dispatch.sh` filters out `gt:slot` beads but does NOT filter by
`ready-for-agent` label. Any open bead (PRD, epic, documentation) that
`bd ready` shows gets dispatched as a work card. This caused the zombie loop
(contaminated test): PRD bead stayed open → dispatch → tech-lead tries to
"implement" a PRD → archive → re-dispatch → worktree conflict → 48 spawn
failures.

**Fix**: add `if 'ready-for-agent' not in labels: continue` in the dispatch
script's Python parser, alongside the existing `gt:slot` filter.

### Merge conflict routing (UNTESTED)

When a verifier rebases and hits a conflict:
1. Verifier releases merge slot
2. Verifier verdicts FAIL with conflict details (file:line, conflicting SHA)
3. Verifier creates fix card for developer with:
   - `workspace_path` = same worktree (developer goes back to same dir)
   - `body` includes `Resume-Session: <harness_session_id>` (pi warm resume)
   - `body` includes `Branch: <branch_name>` and `Worktree: <path>`
4. Developer picks up fix card → `cd` to worktree → resolves conflict → commits
5. New verifier card reviews the resolution → PASS → merge

The developer has the `resolving-merge-conflicts` skill available. The
worktree persists across all iterations — never destroyed between fix cycles.
