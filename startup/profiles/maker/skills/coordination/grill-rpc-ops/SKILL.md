---
name: grill-rpc-ops
description: "Operational playbook for running grill RPC sessions (builder↔PO design interviews via file-based RPC). Covers timeout management, session-key capture, PO behavioral glitches, and the branch-based state model that prevents re-asking. Load when running or debugging a self-grill or peer-grill-rpc session."
version: 3.0.0
metadata:
  hermes:
    tags: [coordination, grill, rpc, debugging, operations]
    category: coordination
---

# Grill RPC Ops — running grill sessions that don't fall over

The grill skills (`self-grill`, `peer-grill-rpc`) define the architecture. This skill covers what actually happens when you run a full grill end-to-end: timeouts, session-key capture, PO behavioral glitches, and the state model that prevents re-asking.

Load this BEFORE launching a grill.

## Design principle: works with any model grade

The grill system must work with lower-grade models, not just frontier. PO (glm-5.2) does NOT reliably follow structured output instructions — it ignores `<Q>`, `<LOCK>`, `<DONE>` tags. All recovery procedures below assume PO output is unstructured markdown prose. The orchestrator (builder) handles structure, not PO.

## Grill philosophy: design tool, not kill gate

**User directive (2026-07-21):** The grill is NOT a kill gate. Build is cheap — sometimes just a few minutes. The grill exists to make the build SMARTER: right features, right direction, right scope. Don't use the grill to decide whether to build. Use it to point the build correctly before spending the time.

