---
name: self-grill
description: "Relentless design grill — PO grills you via file-based RPC until the design is resolved or dead."
disable-model-invocation: true
---

# Self-grill

Launch PO to grill you on an idea. The grill works through 8 design branches one at a time. Each branch is a markdown file — decisions and Q&A logged as they happen. PO sees the current branch + state table every turn, so it can't re-ask resolved questions.

## What's new in v0.5

- **grill-rpc skill** — our own grilling skill, loaded instead of grill-with-docs. Contains the grilling method + RPC protocol in system context (stronger than `-z` prompt).
- **No-tag-tolerant question extraction** — tries `<Q>` tags first, falls back to last paragraph with `?`. Works with any model.
- **Decision auto-locking** — write `Lock D{n}: title = content` in your answer, answer.sh extracts and writes to branch file automatically.
- **Auto _state.md updates** — decision counts update after every turn.

## How it works

```
8 branches (design categories):
  01-product → 02-user → 03-mechanism → 04-data →
  05-edges → 06-output → 07-deployment → 08-constraints

Each turn:
1. answer.sh extracts LOCK decisions from your answer → writes to branch file
2. answer.sh injects [GRILL STATE: branch table + active branch Q&A] as prefix
3. PO sees what's locked, what's been asked, what's open
4. PO asks next question (in <Q> tags or natural prose — both work)
5. answer.sh extracts question, logs Q&A to branch file, updates _state.md
6. When a branch is exhausted, orchestrator marks it done + moves to next
7. Grill complete when all 8 branches are done
```

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
  --skills grill-rpc \
  -z "Grill the builder on this idea.

      You will see [GRILL STATE...] before each answer — branch table + active branch.
      Do NOT re-ask anything in 'Questions already asked.'
      Stay on the active branch. Push past easy answers. 20+ questions is normal.

      Idea: <your idea>" \
  --cli

# Capture session key
hermes -p product-owner sessions list | grep "cli" | head -1 | awk '{print $NF}'
echo "<session-id>" > "$STATE_DIR/SESSION.key"
```

Note: `--skills grill-rpc` loads our custom skill (in shared-skills/). The RPC protocol + `<Q>` tag instructions are in the skill, not the `-z` prompt.

### Inner loop (Q&A within one branch)

```bash
HERMES_GRILL_STATE_DIR="$STATE_DIR" \
"$STATE_DIR/answer.sh" "<your answer>"
```

answer.sh does (all automatically):
1. Extracts `Lock D{n}: ...` from your answer → writes to branch file
2. Injects `[GRILL STATE]` prefix
3. Sends your answer to PO
4. Extracts question (`<Q>` tag or last paragraph with `?`)
5. Logs Q&A to branch file
6. Updates _state.md decision counts

Use background mode with 300s+ timeout.

### Locking decisions

In your answer, include lines like:
```
Lock D1: Product form = CLI command, stdout output
Lock D2: Input = static JSON config
```

answer.sh extracts these automatically. No manual file editing needed.

### Moving between branches

When the active branch is exhausted, update _state.md:
```bash
STATE="$STATE_DIR/context/_state.md"
sed -i 's/| 1 | product | active/| 1 | product | done/' "$STATE"
sed -i 's/| 2 | user | pending/| 2 | user | active/' "$STATE"
sed -i '/^## Active branch/{n;s/.*/user/}' "$STATE"
```

### Done criteria

```bash
grep "| pending\|| active" "$STATE_DIR/context/_state.md"
# Empty output = all branches done = grill complete
```

### Export to spec

```bash
for f in "$STATE_DIR"/context/0*.md; do
    echo "--- $(basename "$f") ---"
    cat "$f"
done > "$STATE_DIR/SUMMARY.md"
```

## Timeout guidance

PO takes 60-200s per turn. Never use foreground terminal with 120s timeout.

## Known issues

1. **Session key capture** — after launching PO, save the session key to SESSION.key immediately.

2. **Question fallback** — if both `<Q>` tag and paragraph fallback fail, answer.sh exits 1 with raw output on stderr.
