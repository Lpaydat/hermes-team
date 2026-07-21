---
name: peer-grill-rpc
description: "Run a deep multi-turn design grill between two Hermes profiles using file-based RPC + synchronous session resume. No kanban, no kanban blocking, no polling. One profile interviews the other, maintaining CONTEXT.md across sessions, until the design is truly resolved or killed with evidence."
---

# Peer Grill RPC — deep design interviews between two agents

Use when you need one Hermes profile (e.g., product-owner) to relentlessly interview another (e.g., builder) about a plan or idea — stress-testing the design until it's either locked, killed with evidence, or hits a genuine impasse.

## Why not intercom or kanban?

The intercom + kanban block/unblock pattern (removed from all profiles 2026-07-21) had three failure modes for multi-turn interviews:

1. **Blocking `intercom ask` freezes the caller** — the caller's session hangs waiting for a synchronous reply that never comes, heartbeats stop, dispatcher kills it.
2. **Repeated `kanban_block(needs_input)` triggers `block_loop_detected`** (limit: 2) → triage escalation → auto-decomposer rewrites the card → context loss → infinite re-ask loop.
3. **Intercom message loss** when sessions died between send and receive, or the broker OOM'd (up to 4.2 GB observed).

File-based RPC + session resume avoids all three: synchronous (no polling), durable (file state), no kanban state machine (no triage).

## Architecture

```
Profile A (griller)              Profile B (builder/answerer)
     |                                    |
     |-- launch with grill-with-docs --->|
     |   skill + idea prompt             |
     |                          writes Q1 to QUESTION.md
     |                          ends turn (exits)
     |<--- process exits ----------------|
     |                                    |
     read QUESTION.md                     |
     answer via:                          |
     hermes -p <griller>                  |
       --resume <SESSION_ID>              |
       -z "<answer>" --cli                |
     |---- blocks until griller responds >|
     |                          reads answer
     |                          updates CONTEXT.md
     |                          writes Q2 to QUESTION.md
     |                          ends turn
     |<--- RPC returns -------------------|
     |                                    |
     read QUESTION.md                     |
     ... repeat until DONE.flag ...
```

**Key insight: `hermes --resume` is synchronous.** It blocks until the griller finishes its turn. When it returns, the next question is already in the file. No polling, no cron, no flags.

## Components

### State directory
```
$GRILL_STATE_DIR/ (e.g., /tmp/grill-<slug>/)
├── QUESTION.md    # current question (griller writes, builder reads)
├── CONTEXT.md     # glossary of resolved terms + locked decisions (bridges sessions)
└── DONE.flag      # created when grill is complete
```

### answer.sh helper (builder side)
```bash
#!/usr/bin/env bash
# Reads SESSION_ID from QUESTION.md, resumes griller's session with the answer.
set -euo pipefail
STATE_DIR="${GRILL_STATE_DIR:-/tmp/grill-<slug>}"
QUESTION_FILE="$STATE_DIR/QUESTION.md"
SESSION_ID=$(grep -m1 '^SESSION_ID: ' "$QUESTION_FILE" 2>/dev/null | sed 's/^SESSION_ID: //' || true)
[[ -n "${SESSION_ID:-}" ]] || { echo "ERROR: No SESSION_ID found" >&2; exit 1; }
ANSWER="${1:?Usage: answer.sh <text>}"
hermes -p product-owner --resume "$SESSION_ID" -z "$ANSWER" --cli
```

## Launching a grill

```bash
STATE_DIR=/tmp/grill-<slug>
rm -f $STATE_DIR/QUESTION.md $STATE_DIR/DONE.flag

# Launch griller (PO) with grill-with-docs + transport instructions
GRILL_STATE_DIR=$STATE_DIR hermes -p product-owner \
  --skills grill-with-docs \
  -z "Grill the builder on: <idea>.
      Read \$GRILL_STATE_DIR/CONTEXT.md first if it exists — skip resolved questions.
      Write each question to \$GRILL_STATE_DIR/QUESTION.md (SESSION_ID/QUESTION_NUM/TIMESTAMP header), then end your turn.
      The builder answers by resuming your session. Update CONTEXT.md when decisions lock.
      Don't stop at first concession." \
  --cli

# Then loop: read Q, answer via answer.sh, repeat
cat $STATE_DIR/QUESTION.md
$STATE_DIR/answer.sh "<your answer>"
# Repeat until DONE.flag appears
```

## Expected depth

Matt Pocock (author of the grilling skill) says real design grills typically need **100+ questions** to reach genuine resolution. Each PO session has a natural arc of 10-60 questions before context limits or fatigue set in — that's why session chaining via CONTEXT.md is essential for long grills.

