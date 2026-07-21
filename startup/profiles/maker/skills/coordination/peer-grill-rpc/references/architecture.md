# Grill RPC Architecture — deep reference

The transport mechanism, design principles, and lessons learned from building the file-based RPC grill loop.

## Why not intercom or kanban?

The intercom + kanban block/unblock pattern (removed from all profiles 2026-07-21) had three failure modes for multi-turn interviews:

1. **Blocking `intercom ask` freezes the caller** — the caller's session hangs waiting for a synchronous reply that never comes, heartbeats stop, dispatcher kills it.
2. **Repeated `kanban_block(needs_input)` triggers `block_loop_detected`** (limit: 2) → triage escalation → auto-decomposer rewrites the card → context loss → infinite re-ask loop.
3. **Intercom message loss** when sessions died between send and receive, or the broker OOM'd (up to 4.2 GB observed).

File-based RPC + session resume avoids all three: synchronous (no polling), durable (file state), no kanban state machine (no triage).

## Architecture

```
Profile A (griller)              Profile B (answerer)
     |                                    |
     |-- launch with grill-with-docs --->|
     |                          writes Q1 to QUESTION.md
     |                          ends turn (exits)
     |<--- process exits ----------------|
     read QUESTION.md                     |
     answer via hermes --resume           |
     |---- blocks until griller responds>|
     |                          reads answer, updates CONTEXT.md
     |                          writes Q2, ends turn
     |<--- RPC returns -------------------|
     ... repeat until DONE.flag ...
```

**Key insight: `hermes --resume` is synchronous.** It blocks until the griller finishes its turn. No polling needed.

## The anti-surrender rule (critical for grill depth)

The answerer will try to end the grill prematurely by conceding, saying "kill it," or pivoting. **The griller must not accept surrender at face value.** Without this rule, grills end at 5-7 questions. With it, grills reach 15+ questions.

- **Verify the concession**: "Are you conceding because you verified the claim, or because you're tired?"
- **Stress-test pivots**: "Is X a real opportunity or a face-saving pivot?"
- **Keep pushing** until: locked design, confirmed kill (all pivots grilled), or genuine impasse.

The answerer can also push the griller to continue: "Your skill says don't accept surrender. Keep grilling."

## Expected depth

Matt Pocock says real design grills need **100+ questions**. Each PO session has a natural arc of 10-60 questions — session chaining via CONTEXT.md is essential.

## Known issues

### Inline-question glitch
~Every 2-3 turns, the griller writes the next question as inline reply text instead of to QUESTION.md. Detect this: after `answer.sh` returns, check if QUESTION.md was updated. If unchanged, extract the question from the RPC output and write it manually.

### Session chaining creates child sessions
Each `hermes --resume` creates a child session with a new ID. The SESSION_ID in QUESTION.md may be stale, but resuming any session in the chain works.

### `notify_on_complete=true` floods the next session
Background processes with `notify_on_complete=true` queue completion notifications that flood the next session on startup. For synchronous RPC calls handled via `process action=wait`, do NOT set `notify_on_complete=true`.

### `set -euo pipefail` + grep = silent script death
In bash scripts with `set -euo pipefail`, `grep` returns exit code 1 on no match, killing the script silently. Always add `|| true` and `2>/dev/null` to grep calls.

## State directory location

Use `/tmp/grill-<slug>/` for grill state — NOT `~/vault/ventures/` (which is a knowledge base, not a working directory).

## Design principle: config over skills

Transport instructions belong in the launch prompt (`-z`), not a separate skill. Iterations:
1. Built a `grill-rpc` transport skill → redundant wrapper, deleted
2. Updated PO's `venture-grill` to say "use files not intercom" → still redundant, deleted
3. Final: `--skills grill-with-docs` + transport instructions in `-z` prompt + `answer.sh`