This means:
- Never refuse to build because "the grill hasn't finished" — start building as soon as the key branches (product, mechanism) are locked
- Don't eagerly kill ideas in the grill — let the gate (human) decide promotion
- The grill feeds the build, it doesn't gate it
- For the maker identity: grill is automatic (it's your nature), but the prototype follows immediately after

## Pre-flight checklist

1. **State dir:** `/tmp/grill-<slug>/` with `answer.sh` + `init_branches.sh` copied in
2. **Initialize branches:** `init_branches.sh "$STATE_DIR" "<idea>"` creates `context/` with 8 branch files + `_state.md`
3. **Clear old state:** `rm -f SESSION.key`
4. **Timeout plan:** Every `answer.sh` call runs in background with timeout=300+

## The session-key capture step

**#1 cause of silent grill degradation.** PO cannot self-report its session key — it writes made-up numbers. After launching PO:

```bash
hermes -p product-owner sessions list | grep "cli" | head -1 | awk '{print $NF}'
echo "<session-id>" > "$STATE_DIR/SESSION.key"
```

Without SESSION.key, answer.sh can't resume — every answer creates a fresh disconnected PO session with zero context.

## Branch-based state model (v0.4+)

Replaces the monolithic CONTEXT.md with 8 branch files, one per design category:

```
context/
  _state.md         # Branch status table (done/pending/active)
  01-product.md     # Product form decisions + Q&A
  02-user.md        # User/audience
  03-mechanism.md   # How it works
  04-data.md        # Inputs/data sources
  05-edges.md       # Edge cases
  06-output.md      # Output/share format
  07-deployment.md  # Where it runs
  08-constraints.md # Rate limits, cost, scale
```

**Why branches solve re-asking:** PO sees only the active branch's questions + decisions (small, focused) + a state table showing which branches are done. Can't re-ask because questions are logged. Can't jump back because the table marks resolved branches as done.

Each turn, answer.sh injects `[GRILL STATE]` prefix: branch table + active branch's locked decisions + questions already asked.

**The orchestrator locks decisions** by editing branch files. PO never locks anything — it just grills. This is by design: PO can't reliably output structured data, so don't ask it to.

### Done criteria (mechanical)

All 8 branches marked done in `_state.md`:
```bash
grep "| pending\|| active" "$STATE_DIR/context/_state.md"
# Empty output = grill complete
```

## Per-turn operation pattern

```
1. Read extracted question (answer.sh stdout from previous turn)
2. Compose answer
3. Launch answer.sh in background:
   terminal(background=true, notify_on_complete=true, timeout=300)
4. Poll: process(action="wait", timeout=60) — repeat until exited
5. answer.sh stdout = next extracted question
   - Empty/error → PO forgot <Q> tags, read stderr for raw output
   - The orchestrator locks decisions by editing branch files
```

## PO behavioral glitches and recovery

### Missing `<Q>` tags (~40% of turns with glm-5.2)

PO writes questions as plain markdown prose. answer.sh exits 1 with raw output on stderr.

**Recovery:** Read question from stderr. The question is always identifiable — usually the last paragraph. Continue normally. Don't waste turns nagging PO about tags; it doesn't help.

### Re-asking resolved decisions

This was the primary motivation for branches. With the branch model, recovery is:
- The `[GRILL STATE]` prefix shows "Questions already asked" for the active branch
- If PO still re-asks, answer briefly: "Already asked — see the questions list above. Move forward."

### Early surrender

PO writes `<DONE>` or says "green light, ship it" after 1-2 questions.

**Recovery:** Don't accept it. Check `_state.md` — if branches are still pending, launch a fresh PO session (outer loop) or resume and push back: "You've grilled 1 of 8 branches. Keep going."

### Missing `<LOCK>` tags (100% of turns with glm-5.2)

PO never uses `<LOCK>` tags. It makes decisions in natural prose but doesn't mark them as locked.

**Recovery:** The orchestrator locks decisions manually by editing branch files. This is the expected workflow, not a glitch. See also: Shell scripting pitfalls below for answer.sh bugs related to branch file logging.

## Provider performance notes

PO uses `glm-5.2` via `zai` provider. Turn times vary wildly:
- **Fast**: launch ~2 min, resume ~60-200s. 8 questions in 45 min.
- **Slow**: resume >12 min. Provider congestion.

If a resume takes >10 min, kill and retry. Consider switching PO to deepseek (configured fallback) for speed.

## Answering with --file for long answers

```bash
answer.sh --file /dev/stdin << 'ANSWER'
Multi-paragraph answer...
ANSWER
```

## Expected depth

8-15 questions per PO session, locking 10-14 decisions across 8 branches. PO should find contradictions in locked decisions, verify claims, and push past concessions.

## Shell scripting pitfalls (learned from v0.4 E2E test)

These bugs were found in answer.sh during live testing. All are fixed in the committed code, but documenting here so they don't reappear:

1. **`bc` is not installed** on this system. Never pipe arithmetic through `bc`. Use bash arithmetic `$((...))` directly.
2. **`date` uses Thai Buddhist calendar locale** → year 2569. Always use `LC_ALL=C date -u` for timestamps.
3. **`grep -c` with `set -euo pipefail`**: when grep finds 0 matches it exits 1, which kills the script under `set -e`. Always append `|| true` and then `${VAR:-0}` to default.
4. **`sed -i` for state file updates is fragile** — multi-line content breaks the pattern. Prefer direct file writes or orchestrator-managed edits.

See `references/2026-07-21-graph-e2e-findings.md` for detailed findings from the graph-backed E2E test (v0.3) that proved tag-based protocols don't work with glm-5.2.

See `references/2026-07-21-branch-e2e-findings.md` for the v0.4 branch-based E2E test that confirmed branches solve re-asking and identified shell scripting pitfalls.

See `references/2026-07-21-v05-grill-rpc-findings.md` for the v0.5 changes: grill-rpc skill, auto-locking, no-tag fallback, auto _state.md updates.

See `references/2026-07-21-v051-live-e2e.md` for the v0.5.1 E2E test results: 9Q/20D complete grill with LOCK insertion bug fixes.

See `references/2026-07-21-v051-commit-cutoff-e2e.md` for the commit-cutoff grill: v0.5.1 complete E2E with auto-locking, grill-rpc skill, and no-tag fallback all working together.

## v0.5+ enhancements (grill-rpc skill + auto-lock + no-tag fallback)

### grill-rpc skill replaces grill-with-docs

**User directive: do NOT modify Matt Pocock's skills.** They get overwritten on updates. Instead, `shared-skills/grill-rpc/SKILL.md` contains our own grilling methodology + RPC protocol. Load it via `--skills grill-rpc`. The `<Q>` tag instruction lives in the skill (system context), not the `-z` prompt.

### Auto decision-locking

The builder locks decisions by writing `Lock D{n}: title = content` lines in their answer. answer.sh:
1. Extracts via `grep -iE 'Lock D[0-9]+:'` (no `^` anchor — indented lines must match)
2. Inserts under the `## Decisions` section in the active branch file (not appended to EOF)
3. Updates _state.md decision counts automatically

### No-tag-tolerant extraction

answer.sh tries `<Q>` tags first, then falls back to the last paragraph containing `?`. This eliminates the stderr-dump-and-exit-1 failure mode from v0.4. Works with any model grade.

### v0.5.1 bug fixes (from live E2E test)

- LOCK grep: removed `^` anchor so indented `Lock D{n}:` lines match
- LOCK insertion: writes under `## Decisions` section via temp file rewrite, not appended to EOF
- _state.md count: matches `Lock D{n}` prefix (not just `^D{n}`)

## E2E test results summary

| Version | Questions | Decisions | Contradictions found | Status |
|---------|-----------|-----------|---------------------|--------|
| v0.2 (CONTEXT.md) | 8 | 14 | 1 (rate limit math) | Complete |
| v0.4 (branches) | 9 | 15-22 | 2 (JSON vs bash, hard-block vs --no-verify) | Complete |
| v0.5 (grill-rpc) | 9 | 20 | 2 (same as v0.4) | Complete |

Key finding: branch model solved re-asking. grill-rpc skill improved protocol compliance. Auto-locking eliminated manual file editing.

## Related skills

- `self-grill` — the launcher skill (shared, global, pinned). Defines branch-based architecture.
- `peer-grill-rpc` — detailed architecture reference for builder↔PO RPC.
- `multi-agent-test-isolation` — clean-slate setup for testing cross-agent interactions.
