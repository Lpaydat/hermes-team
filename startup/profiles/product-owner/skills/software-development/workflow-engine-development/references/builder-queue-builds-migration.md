# Builder Grill→Build Migration: Queue-Builds Analysis

**Session:** 2026-08-01
**Goal:** Replace queue-builds.sh's card creation with engine workflow templates.

## What queue-builds.sh does (293 lines)

1. Parses `~/vault/ventures/idea-bank.md` (markdown table, pipe-delimited)
2. Filters: skip `BUILT_AWAITING_REVIEW`, `IN_GRILL`, `building` statuses
3. Sorts by score descending, takes top 10
4. Dedupes: one `hermes kanban list --json` call, checks slug in title/body
5. Creates Grill card: title=`Grill: <name>`, assignee=builder, no parent
6. Creates Build card: title=`Build: <name>`, assignee=builder, parent=grill_id
7. Writes 6h cooldown marker to `~/.last-queue`

## Dispatcher parent-child mechanics

- Build card starts `todo` (parent not done)
- When grill completes, `recompute_ready()` promotes build to `ready`
- Dispatcher spawns builder on the build card
- Engine's `create_card(parent=)` fully supports this
- **Gap:** if parent is blocked/failed, child is stranded forever (no propagation)

## Grill→Build handoff contract

- Grill produces: `~/projects/<slug>/context/` (per-branch .md files with decisions)
- Grill produces: `~/projects/<slug>/.context/grill/decisions.md` (flat summary)
- Build reads both as its spec
- Validation: `validate-grill-output.sh` (grill), `/tmp/verify-<slug>.py` (build)
- **No explicit metadata schema exists** — enforcement is script-based, not metadata-based

## Design options identified

**Option A — Engine owns full pipeline:** command node replaces queue-builds.sh entirely, foreach iterates over idea-bank entries, creates one workflow instance per idea.

**Option B — Engine owns grill→build chain:** queue-builds.sh keeps creating grill cards (or becomes a command node that only creates grill cards). Engine triggers on grill card completion and orchestrates build → handoff.

**Recommended:** Option B for the first junction. queue-builds.sh is battle-tested. The engine replaces the parent-child dependency management and the manual handoff. One junction at a time.

## Design answers (2026-08-01 deep-dive)

### (1) Triggering: manual, not scheduled

The `scheduled` trigger source is NOT implemented in `runtime.py` — only
`card_completed` and `bead_ready` exist. A template with
`"trigger": {"source": "scheduled"}` is silently ignored. Use manual trigger
(no `trigger` field) with Hermes cron wrapping `main.py start`.

### (2) Foreach has a blocking limitation for this use case

Foreach card titles are hardcoded at `runtime.py:1343`:
```python
title=f"[{node.id}#{idx}] {node.skill or 'task'}"
```
This produces `[queue#0] self-grill`, NOT `Grill: <name>`. Since
`builder-grill-build.json` triggers on `title_prefix: "Grill:"`, **the
downstream workflow would never fire**. Requires a `title_template` engine
enhancement (~10 LOC) to fix.

Second limitation: `resolve_template()` does flat key→value replacement only.
`${item.slug}` does NOT work when item is a dict — the engine renders `str(dict)`
which is unusable. Workaround: output flat slug strings; add dot-path resolution
as a follow-up (~15 LOC).

### (3) Grill and build belong in SEPARATE templates

The parent-child kanban link is replaced by the card_completed trigger:
```
Grill card completes → card_completed trigger → builder-grill-build fires → build node dispatches
```
No `--parent` link needed. The trigger system is the dependency mechanism.

### (4) Idea-bank parsing: command node + Python script

Replaces the awk/bash parsing with a Python command node that outputs JSON.
The chain-mode task node creates cards from that JSON.

### (5) Parent-child dependency: eliminated, replaced by trigger

Current: grill card (parent) → `--parent` link → build card (child, auto-promotes).
New: grill card (standalone) → completes → triggers builder-grill-build.

**The existing builder-grill-build.json has a redundant grill node** — it
triggers on "Grill:" card completion but its first node is ALSO a grill task.
This either duplicates grill work or fires at the wrong time. The template
should contain **build + handoff only** — the trigger card IS the grill stage.

## Recommended implementation: Path C (command parse → chain dispatch)

Three implementation paths were evaluated:

| Path | Shape | Works today? | Custom titles? |
|------|-------|-------------|----------------|
| A (native foreach) | command → foreach | ❌ needs title_template | ❌ |
| B (command wrapper) | single command running queue-builds.sh | ✅ | ✅ (script controls) |
| **C (command → chain)** | command parse → chain-mode task | ✅ | ✅ (JSON spec) |

**Path C is recommended** — works today without engine changes, replaces awk
parsing with Python, uses `card_mode: "chain"` for parent-child card pairs,
supports custom titles via JSON child specs.

Template shape (`/tmp/proposed-builder-template.json`):
```json
{
  "id": "builder-queue-builds",
  "nodes": [
    {"id": "parse_idea_bank", "type": "command", "profile": "builder",
     "command": "python3 ~/.../parse-idea-bank.py --board ${trigger.board} --max 10"},
    {"id": "queue", "card_mode": "chain", "profile": "builder", "skill": "self-grill",
     "body_template": "${nodes.parse_idea_bank.output.stdout}",
     "depends_on": ["parse_idea_bank"]}
  ],
  "edges": [{"from": "parse_idea_bank", "to": "queue"}]
}
```

The parse script outputs a JSON list of chain child specs. The chain node
parses it as JSON, creates a parent card, then each child with `--parent`.

## Required engine enhancements (for Path A / future cleanup)

| Enhancement | Priority | LOC | Description |
|-------------|----------|-----|-------------|
| Custom foreach titles (`title_template`) | P0 (blocks Path A) | ~10 | Add optional field; foreach uses it if present |
| Dot-path variable resolution (`${item.slug}`) | P1 | ~15 | `resolve_template()` supports dict dot-paths |
| `scheduled` trigger source | NOT NEEDED | — | Hermes cron owns scheduling; use manual trigger |

## Known bugs in queue-builds.sh (from analysis)

1. "Door D first" header comment is unimplemented — origin parsed but unused
2. `tolower(slug)` awk bug — return value discarded, slug stays cased
3. `context/` vs `.context/` path inconsistency in card bodies
4. Dedup silently disabled if `hermes kanban list` fails (EXISTING=[])
5. Dedup matches done/archived cards (no status filter)
6. `prototype_built` status passes the filter (would re-queue built ideas)
7. Marker format drift: early-exit writes date-only, normal exit writes ISO-8601
