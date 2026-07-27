# Kanban Card Creation Pitfalls (2026-07-24)

## 1. Shell truncates multiline bodies

Creating cards via `terminal("hermes kanban create --body '...'")` loses everything after the first newline. The shell quoting in heredoc/variable expansion mangles newlines.

**Fix:** Use the `kanban_create` tool (Python API) directly. It handles multiline bodies correctly:

```python
kanban_create(
    title="...",
    assignee="builder",
    body="""multiline
body
here""",
    board="hermes-hq",
    parents=["t_prev_card_id"]  # for chaining
)
```

## 2. CLI `show` truncates displayed body

`hermes kanban --board hermes-hq show <id>` only displays ~50 chars of the body. This is a display limit, not data loss. The full body IS stored in the DB. Verify:

```bash
python3 -c "
import sqlite3
c = sqlite3.connect('~/.hermes-teams/startup/kanban/boards/hermes-hq/kanban.db').cursor()
c.execute('SELECT length(body), substr(body,1,200) FROM tasks WHERE id=\"t_xxx\"')
print(c.fetchone())
"
```

The builder's `kanban_show` tool returns the FULL body — the builder reads complete instructions.

## 3. One card per idea (NOT one card for N ideas)

A builder kanban session is one `hermes -p builder chat -q "work kanban task t_xxx"` process. It runs until `kanban_complete` or the session exhausts its turn budget. One session = one idea's full pipeline.

Putting N ideas in one card causes premature completion: the builder spends all turns on the first idea's dossier research and never reaches grilling or building for any idea. Observed 2026-07-24: 5 ideas in one card → 39 messages spent on dossier research for idea 5 → card completed with zero prototypes.

**Correct pattern:** One card per idea, chained sequentially via `--parent`:

```
Card A (idea 1) — no parent → ready immediately
Card B (idea 2) — parent: Card A → auto-promotes when A completes
Card C (idea 3) — parent: Card B → auto-promotes when B completes
...
```

This is exactly what `queue-builds.sh` does. When manually creating test cards, follow the same pattern.
