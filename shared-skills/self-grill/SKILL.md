---
name: self-grill
description: "Relentless design grill — PO grills you via file-based RPC until the design is resolved or dead."
disable-model-invocation: true
---

# Self-grill

Launch PO to grill you on an idea. Each PO session brings fresh eyes on the accumulated design — it reads CONTEXT.md, skips resolved questions, and finds new angles. When a fresh PO session can't find anything worth asking, the design is done.

The completion criterion is PO's, not yours: `test -f "$STATE_DIR/DONE.flag"`. When you feel done — tired, conceding, wanting to build — that is the grill working. Answer the feeling as a data point for PO to push through. The valuable questions come after the point where you wanted to stop.

## Setup

```bash
STATE_DIR="/tmp/grill-<slug>"
mkdir -p "$STATE_DIR"
rm -f "$STATE_DIR/QUESTION.md" "$STATE_DIR/DONE.flag" "$STATE_DIR/SUMMARY.md"
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

```bash
HERMES_GRILL_STATE_DIR="$STATE_DIR" hermes -p product-owner \
  --skills grill-with-docs \
  -z "Grill the builder on this idea via file-based RPC.
      Read \$HERMES_GRILL_STATE_DIR/CONTEXT.md first if it exists.
      Write each question to QUESTION.md (SESSION_ID / QUESTION_NUM / TIMESTAMP header), then end your turn.
      Update CONTEXT.md when decisions lock. Write DONE.flag + SUMMARY.md when the design is resolved or dead.
      Do NOT stop at the builder's first concession — push through it. 50+ questions is normal.
      Idea: <your idea>" \
  --cli
```

Every session uses the same command — first or subsequent. The `-z` prompt always says "Read CONTEXT.md first if it exists." On the first run there's no CONTEXT.md; on later runs there is. PO handles both.

### Inner loop: Q&A within one session

After PO writes Q1 and exits, iterate:

1. Read `QUESTION.md` — it contains the current question.
2. Think about it. Reason, push back, concede honestly — answer as a real builder would.
3. Send your answer: `"$STATE_DIR/answer.sh" "<your answer>"` — blocks until PO finishes.
4. Check: `test -f "$STATE_DIR/DONE.flag"` — if present, this session is over. Return to the outer loop.
5. If absent, `QUESTION.md` now has the next question. Go to step 1.

The inner loop only ends when this session's PO writes `DONE.flag`. Then assess whether to start another session (outer loop).
