# Grill Launch Recipes

## Standard grill (builder answers, PO grills)

```bash
STATE_DIR=~//tmp/grill-rpc
GRILL_PROFILE=product-owner

# Clear state (fresh grill)
rm -f $STATE_DIR/QUESTION.md $STATE_DIR/DONE.flag $STATE_DIR/SUMMARY.md

# Launch griller
GRILL_STATE_DIR=$STATE_DIR hermes -p $GRILL_PROFILE \
  --skills grill-with-docs \
  -z "Grill the builder on: <idea>.
      Read \$GRILL_STATE_DIR/CONTEXT.md first if it exists — skip resolved questions.
      Write each question to \$GRILL_STATE_DIR/QUESTION.md (SESSION_ID/QUESTION_NUM/TIMESTAMP header), then end your turn.
      The builder answers by resuming your session. Update CONTEXT.md when decisions lock.
      Don't stop at first concession — grill until locked design, confirmed kill, or genuine impasse." \
  --cli

# Answer loop
cat $STATE_DIR/QUESTION.md                    # read the question
GRILL_STATE_DIR=$STATE_DIR GRILL_PROFILE=$GRILL_PROFILE \
  <skill_dir>/templates/answer.sh "<answer>"  # send answer (blocks until next Q)
# Repeat until DONE.flag appears
```

## Continuing a grill across sessions (session chaining)

When a PO session reaches its natural end (context limit, declares done), launch fresh:

```bash
# CONTEXT.md already exists from previous session — PO reads it and continues
GRILL_STATE_DIR=$STATE_DIR hermes -p $GRILL_PROFILE \
  --skills grill-with-docs \
  -z "Continue grilling the builder. Read \$GRILL_STATE_DIR/CONTEXT.md FIRST — it has all resolved decisions from previous sessions. Do not re-ask resolved questions. Write each question to \$GRILL_STATE_DIR/QUESTION.md, end your turn. Don't stop at first concession." \
  --cli
```

## Recovering from the inline-question glitch

~Every 2-3 turns, the griller writes the question as inline reply text instead of to QUESTION.md. The RPC output contains it. Recover:

```bash
# The question is in the answer.sh output — extract it and write to file manually:
cat > $STATE_DIR/QUESTION.md << 'EOF'
SESSION_ID: <session_id_from_file>
QUESTION_NUM: <N+1>
TIMESTAMP: <ISO>

---
<paste question from RPC output>
EOF
```

## Cleaning up after a grill

```bash
# Stop any running griller processes
pkill -f "hermes.*$GRILL_PROFILE.*--skills grill-with-docs"

# Archive state (keep CONTEXT.md for reference)
mv $STATE_DIR/QUESTION.md $STATE_DIR/QUESTION.md.archived 2>/dev/null
touch $STATE_DIR/DONE.flag

# Clean test sessions from griller profile
hermes -p $GRILL_PROFILE sessions prune --newer-than 1h --yes
```
