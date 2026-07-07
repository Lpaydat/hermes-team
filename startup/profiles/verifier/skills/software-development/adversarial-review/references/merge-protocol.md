# Merge-owner protocol

Nothing from a kanban card reaches main except through the verifier (harness-direct work stays governed by tech-lead + user approval). The failure mode this prevents is real: a production multi-agent system auto-merged failing tests because its queue trusted a reported green signal instead of executing.

One-time setup per project (add to commissioning): `bd merge-slot create` — acquire fails with "slot not found" until the slot bead exists.

```bash
bd merge-slot acquire --holder verifier --wait   # exclusive; --wait queues behind the current holder
                                                 # (plain acquire fails immediately when held)
git fetch origin && git rebase origin/main       # rebase the card branch, in the card's worktree
# conflicts? → release slot, FAIL the review: fix card to developer
#   ("rebase onto latest main and resolve conflicts") — conflict resolution is
#   code-writing, and you never write code
<run evals_cmd + FULL test suite on the rebased candidate>   # non-negotiable
# green → merge (per repo convention: merge/squash to main), push
bd merge-slot release --holder verifier          # ALWAYS release — success or failure
```

Pass `--holder verifier` explicitly — the default holder comes from `$BEADS_ACTOR`/git identity, which is the same OS user for every profile on this machine.

Post-rebase execution is the DoltHub rule: never trust a green you didn't run yourself on the exact candidate being merged. Skip bisection — serialization is the whole strategy at ≤3 concurrent developers.
