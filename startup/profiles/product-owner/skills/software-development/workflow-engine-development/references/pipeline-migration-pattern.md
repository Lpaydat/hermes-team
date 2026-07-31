# Pipeline Migration Pattern — Script to Template

> Pattern observed migrating the builder's queue-builds.sh to an engine template.

## The pattern

Many pipeline scripts follow the same shape:
1. Parse input data (file, API, DB)
2. Filter/sort/dedup
3. For each item: create kanban cards (often parent-child pairs)
4. Update a marker/cooldown file

This maps cleanly to engine features:

```
parse (command node) → grill (foreach) → build (foreach) → handoff (foreach)
```

### Step 1: Replace parsing with a command node

Write a Python script that reads the input and outputs JSON. The command
node captures stdout, parses JSON, merges into node output.

```json
{
  "id": "parse",
  "type": "command",
  "command": "python3 ~/.hermes-teams/.../parse-input.py --max 10"
}
```

The script outputs:
```json
{"ideas": [{"slug": "x", "name": "Y", "score": 18}], "count": 1}
```

### Step 2: Replace card creation with foreach

```json
{
  "id": "grill",
  "profile": "builder",
  "skill": "self-grill",
  "foreach": "${nodes.parse.output.ideas}",
  "title_template": "Grill: ${item.name}",
  "body_template": "Slug: ${item.slug}...",
  "depends_on": ["parse"]
}
```

### Step 3: Replace parent-child dependency with edges

The script's `--parent` flag creates a kanban parent-child link (child stays
in `todo` until parent completes, dispatcher promotes). The engine replaces
this with explicit edges — the build foreach dispatches only after the grill
foreach completes.

**No `--parent` needed.** The engine handles sequencing.

## When NOT to use this pattern

- **Scripts that do data sync** (e.g., bead-sync between SQLite and Dolt) —
  these are not workflows, they're imperative data operations. Keep as
  standalone scripts called by command nodes or cron.
- **Scripts that need delivery** (send to Telegram/Discord) — the engine
  has no delivery mechanism. Keep as Hermes cron jobs.
- **Interactive scripts** (require user input) — can't run in command nodes.

## Key insights from the builder migration

1. **Foreach creates cards, not instances.** One foreach node creates N
   cards on the board. The engine watches all N and advances when all complete.

2. **Foreach cards have independent lifecycles.** Each grill card is
   independently claimed, worked, and completed by the dispatcher. The
   engine tracks all of them.

3. **Dot-path resolution enables rich templates.** `${item.slug}`,
   `${item.name}`, `${item.score}` all resolve from dict items. Without
   this, foreach only gets `${item}` as a flat string.

4. **Dedup must be in the parse script.** The engine's idempotency keys
   differ across runs (new instance = new keys). Dedup logic stays in
   the Python parse script, not the template.

5. **The `.context/` vs `context/` inconsistency.** The builder skills
   reference both dotted and non-dotted paths. This is a pre-existing
   inconsistency in the skills, not an engine issue.