In testing (2026-07-21), a single PO session reached **15 questions** with the anti-surrender rule active, driving to genuine existential depth (the idea was killed at Q7 in a prior attempt where PO accepted surrender; with the anti-surrender rule it pushed through to Q15 examining validation methodology, property taxonomies, and element identity resolution). Without the anti-surrender rule, grills end at 5-7 questions (first real pressure).

## Session chaining (long grills)

Each PO session has a natural arc (10-60 questions). When a session ends:
1. Launch a fresh PO session with the same `--skills grill-with-docs` + prompt.
2. The new session reads CONTEXT.md, skips resolved questions, continues the grill.
3. Decisions survive across session boundaries — no re-asking, no context loss.

CONTEXT.md is maintained by the `domain-modeling` skill (loaded via `grill-with-docs`). It's a glossary of resolved terms and locked decisions, updated inline as the grill progresses.

## The anti-surrender rule (critical for grill depth)

The answerer will try to end the grill prematurely by conceding, saying "kill it," or pivoting. **The griller must not accept surrender at face value.** Without this rule, grills end at 5-7 questions (first real pressure). With it, grills reach 15+ questions and find genuinely deep insights.

The griller should:
- **Verify the concession is genuine**: "Are you conceding because you verified the claim, or because you're tired?"
- **Stress-test pivots**: "Is X a real opportunity or a face-saving pivot?"
- **Keep pushing** until: locked design (all decisions resolved with evidence), confirmed kill (idea dead + all pivots grilled), or genuine impasse (recommend smallest experiment).

The answerer can also push the griller to continue: "Your skill says don't accept surrender at face value. You declared the grill closed but haven't grilled the build plan itself. Keep grilling."

## Known issues

### Inline-question glitch
~Every 2-3 turns, the griller writes the next question as inline reply text instead of to QUESTION.md. Detect this: after `answer.sh` returns, check if QUESTION.md was updated (compare content or mtime to before the call). If unchanged, the question is in the RPC output — extract it and write it to QUESTION.md manually, then continue the loop.

### Session chaining creates child sessions
Each `hermes --resume` creates a child session with a new ID. The SESSION_ID in QUESTION.md may point to a parent session, but resuming any session in the chain works — full context is preserved.

### `notify_on_complete=true` floods the next session
Background processes with `notify_on_complete=true` queue completion notifications. If the session ends before they're delivered, they flood the NEXT session on startup, causing it to start working immediately on stale context. For synchronous RPC calls already handled via `process action=wait`, do NOT set `notify_on_complete=true` — the wait handles completion; the notify just creates queue pollution. Clear stale background processes before ending a session.

### `set -euo pipefail` + grep = silent script death
In bash scripts with `set -euo pipefail`, `grep` returns exit code 1 on no match, which kills the script silently before any error message. Always add `|| true` and `2>/dev/null` to grep calls in set-e scripts.

## What NOT to do

- ❌ Use `intercom send` or `intercom ask` for the interview transport — intercom is removed from all profiles
- ❌ Use `kanban_block` to wait for answers
- ❌ Build a poller/cron job — `hermes --resume` is synchronous, the RPC return IS the signal
- ❌ Use `ANSWERED.flag` or mtime comparison — unnecessary with synchronous RPC
- ❌ Build a custom grill skill wrapping `grill-with-docs` — just pass transport instructions in the launch prompt (`-z`)
- ❌ Create a separate "transport" skill when a config/profile edit suffices — if a profile needs to communicate differently, edit its existing skills/config, don't build parallel infrastructure

## Design principle: config over skills

When the only thing changing is HOW an agent communicates (transport mechanism), update the agent's existing skill or config — don't create a new skill. This session went through three iterations before reaching the simplest design:
1. Built a `grill-rpc` transport skill (redundant wrapper)
2. Realized the transport instructions belong in the launch prompt, not a skill
3. Realized `venture-grill` (PO's existing grill skill) just needed to say "use files, not intercom" — then deleted it too because even that was redundant with `--skills grill-with-docs` + prompt

The final design: `--skills grill-with-docs` (Matt Pocock's proven skill, unchanged) + transport instructions in `-z` prompt + `answer.sh` helper script. Zero custom skills needed.

## References

- [`references/pitfalls.md`](references/pitfalls.md) — inline-question glitch recovery, `notify_on_complete` trap, `set -e` + grep gotcha, state dir rules
- [`references/architecture.md`](references/architecture.md) — transport design, anti-surrender rule, known issues, design principles
- [`templates/answer.sh`](templates/answer.sh) — the answer helper script
- `grill-with-docs` skill (Matt Pocock) — the interview method + CONTEXT.md maintenance
- `domain-modeling` skill — CONTEXT.md format and ADR conventions
- `self-grill` skill (shared, global) — the lean launcher that uses this architecture. **Overlap note:** `self-grill` is the user-invoked entry point (global, pinned, symlinked to all profiles); this skill is the detailed reference for the builder profile. The background curator may consolidate them.
