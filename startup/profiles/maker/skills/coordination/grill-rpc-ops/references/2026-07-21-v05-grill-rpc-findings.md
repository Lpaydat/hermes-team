# v0.5 E2E Findings — grill-rpc skill, auto-lock, no-tag fallback

## What changed in v0.5

### 1. grill-rpc skill (replaces grill-with-docs)

Created `shared-skills/grill-rpc/SKILL.md` — our own grilling skill with the RPC protocol embedded. Loaded via `--skills grill-rpc` instead of `--skills grill-with-docs`.

**Why:** User directive: "don't touch official Matt Pocock skills." grill-with-docs is Matt Pocock's. Our protocol instructions (`<Q>` tags, branch awareness, "don't re-ask") were in the `-z` prompt, which is weaker than skill context. Moving them into a skill makes them system-level context — PO is more likely to comply.

**Result:** PO still doesn't reliably use `<Q>` tags (~50% compliance). But the grilling quality is excellent — the skill's methodology ("one question at a time, provide recommended answers, push past easy answers") works well.

### 2. Auto decision-locking

answer.sh extracts `Lock D{n}: title = content` from the BUILDER's answer text and writes to the active branch file automatically.

**Why:** In v0.4, the orchestrator had to manually edit branch files to lock decisions. This was tedious and error-prone — during the E2E test, many decisions were stated in answers but never written to files.

**Result:** Builder writes `Lock D1: Product = CLI command` in their answer, answer.sh's grep extracts it and appends to the branch file. No manual editing needed.

### 3. No-tag-tolerant question extraction

answer.sh tries `<Q>` tags first, falls back to last paragraph containing `?`.

**Why:** PO (glm-5.2) ignores `<Q>` tags ~50% of the time. v0.4 dumped raw output to stderr and exited 1. The fallback extracts the question automatically — no manual intervention needed.

**Result:** In unit testing, the fallback correctly identifies the question paragraph. In live testing, it needs E2E validation (not yet tested with v0.5).

### 4. Auto _state.md updates

answer.sh counts `^D[0-9]` lines in each branch file and updates the decision count in _state.md's table after every turn.

**Why:** v0.4 required manual sed commands to update _state.md. Often forgotten during fast-paced grilling, leaving decision counts stale.

## Shell scripting lessons (confirmed from v0.4, still relevant)

1. `bc` not installed → use `$((...))` directly
2. `date` locale → `LC_ALL=C date -u`  
3. `grep -c` + `set -e` → always `|| true` + `${VAR:-0}`
4. Thai Buddhist calendar locale gives year 2569

## What still needs E2E testing

- grill-rpc skill compliance (does system context improve `<Q>` tag usage?)
- Auto-lock extraction in live conditions
- Fallback question extraction quality with real PO output
- Auto _state.md updates in a full grill

## Files

- `shared-skills/grill-rpc/SKILL.md` — the new grilling skill
- `shared-skills/self-grill/scripts/answer.sh` — v0.5 with all three fixes
- `shared-skills/self-grill/SKILL.md` — updated for grill-rpc + Lock syntax
