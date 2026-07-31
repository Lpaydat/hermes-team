# Builder Pipeline Migration — queue-builds.sh → Workflow Template

## The migration pattern (reusable for any cron→template migration)

### Step 1: Analyze the existing script with subagents
Dispatch parallel subagents to analyze: (a) the script line-by-line, (b) the dispatcher's card lifecycle, (c) the handoff contract between cards, (d) the engine's current capabilities.

### Step 2: Identify the junction
queue-builds.sh creates 2 cards per idea: Grill (standalone) + Build (parent=grill). The dispatcher promotes build when grill completes.

### Step 3: Replace with engine template
The engine replaces the script with a workflow:
```
parse_idea_bank (command) → grill (foreach) → build (foreach) → handoff (foreach)
```

The parent-child kanban dependency is replaced by engine edges — the build node only dispatches after all grill cards complete.

### Step 4: Engine features needed
- `title_template` on foreach nodes: `"Grill: ${item.name}"`
- Dot-path resolution: `${item.slug}` resolves dict fields in body and title
- `command` node runs the parse script, outputs JSON, foreach iterates over the `ideas` array

## Key decisions

**One template, not multiple.** Splitting into separate templates (one for grill, one for build) hits the cross-workflow double-fire prevention. Keep it as one template with edges.

**Dedup is critical.** The parse script must check the board for existing cards before outputting ideas. Without dedup, running the workflow twice creates duplicates.

**Foreach waits for ALL items.** With 10 grill cards (max 5 concurrent), the build node waits for all 10. This is slightly slower than independent parent-child pairs but acceptable since the profile processes sequentially anyway.

**Quality assessment: 3 tradeoffs**
1. Dedup: solved by parse script checking board
2. Throughput: acceptable — builder is sequential anyway (max 5 concurrent)
3. Parent-child link: not needed — engine tracks the relationship in state DB

## The parse-idea-bank.py script

Replaces the awk/sed parsing in queue-builds.sh. Reads idea-bank.md, filters out BUILT/IN_GRILL/building, sorts by score, outputs JSON:
```json
{"ideas": [{"slug": "x", "name": "Y", "score": 18}], "count": 1}
```

Supports `--board` (for dedup), `--max N`, `--slugs slug1,slug2` (targeted mode), `--no-dedup`.

## The template structure

```json
{
  "id": "builder-grill-build",
  "nodes": [
    {"id": "parse_idea_bank", "type": "command", "command": "python3 parse-idea-bank.py --board ${trigger.board} --max 10"},
    {"id": "grill", "foreach": "${nodes.parse_idea_bank.output.ideas}", "title_template": "Grill: ${item.name}", "profile": "builder", "skill": "self-grill", "depends_on": ["parse_idea_bank"]},
    {"id": "build", "foreach": "${nodes.parse_idea_bank.output.ideas}", "title_template": "Build: ${item.name}", "profile": "builder", "skill": "venture-prototype", "depends_on": ["grill"]},
    {"id": "handoff", "foreach": "${nodes.parse_idea_bank.output.ideas}", "title_template": "Review: ${item.name}", "profile": "builder", "skill": "prototype-review-handoff", "depends_on": ["build"]}
  ],
  "edges": [
    {"from": "parse_idea_bank", "to": "grill"},
    {"from": "grill", "to": "build"},
    {"from": "build", "to": "handoff"}
  ]
}
```
