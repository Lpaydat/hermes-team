---
name: self-grill
description: "Relentless design grill — PO grills you via file-based RPC until the design is resolved or dead."
disable-model-invocation: true
---

# Self-grill

Launch PO to grill you on an idea. Each PO session brings fresh eyes on the accumulated design — it reads CONTEXT.md, skips resolved questions, and finds new angles. When a fresh PO session can't find anything worth asking, the design is done.

The completion criterion is PO's, not yours: `test -f "$STATE_DIR/DONE.flag"`. When you feel done — tired, conceding, wanting to build — that is the grill working. Answer the feeling as a data point for PO to push through. The valuable questions come after the point where you wanted to stop.

## How it works

PO outputs questions wrapped in `<Q>...</Q>` tags. `answer.sh` captures PO's full output, extracts ONLY the question, and prints it. PO's verbose reasoning stays in the wrapper — never enters your context. You see just the question, clean and minimal.

Three files in the state dir:
- **SESSION.key** — the real hermes session key (captured on launch, read by answer.sh)
- **CONTEXT.md** — shared decision log, read by every fresh PO session (the bridge)
- **DONE.flag** — written by PO when the design is resolved or dead

## Setup

```bash
STATE_DIR="/tmp/grill-<slug>"
mkdir -p "$STATE_DIR"
rm -f "$STATE_DIR/SESSION.key" "$STATE_DIR/DONE.flag" "$STATE_DIR/SUMMARY.md" "$STATE_DIR/CONTEXT.md"
cp "$HOME/.hermes-teams/shared-skills/self-grill/scripts/answer.sh" "$STATE_DIR/answer.sh"
chmod +x "$STATE_DIR/answer.sh"
```

## The grill — two nested loops

### Outer loop: fresh PO sessions

Repeat until a session produces too few or low-value questions:

1. Launch a fresh PO session (command below).
2. Run the inner loop (Q&A) until that session writes `DONE.flag`.
3. Assess: did this session add meaningful new questions and lock new decisions in CONTEXT.md?
   - **Yes** → start another PO session. Fresh eyes on the accumulated design.
   - **No — few questions, or the questions rehash resolved ground** → the design is done. Stop.

Leave `CONTEXT.md` across sessions — it's the bridge. Each fresh PO session reads it, skips resolved questions, and probes what previous sessions missed.

### Launch a PO session

IMPORTANT: You must capture the session key after launching. The session key appears in the output or you can get it from `hermes -p product-owner sessions list`.

```bash
# Launch PO
HERMES_GRILL_STATE_DIR="$STATE_DIR" hermes -p product-owner \
  --skills grill-with-docs \
  -z "Grill the builder on this idea via file-based RPC.
      Read \$HERMES_GRILL_STATE_DIR/CONTEXT.md first if it exists.
      Wrap EVERY question in <Q> tags like: <Q>Your question here</Q>
      Update CONTEXT.md when decisions lock.
      Write DONE.flag + SUMMARY.md when the design is resolved or dead.
      Do NOT stop at the builder's first concession — push through it. 50+ questions is normal.
      Before asking any question, check CONTEXT.md — do NOT re-ask anything already locked.
      Idea: <your idea>" \
  --cli

# After PO exits, capture its session key
hermes -p product-owner sessions list | head -2
# Copy the ID (e.g. 20260721_060823_6334fd) and save it:
echo "<session-id>" > "$STATE_DIR/SESSION.key"
```

Every session uses the same command — first or subsequent. The `-z` prompt always says "Read CONTEXT.md first if it exists." On the first run there's no CONTEXT.md; on later runs there is. PO handles both.

### Inner loop: Q&A within one session

After PO outputs Q1 and exits, iterate:

1. Send your answer: `"$STATE_DIR/answer.sh" "<your answer>"` — this blocks until PO finishes (60-200s typical).
   - Use background mode with 300s+ timeout: `terminal(background=true, notify_on_complete=true, timeout=300)`
   - Poll with `process(action='wait', timeout=60)` until it exits.
2. **answer.sh output = the extracted question** (clean, no PO reasoning). If output is empty, check `$STATE_DIR/DONE.flag`.
3. Think about the question. Reason, push back, concede honestly — answer as a real builder would.
4. Go to step 1 with your next answer.

The inner loop only ends when this session's PO writes `DONE.flag` (answer.sh returns empty). Then assess whether to start another session (outer loop).

## Timeout guidance

PO takes 60-200s per turn. Never use foreground terminal with 120s timeout — it kills the process mid-response.

Correct pattern for each answer:
```python
# Launch in background with generous timeout
terminal(background=true, notify_on_complete=true, timeout=300,
         command=f'"{STATE_DIR}/answer.sh" "{answer}"')

# Poll until done
process(action='wait', session_id=<id>, timeout=60)
# Repeat wait if still running — PO needs time
```

## Known issues

1. **PO sometimes forgets to check CONTEXT.md before asking** — it may re-ask a resolved question. When this happens, answer briefly: "Already locked — see D{N} in CONTEXT.md. Ask something new." Don't engage with the re-asked question.

2. **answer.sh fallback** — if PO doesn't use `<Q>` tags, answer.sh prints a warning to stderr and exits 1. The raw output goes to stderr too. Read it manually, extract the question, and continue. Then nudge PO in your next answer to use the tags.

3. **Session key capture** — after launching PO, you MUST save the session key to SESSION.key. Without it, answer.sh can't resume and the grill fragments across disconnected sessions.
