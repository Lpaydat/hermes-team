---
name: self-grill
description: "Relentless design grill — PO grills you via file-based RPC until the design is resolved or dead."
disable-model-invocation: true
---

# Self-grill

Launch PO to grill you on an idea. Branches are created dynamically as the grill reveals what design categories matter for THIS specific idea — no hardcoded list. PO identifies what needs interrogation, you add branches, the grill progresses.

## How it works

```
1. Set up empty grill state (no branches)
2. Launch PO with the idea
3. PO asks questions → first few questions reveal what categories matter
4. Ask PO: "What 3-5 design categories does this idea need?"
5. Create branches from PO's answer
6. Grill through each branch (one at a time)
7. Add new branches if the grill surfaces new categories
8. Grill complete when all branches are done
```

## Setup

```bash
STATE_DIR="/tmp/grill-<slug>"
mkdir -p "$STATE_DIR"
rm -f "$STATE_DIR/SESSION.key"

cp "$HOME/.hermes-teams/shared-skills/self-grill/scripts/answer.sh" "$STATE_DIR/answer.sh"
cp "$HOME/.hermes-teams/shared-skills/self-grill/scripts/init_branches.sh" "$STATE_DIR/init_branches.sh"
cp "$HOME/.hermes-teams/shared-skills/self-grill/scripts/add_branch.sh" "$STATE_DIR/add_branch.sh"
cp "$HOME/.hermes-teams/shared-skills/self-grill/scripts/set_active.sh" "$STATE_DIR/set_active.sh"
chmod +x "$STATE_DIR"/*.sh

# Initialize (no branches yet)
"$STATE_DIR/init_branches.sh" "$STATE_DIR" "<your idea>"
```

## The grill

### Launch PO

```bash
HERMES_GRILL_STATE_DIR="$STATE_DIR" \
hermes -p product-owner \
  --skills grill-rpc \
  -z "Grill the builder on this idea.

      You will see [GRILL STATE...] before each answer. It shows:
      - A branch table (which design categories are done/active/pending)
      - The active branch with locked decisions and questions already asked

      Branches are dynamic. Start by asking questions about the idea.
      After 2-3 questions, I'll ask you what design categories this idea needs.
      You can propose new branches at any time during the grill.

      RULES:
      - Do NOT re-ask anything in 'Questions already asked'
      - Wrap EVERY question in <Q> tags: <Q>Your question</Q>
      - Stay on the active branch. Don't jump ahead.
      - Push past easy answers. 20+ questions is normal.

      Idea: <your idea>" \
  --cli

# Capture session key
hermes -p product-owner sessions list | grep "cli" | head -1 | awk '{print $NF}'
echo "<session-id>" > "$STATE_DIR/SESSION.key"
```

### Phase 1: Discovery (first 2-3 questions)

Let PO ask questions naturally. Don't create branches yet. After 2-3 exchanges, ask PO:

```
Based on what you've learned, what 3-5 design categories does this idea need?
List them as category names (e.g. "product form", "data sources", "edge cases").
```

Create branches from PO's answer:

```bash
"$STATE_DIR/add_branch.sh" "$STATE_DIR" "product form"
"$STATE_DIR/add_branch.sh" "$STATE_DIR" "data sources"
"$STATE_DIR/set_active.sh" "$STATE_DIR" "product form"
```

### Phase 2: Grill through branches

```bash
HERMES_GRILL_STATE_DIR="$STATE_DIR" \
"$STATE_DIR/answer.sh" "<your answer>"
```

answer.sh does automatically:
1. Extract `Lock D{n}: title = content` from your answer → writes to branch file
2. Inject `[GRILL STATE]` prefix
3. Send answer to PO
4. Extract question (`<Q>` tag or last paragraph with `?`)
5. Log Q&A to branch file
6. Update _state.md decision counts

Use background mode with 300s+ timeout.

### Adding branches mid-grill

When the grill surfaces a new category:

```bash
"$STATE_DIR/add_branch.sh" "$STATE_DIR" "security"
```

### Locking decisions

In your answer, include:
```
Lock D1: Product form = CLI command
Lock D2: Input = JSON config
```

### Moving between branches

When the active branch is exhausted:

```bash
"$STATE_DIR/set_active.sh" "$STATE_DIR" "next branch name"
```

### Done criteria

```bash
# Check for pending or active branches
grep "| pending\|| active" "$STATE_DIR/context/_state.md"
# Empty = all done = grill complete
```

### Export

```bash
for f in "$STATE_DIR"/context/*.md; do
    [[ "$(basename "$f")" == "_state.md" ]] && continue
    echo "--- $(basename "$f") ---"
    cat "$f"
done > "$STATE_DIR/SUMMARY.md"
```

## Timeout guidance

PO takes 60-200s per turn. Never use foreground terminal with 120s timeout.

## Known issues

1. **Session key capture** — save to SESSION.key immediately after launching PO.
2. **Question fallback** — if `<Q>` and paragraph fallback both fail, read stderr.
