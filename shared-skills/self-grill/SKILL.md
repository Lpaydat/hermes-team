---
name: self-grill
description: "Relentless design grill — PO grills you via file-based RPC until the design is resolved or dead."
disable-model-invocation: true
---

# Self-grill

Launch PO to grill you on an idea. PO asks questions, you answer, PO locks decisions via `<LOCK>` tags. The wrapper (`answer.sh`) extracts decisions and writes them to a graph DB — no CONTEXT.md file. PO sees current state via a `[STATE: ...]` prefix injected before each answer.

The grill is done when PO writes `<DONE>` or when you (the orchestrator) decide the design is complete.

## How it works

```
answer.sh flow (per turn):
1. Read [STATE] from graph DB → prepend to answer
2. Resume PO with "[STATE: LOCKED(N): ... | OPEN(M): ...]\n\n<your answer>"
3. Capture PO output
4. Extract <LOCK> tags → write decisions to graph DB
5. Extract <Q> tag → print clean question to stdout
6. If <DONE> tag → mark grill root resolved
```

PO never writes files. PO never calls graph tools. PO just outputs structured tags and the wrapper handles everything.

Three files in state dir:
- **SESSION.key** — real hermes session key (captured on launch)
- **TOPIC** — graph topic tag for this grill (e.g. `grill-github-sentence`)
- **answer.sh** + **graph_state.py** — the scripts (copied from shared-skills)

No CONTEXT.md. No DONE.flag. The graph DB is the single source of truth.

## Setup

```bash
STATE_DIR="/tmp/grill-<slug>"
TOPIC="grill-<slug>"
mkdir -p "$STATE_DIR"
rm -f "$STATE_DIR/SESSION.key" "$STATE_DIR/TOPIC"
cp "$HOME/.hermes-teams/shared-skills/self-grill/scripts/answer.sh" "$STATE_DIR/answer.sh"
cp "$HOME/.hermes-teams/shared-skills/self-grill/scripts/graph_state.py" "$STATE_DIR/graph_state.py"
chmod +x "$STATE_DIR/answer.sh"
echo "$TOPIC" > "$STATE_DIR/TOPIC"

# Initialize grill root in graph DB
python3 "$STATE_DIR/graph_state.py" init "$TOPIC" "<your idea>"
```

## The grill — two nested loops

### Outer loop: fresh PO sessions

Repeat until a session produces too few or low-value questions:

1. Launch a fresh PO session (command below).
2. Run the inner loop (Q&A) until PO writes `<DONE>`.
3. Assess: did this session add meaningful new questions and lock new decisions?
   - **Yes** → start another PO session. Fresh eyes on the accumulated design.
   - **No** → the design is done. Stop.
4. To assess, check the graph state:
   ```bash
   python3 "$STATE_DIR/graph_state.py" status "$TOPIC"
   python3 "$STATE_DIR/graph_state.py" is-done "$TOPIC" && echo "DONE" || echo "still open"
   ```

### Launch a PO session

```bash
HERMES_GRILL_STATE_DIR="$STATE_DIR" \
HERMES_GRILL_TOPIC="$TOPIC" \
hermes -p product-owner \
  --skills grill-with-docs \
  -z "Grill the builder on this idea via file-based RPC.
      You will see a [STATE: ...] prefix before each answer showing what's LOCKED and OPEN.
      Do NOT re-ask anything in LOCKED.
      Wrap EVERY question in <Q> tags: <Q>Your question here</Q>
      Wrap EVERY locked decision in <LOCK> tags: <LOCK title=\"D1: Product form\">Disposable generator</LOCK>
      Write <DONE> when the design is fully resolved (all categories covered, no open questions).
      Do NOT stop at the builder's first concession — push through it. 50+ questions is normal.
      Idea: <your idea>" \
  --cli

# After PO exits, capture its session key
hermes -p product-owner sessions list | grep "cli" | head -1 | awk '{print $NF}'
# Save it:
echo "<session-id>" > "$STATE_DIR/SESSION.key"
```

### Inner loop: Q&A within one session

After PO outputs Q1 and exits, iterate:

1. Read the extracted question (from answer.sh stdout).
2. Think about it. Reason, push back, concede honestly.
3. Send your answer:
   ```bash
   HERMES_GRILL_STATE_DIR="$STATE_DIR" \
   HERMES_GRILL_TOPIC="$TOPIC" \
   "$STATE_DIR/answer.sh" "<your answer>"
   ```
   Use background mode with 300s+ timeout:
   ```
   terminal(background=true, notify_on_complete=true, timeout=300)
   process(action='wait', timeout=60)  # repeat until exited
   ```
4. answer.sh stdout = the next extracted question. If empty → check `is-done`.
5. Go to step 1.

## Tag format reference

PO uses these tags (wrapper extracts them, PO never writes files):

| Tag | Format | Extracted by | Purpose |
|-----|--------|-------------|---------|
| `<Q>` | `<Q>question text</Q>` | answer.sh → stdout | The next question (clean, no reasoning) |
| `<LOCK>` | `<LOCK title="D1: Title">content</LOCK>` | answer.sh → graph DB | A locked decision |
| `<DONE>` | `<DONE>` | answer.sh → graph root resolved | Grill complete signal |

## When the grill is done

```bash
# Verify completion
python3 "$STATE_DIR/graph_state.py" is-done "$TOPIC" && echo "COMPLETE"

# Export to SUMMARY.md
python3 "$STATE_DIR/graph_state.py" export "$TOPIC" > "$STATE_DIR/SUMMARY.md"

# View all decisions
python3 "$STATE_DIR/graph_state.py" status "$TOPIC"
```

## Timeout guidance

PO takes 60-200s per turn. Never use foreground terminal with 120s timeout.

Correct pattern:
```python
terminal(background=true, notify_on_complete=true, timeout=300,
         command=f'HERMES_GRILL_STATE_DIR="{STATE_DIR}" HERMES_GRILL_TOPIC="{TOPIC}" "{STATE_DIR}/answer.sh" "{answer}"')
process(action='wait', session_id=<id>, timeout=60)
# Repeat wait if still running
```

## Known issues

1. **PO sometimes ignores tags** — if answer.sh exits 1 with "no <Q> tags", read stderr for the raw output. Extract the question manually and continue.

2. **PO re-asks resolved decisions** — the [STATE] prefix shows what's locked. If PO still re-asks, answer briefly: "Already locked — see [STATE]. Ask something new."

3. **Session key capture** — after launching PO, you MUST save the session key to SESSION.key. Without it, answer.sh can't resume.
