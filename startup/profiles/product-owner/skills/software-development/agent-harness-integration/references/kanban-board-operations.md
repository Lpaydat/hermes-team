# Kanban Board Operations — correct tool usage patterns

Patterns verified during the ngin ticket creation session (2026-08-05).
Every pattern here was learned by doing it WRONG first, then doing it right.

## 1. Create cards with dependencies atomically

**WRONG:** Create all cards as `ready`, then `INSERT INTO task_links` after.
The window between creation and linking lets the dispatcher claim children
before the parent gate exists. All 21 tickets went to `running` simultaneously.

**RIGHT:** Use `kanban_create` with `parents=["card_id"]`. The card AND its
parent edges are set in one call. Children start as `todo` (blocked). When a
parent completes, `recompute_ready()` promotes children to `ready` automatically.

```
# Frontier card (no parents) → starts as ready
kanban_create(title="...", assignee="tech-lead", board="ngin")

# Child card (has parents) → starts as todo (blocked)
kanban_create(title="...", assignee="tech-lead", board="ngin", 
             parents=["t_parent1", "t_parent2"])
```

## 2. NEVER use raw SQL on kanban.db

The sqlite3 guard blocks writes to `*kanban*.db` and `*workflow-state.db`.
This includes `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`.

If you need to:
- **Create cards** → `kanban_create`
- **Link dependencies** → `kanban_create(parents=[...])` at creation time, or `kanban_link`
- **Archive cards** → `hermes kanban --board <board> archive <card_id>`
- **Clean up a board** → `hermes kanban --board <board> archive <id>` for each card, then `hermes kanban --board <board> gc`
- **Read card state** → `kanban_list` or `hermes kanban --board <board> list --json`

## 3. Board cleanup requires BOTH databases + process kill

When killing a workflow run, clean ALL three:

1. **Kill worker processes** — but DON'T use `pkill -f "ngin"` (matches the
   repo path and kills your own terminal). Use specific PIDs from `ps aux`.
2. **Archive cards** — `hermes kanban --board <board> archive <id>` for each
3. **GC** — `hermes kanban --board <board> gc` purges workspaces and event rows

The workflow-state.db (trigger_keys, trigger_watermark, instances) is cleaned
by the sqlite3 guard from writes — but stale trigger keys can persist. If the
engine won't fire on a new card, check for stale trigger keys via
`hermes kanban --board <board> list` (reads are allowed).

## 4. The dispatcher scans ALL boards automatically

`_tick_once()` in `kanban_watchers.py:1275` enumerates ALL boards via
`list_boards(include_archived=False)` every tick. New boards are discovered
automatically — no restart needed.

When the dispatcher claims a card, `_default_spawn` injects:
- `HERMES_KANBAN_BOARD` — the board slug
- `HERMES_KANBAN_DB` — path to the board's kanban.db
- `HERMES_KANBAN_WORKSPACES_ROOT` — workspaces root for that board

Workers inherit the board context. When a worker calls `kanban_create`, it
defaults to the same board. Cross-board card creation requires explicit
`board=` parameter.

## 5. The workflow pipeline card-routing order

```
[spec] card → assigned to product-owner
  → PO runs to-tickets → creates ticket cards
  → dev-dispatch triggers (PO + [spec] + done) → routes by type
  → tech-lead-execute triggers (tech-lead + [spec] + done) → plan→verify→fix→close
  → qa-gate triggers (verifier + done + verdict=PASS) → QA pipeline
```

Key: the PO decomposes specs into TICKETS. Tech-lead-execute decomposes TICKETS\ninto dev+verify phases. These are different decomposition levels — don't skip\nthe PO.\n\ndev-dispatch creates routing cards for tech-lead, but the `route-tech-lead`\nnode has no `title_template` with `[spec]` prefix. This means tech-lead-execute\n(which triggers on `[spec]` prefix) won't fire on dev-dispatch's output. This\nis a known template design gap.\n\n## 6. [ticket-] prefix now triggers tech-lead-execute (commit 8effed0)\n\nAs of 2026-08-05, `tech-lead-execute.json` uses `title_prefix_any` instead of\n`title_prefix`:\n\n```json\n\"title_prefix_any\": [\"[spec]\", \"[ticket-\"]\n```\n\nThis means pre-decomposed tickets (created by PO via to-tickets with\n`[ticket-XX]` prefix) now trigger the plan→verify→fix→close pipeline.\n\n**Caveat:** if tickets are already atomic, routing through tech-lead-execute\ncauses redundant decomposition (tech-lead treats each as a mini-spec and\nspawns dev+verify children). For atomic tickets, assign to `developer`\ndirectly.\n\n## 7. NEVER pkill -f with board name — it kills your terminal\n\n`pkill -f "hermes.*ngin"` matches YOUR terminal if the board name appears in\nyour cwd or command line. This causes exit code -9 and loses your session.\n\n**Right way:** `ps aux | grep "hermes.*work kanban task"` to find worker PIDs,\nthen `kill -9 <pid1> <pid2>` with specific PIDs only.\n\n## 8. sqlite3 guard scope: real DBs only, not test DBs\n\nThe guard protects ONLY databases under `~/.hermes-teams/startup/kanban/`.\nTest databases in `/tmp` or other locations are NOT blocked. This was a bug\nin the initial guard (pattern `*kanban*.db` matched test fixtures like\n`/tmp/wf-test-XXX/kanban.db`), which broke the workflow engine test suite.\n\nThe Python guard (`sitecustomize.py`) checks the path against\n`~/.hermes-teams/startup/kanban`. The CLI guard should do the same but may\nstill have the broad pattern — if tests fail with sqlite3-guard errors, check\nwhether the CLI guard was updated.
