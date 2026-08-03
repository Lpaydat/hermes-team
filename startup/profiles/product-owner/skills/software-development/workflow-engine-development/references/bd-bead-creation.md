# Creating Beads with Dependencies

Quick reference for `bd create` with the dependency types that actually work.

## Dependency types (the ones that matter)

```
parent-child    — link a ticket to its epic
blocked-by      — "this ticket waits on that one" (stored as type=blocks)
blocks          — reverse of blocked-by
```

**Gotcha:** `bd create --deps blocked-by:X` creates a dependency row with
`type=blocks` and `depends_on_id=X`. The JSON output shows it as type `blocks`,
not `blocked-by`. Don't let this confuse you when querying.

**Gotcha:** `parent:X` does NOT work. The correct type is `parent-child:X`.

## Creating an epic + children with dependencies

```python
# Epic
epic = bd_create("Title", type="epic")

# Child with parent link + blocker
bd_create("Child title",
    deps=[f"parent-child:{epic}", f"blocked-by:{blocker_id}"])
```

## Verifying the dependency graph

```bash
# Show reverse deps (who blocks this ticket)
bd show <id> | grep "←"

# List all with JSON, filter by label
bd list --all --json | python3 -c "
import sys, json
for b in json.loads(sys.stdin.read()):
    blockers = [d['depends_on_id'] for d in b.get('dependencies',[])
                if d.get('type') == 'blocks']
    print(f'{b[\"id\"]} blocked-by: {blockers}')
"
```

## Common mistakes

- Using `parent:` instead of `parent-child:` — fails with "unknown dependency type"
- Creating duplicates if the first `bd create` fails on a bad dep type but still
  creates the bead (check output for the ID even on error)
- Forgetting to close duplicates before proceeding
