---
name: self-grill
description: "Relentless design grill — PO grills you via file-based RPC until the design is resolved or dead."
disable-model-invocation: true
---

# Self-grill

Launch PO to grill you on an idea. The grill works through 8 design branches one at a time. Each branch is a markdown file — decisions and Q&A logged as they happen. PO sees the current branch + state table every turn, so it can't re-ask resolved questions.

## How it works

```
8 branches (design categories):
  01-product → 02-user → 03-mechanism → 04-data →
  05-edges → 06-output → 07-deployment → 08-constraints

Each turn:
1. answer.sh injects [GRILL STATE: branch table + active branch content] as prefix
2. PO sees what's locked, what's been asked, what's open
3. PO asks next question (wrapped in <Q> tags)
4. answer.sh extracts question, logs Q&A to branch file
5. When a branch is exhausted, orchestrator marks it done + moves to next
6. Grill complete when all 8 branches are done
```

## Why branches solve re-asking

PO re-asks because CONTEXT.md was a 12KB blob mixing everything. With branches:
- PO sees only the active branch's questions + decisions (small, focused)
- The state table shows which branches are done (don't go back)
- Q&A is logged to the branch file automatically — permanent record per category

## Setup

```bash
STATE_DIR="/tmp/grill-<slug>"
mkdir -p "$STATE_DIR"
rm -f "$STATE_DIR/SESSION.key"

cp "$HOME/.hermes-teams/shared-skills/self-grill/scripts/answer.sh" "$STATE_DIR/answer.sh"
cp "$HOME/.hermes-teams/shared-skills/self-grill/scripts/init_branches.sh" "$STATE_DIR/init_branches.sh"
chmod +x "$STATE_DIR/answer.sh" "$STATE_DIR/init_branches.sh"

# Initialize branches
"$STATE_DIR/init_branches.sh" "$STATE_DIR" "<your idea>"
```

This creates `context/` with `_state.md` + 8 branch files.

## The grill

### Launch PO

```bash
HERMES_GRILL_STATE_DIR="$STATE_DIR" \
hermes -p product-owner \
  --skills grill-with-docs \
  -z "Grill the builder on this idea via file-based RPC.

      You will see [GRILL STATE...] before each answer. It shows:
      - A branch table (which design categories are done/pending)
      - The active branch with its locked decisions and questions already asked

      RULES:
      - Do NOT re-ask anything in 'Questions already asked'
      - Wrap EVERY question in <Q> tags: <Q>Your question</Q>
      - Stay on the active branch. Don't jump ahead.
      - Push past the builder's first concession. 50+ questions is normal.

      Idea: <your idea>" \
  --cli

# Capture session key
hermes -p product-owner sessions list | grep "cli" | head -1 | awk '{print $NF}'
echo "<session-id>" > "$STATE_DIR/SESSION.key"
```

### Inner loop (Q&A within one branch)

```bash
HERMES_GRILL_STATE_DIR="$STATE_DIR" \
"$STATE_DIR/answer.sh" "<your answer>"
```

answer.sh does:
1. Injects `[GRILL STATE]` prefix (branch table + active branch decisions/questions)
2. Sends your answer to PO via session resume
3. Extracts `<Q>` tag → prints clean question
4. Logs this Q&A to the active branch file

Use background mode with 300s+ timeout:
```python
terminal(background=true, notify_on_complete=true, timeout=300,
         command=f'HERMES_GRILL_STATE_DIR="{STATE_DIR}" "{STATE_DIR}/answer.sh" "{answer}"')
process(action='wait', session_id=<id>, timeout=60)
```

### Locking decisions

When you and PO agree on a decision, the orchestrator locks it manually:

```bash
# Add decision to active branch file
BRANCH_FILE="$STATE_DIR/context/01-product.md"
# Edit the file: replace "(none yet)" under Decisions with the locked decision
```

Then update _state.md decision count for that branch.

### Moving between branches

When the active branch is exhausted (PO can't find new questions):

```bash
# Mark branch as done in _state.md
sed -i 's/| 1 | product | pending/| 1 | product | done/' "$STATE_DIR/context/_state.md"
sed -i 's/| 1 | product | active/| 1 | product | done/' "$STATE_DIR/context/_state.md"

# Set next branch as active
sed -i 's/^## Active branch/## Active branch\n# old below/' "$STATE_DIR/context/_state.md"
echo "user" >> "$STATE_DIR/context/_state.md"
```

Or just edit `_state.md` directly — change the active branch and mark the old one done.

### Done criteria

The grill is done when ALL 8 branches are marked done in `_state.md`. This is mechanical — check the table:

```bash
grep "| pending\|| active" "$STATE_DIR/context/_state.md"
# Empty output = all branches done = grill complete
```

### Export to spec

When done, each branch file contains decisions + Q&A. Concatenate them for a full spec:

```bash
for f in "$STATE_DIR"/context/0*.md; do
    echo "--- $(basename "$f") ---"
    cat "$f"
done > "$STATE_DIR/SUMMARY.md"
```

## Timeout guidance

PO takes 60-200s per turn. Never use foreground terminal with 120s timeout.

## Known issues

1. **PO sometimes ignores <Q> tags** — answer.sh falls back to stderr with raw output. Read the question manually.

2. **PO doesn't lock decisions** — the orchestrator (you) locks them by editing branch files. PO just grills.

3. **Session key capture** — after launching PO, save the session key to SESSION.key immediately.
