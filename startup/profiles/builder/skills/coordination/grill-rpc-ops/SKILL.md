---
name: grill-rpc-ops
description: "Operational playbook for running grill RPC sessions (builder↔PO design interviews via file-based RPC). Covers timeout management, session-key capture, and recovery from PO behavioral glitches. Load when running or debugging a self-grill or peer-grill-rpc session."
version: 2.0.0
metadata:
  hermes:
    tags: [coordination, grill, rpc, debugging, operations]
    category: coordination
---

# Grill RPC Ops — running grill sessions that don't fall over

The grill skills (`self-grill`, `peer-grill-rpc`) define the architecture. This skill covers what actually happens when you run a full grill end-to-end: the timeouts you need, the session-key capture step, and the PO behavioral glitches you'll hit every session.

Load this BEFORE launching a grill.

## What changed in v2 (graph-backed)

v1 used CONTEXT.md for decision state — PO wrote decisions to a file that grew to 12KB+. v2 replaces CONTEXT.md with the graph DB:

- **Decisions** are graph nodes (created by answer.sh extracting `<LOCK>` tags)
- **State** is queried via `graph_state.py status` — returns one-liner: `[STATE: LOCKED(N): ... | OPEN(M): ...]`
- **Done check** is `graph_state.py is-done` — mechanical, not subjective
- **Export** is `graph_state.py export` — dumps all decisions for SUMMARY.md
- PO never writes files. PO outputs tags. The wrapper handles state.

## Pre-flight checklist

1. **State dir:** `/tmp/grill-<slug>/` with `answer.sh` + `graph_state.py` copied in and chmod +x
2. **TOPIC file:** `echo "grill-<slug>" > $STATE_DIR/TOPIC`
3. **Graph init:** `python3 graph_state.py init <topic> "<idea>"`
4. **Timeout plan:** Every `answer.sh` call runs in background with timeout=300+

## The session-key capture step

**This is the #1 cause of silent grill degradation.** PO cannot reliably self-report its session key.

After launching PO:
```bash
hermes -p product-owner sessions list | grep "cli" | head -1 | awk '{print $NF}'
# Save it:
echo "<session-id>" > "$STATE_DIR/SESSION.key"
```

## Per-turn operation pattern

Each answer cycle:

```
1. Read extracted question (answer.sh stdout from previous turn)
2. Compose answer
3. Launch answer.sh in background:
   terminal(background=true, command="answer.sh '...' 2>&1",
            notify_on_complete=true, timeout=300)
4. Poll: process(action="wait", timeout=60) — repeat until exited
5. answer.sh stdout = next extracted question
   - Empty stdout → check graph_state.py is-done
   - answer.sh exit 1 → PO forgot <Q> tags, read stderr for raw output
```

answer.sh does three things per turn:
1. Injects `[STATE: LOCKED(N): ... | OPEN(M): ...]` prefix before your answer
2. Captures PO output, extracts `<Q>`, `<LOCK>`, `<DONE>` tags
3. Writes LOCKs to graph DB automatically

**Never use 120s timeout** — PO takes 60-200s per turn.

## Checking grill state

```bash
# What's locked and open (one-liner)
python3 graph_state.py status <topic>

# Is the grill done?
python3 graph_state.py is-done <topic> && echo "DONE" || echo "still open"

# Full export for SUMMARY.md
python3 graph_state.py export <topic> > SUMMARY.md
```

## PO behavioral glitches and recovery

### Missing `<Q>` tags (~40% of turns)

PO forgets to wrap its question in `<Q>...</Q>`. answer.sh exits 1 with raw output on stderr.

**Recovery:** Read question from stderr. Include in next answer: "Wrap your next question in `<Q>` tags."

### Re-asking resolved decisions

The `[STATE]` prefix shows what's locked. If PO still re-asks:

```
"Already locked — see [STATE] above. D5 is resolved. Ask something new."
```

### Early surrender

PO writes `<DONE>` after 1-2 questions. The grill is not actually done.

**Recovery:** Don't run `graph_state.py done`. Instead check: are there open questions? Is decision coverage complete across categories? If not, launch a fresh PO session (outer loop) instead of accepting the surrender.

### Missing `<LOCK>` tags

PO makes a decision but doesn't wrap it in `<LOCK>` tags. The decision doesn't get written to the graph.

**Recovery:** Manually lock it:
```bash
python3 graph_state.py lock <topic> "D5: Generation method" "deterministic templates"
```

## Provider performance notes

PO uses `glm-5.2` via `zai` provider. Turn times vary wildly:
- **Fast session**: launch ~20s, resume ~60-200s
- **Slow session**: resume >12 min. Provider congestion.

If a resume takes >10 min, kill and retry.

## Answering with --file for long answers

```bash
answer.sh --file /dev/stdin << 'ANSWER'
Multi-paragraph answer...
ANSWER
```

## Expected depth

A productive grill reaches 8-15 questions per session, locking 10-14 decisions. Categories that should have at least one locked decision before declaring done:

1. Product form — what is it
2. User — who's it for
3. Core mechanism — how does it work
4. Data/inputs — what goes in
5. Edge cases — what breaks
6. Output/share — what comes out
7. Deployment — where does it run
8. Constraints — rate limits, cost, scale

## Related skills

- `self-grill` — the launcher skill (shared, global, pinned)
- `peer-grill-rpc` — architecture reference for builder↔PO RPC
- `multi-agent-test-isolation` — clean-slate setup for testing
