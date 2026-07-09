---
name: humanizer
description: "Synthesize QA swarm outputs into a final verdict. Read the blackboard, file findings, complete with metadata."
version: 1.0.0
disable-model-invocation: true
---

# Synthesizer — finalize the QA verdict

When loaded as the synthesizer in a QA swarm:

1. Read the root card's blackboard (comments with `[swarm:blackboard]` prefix)
2. Read all worker completion summaries via `kanban_show`
3. Synthesize all verdicts and findings
4. File Critical findings as kanban cards to `developer`
5. Complete with `kanban_complete(metadata={verdict, findings_count, claims_tested, claims_proven})`

The verdict is the gate: PASS (all claims proven, no Critical), FAIL (Critical findings), or BLOCK (blocked on fixes).
