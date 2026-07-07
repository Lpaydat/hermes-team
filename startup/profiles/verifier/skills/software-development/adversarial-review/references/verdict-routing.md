# Verdict routing — FAIL, PASS, ESCALATE

## FAIL — create fix card and iterate

1. Comment findings on the DEVELOPER card, with a structured header line — `REVIEW-ITERATION: <N>` — followed by findings: per finding, severity, file:line, evidence, the contract item violated. Cards have NO mutable metadata field — **this comment line IS the iteration counter**; the chain of review cards is the fallback count.

2. Create a fix card:
   ```
   kanban_create(
     assignee="developer",
     parents=[<your review card>],
     workspace_kind="dir",
     workspace_path=<the developer's worktree_path from parent metadata>,
     body="Review-Iteration: <N+1>, Chain-Root: <original developer card id>, 
           Resume-Session: <harness_session_id>, Branch: <branch_name>, 
           Worktree: <worktree_path>, <pointer to findings comment>, 
           <same contract_ref/evals_cmd>"
   )
   ```
   The explicit workspace_path makes the developer's warm resume reachable — resume is cwd-scoped, and a fresh worktree would orphan the session.

3. Create a fresh review card as the fix card's child (body: contract_ref, evals_cmd, base SHA + branch; the new head arrives automatically via the fix card's completion metadata when it promotes).

4. Complete your review card with verdict=fail summary.

## PASS — merge

Zero Critical/Important findings, every contract item checked, every AC verified, subjective axes ≥ 0.7 where applicable. Proceed to [merge-protocol.md](merge-protocol.md). After merging, `kanban_complete` with the review summary; the completion boundary closes the bead (kanban→beads writeback — you are the completion boundary).

## ESCALATE — never loop

Two escalation triggers, both route to tech-lead:

**Iteration cap**: `REVIEW-ITERATION ≥ 3` (count the header lines on the developer-card thread, or the review cards in the chain). Block your own review card `needs_input` (you cannot block a foreign card — the ownership guard rejects it, and the developer card is already done). Create a tech-lead escalation card via `kanban_create` linking the chain root + all review cards. Tech-lead reads accumulated comments, then the trace ledger (trace-first), and re-contracts, switches harness, or abandons.

**Spec gap**: code matches the contract but the contract is wrong. Block for tech-lead immediately. If it's contract-vs-INTENT (the bead itself promises the wrong thing), note that: tech-lead routes it to product-owner, who owns bead content. You never re-contract anyone, never amend a bead, never edit a contract.
