# Pitfalls — grill RPC operations

## Inline-question glitch

~Every 2-3 turns, PO writes the next question as inline reply text in the RPC output instead of to QUESTION.md.

**Detection:** After `answer.sh` returns, check if QUESTION.md content changed. If it still shows the question you just answered, the next question is in the RPC output.

**Recovery:** Extract the question from the RPC output, write it to QUESTION.md with the correct header format (SESSION_ID / QUESTION_NUM / TIMESTAMP), then continue the loop.

## `notify_on_complete` floods the next session

Do NOT use `notify_on_complete=true` when launching PO sessions or answer.sh as background processes. Completion notifications queue and flood the NEXT session on startup, causing it to start working immediately on stale context.

Use `terminal(background=true)` without `notify_on_complete` (defaults false). Handle completion via `process action=wait` synchronously.

## `set -euo pipefail` + grep = silent script death

In bash scripts with `set -euo pipefail`, `grep` returns exit code 1 on no match, killing the script silently before error messages. Always add `|| true` and `2>/dev/null` to grep calls in set-e scripts.

## State directory

Use `/tmp/grill-<slug>/` — NOT `~/vault/ventures/` (which is a knowledge base, not a working directory). This has been corrected multiple times; do not regress.
