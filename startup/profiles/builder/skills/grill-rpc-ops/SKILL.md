---
name: grill-rpc-ops
description: "Operational playbook for self-grill RPC sessions — PO launch, branch management, timeout patterns, known pitfalls."
disable-model-invocation: true
---

# Grill RPC Operations

Operational reference for running grill sessions. Covers the mechanics that `self-grill` delegates here: PO launch recipe, answer pattern, branch management, timeout handling, and model quirks.

## Scripts (in `shared-skills/self-grill/scripts/`)

| Script | Purpose |
|--------|---------|
| `init_branches.sh` | Create empty `_state.md` — zero branches. |
| `add_branch.sh` | Create a new branch file + add row to `_state.md`. Idempotent. |
| `set_active.sh` | Mark a branch active, others move to done. |
| `answer.sh` | Send answer to PO, extract question, auto-lock decisions, update state. |

## PO Launch Recipe

```bash
STATE_DIR="/tmp/grill-<slug>"
mkdir -p "$STATE_DIR"

cp ~/.hermes-teams/shared-skills/self-grill/scripts/*.sh "$STATE_DIR/"
chmod +x "$STATE_DIR"/*.sh

"$STATE_DIR/init_branches.sh" "$STATE_DIR" "<idea>"

HERMES_GRILL_STATE_DIR="$STATE_DIR" \
hermes -p product-owner \
  --skills grill-rpc \
  -z "Grill the builder on: <idea>. You will see [GRILL STATE...] before each answer. Branches are dynamic — propose categories as needed." \
  --cli

hermes -p product-owner sessions list | grep "cli" | head -1 | awk '{print $NF}' > "$STATE_DIR/SESSION.key"
```

## Answer Pattern

```bash
HERMES_GRILL_STATE_DIR="$STATE_DIR" \
"$STATE_DIR/answer.sh" --file /dev/stdin << 'ANSWER'
Lock D1: Title = Value

Your answer text here.
ANSWER
```

answer.sh automatically:
1. Extracts `Lock D{n}: title = content` → writes to branch file
2. Injects `[GRILL STATE]` prefix (branch table + active branch Q&A)
3. Sends answer to PO via `hermes --resume`
4. Extracts question: `<Q>` tag first, fallback to last paragraph with `?`
5. Logs Q&A to branch file
6. Updates `_state.md` decision counts dynamically

## Branch Management

```bash
"$STATE_DIR/add_branch.sh" "$STATE_DIR" "security model"   # add
"$STATE_DIR/set_active.sh" "$STATE_DIR" "security model"    # switch active
grep "pending\|active" "$STATE_DIR/context/_state.md"       # empty = all done
```

Branch names normalize spaces→hyphens: "product form" → `product-form.md`.

## Decision Locking

```
Lock D1: product form = CLI command
Lock D2: input = JSON config file
```

answer.sh extracts these via grep and inserts them under `## Decisions` in the active branch file.

## Timeout (CRITICAL)

glm-5.2 takes **60-200 seconds per turn**. Never foreground `hermes --resume` with <300s timeout — gets interrupted (exit 130).

**Correct pattern:** background=true + notify_on_complete=true + repeated `process wait(timeout=60)`.

answer.sh wraps `hermes --resume` in `HERMES_GRILL_TIMEOUT` (default 600s) internally.

## Model Quirks

### `<Q>` tag compliance

glm-5.2 uses `<Q>` tags ~50% of the time. Fallback (last paragraph with `?`) catches the rest. `<LOCK>` and `<DONE>` tags have 0% compliance — decisions are locked by the builder, not PO.

### Vision

zai API has **no vision models** — all glm variants reject image content types. Use OpenRouter/Google for vision. Config key: `auxiliary.vision.{provider,model}`.

### Config caching

`delegation.max_iterations` and other config values are cached at engine startup. Changes on disk don't affect the running session. Restart to apply.

## Done Criteria

```bash
grep "| pending" "$STATE_DIR/context/_state.md" && echo "STILL GOING" || echo "DONE"
grep "| active" "$STATE_DIR/context/_state.md" && echo "STILL GOING" || echo "DONE"
```

## Skill Registration

Shared skills live in `~/.hermes-teams/shared-skills/<name>/` but must be symlinked into `~/.hermes-teams/startup/profiles/builder/skills/<name>` to be loadable via `skill_view`:

```bash
ln -s ~/.hermes-teams/shared-skills/<name> ~/.hermes-teams/startup/profiles/builder/skills/<name>
```

## Reference Files

See `references/` for dated findings from past sessions:
- PO timeout patterns, vision provider findings, dynamic branch E2E tests, anti-rationalization gate, build-queue pipeline architecture, four-door model (Problem/Opportunity/Copycat/User), config cache findings, fact-verification patterns.
