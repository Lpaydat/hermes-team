---
name: requesting-code-review
description: "Verify QA swarm outputs. Gate: check all workers posted results, pass or block."
version: 1.0.0
disable-model-invocation: true
---

# Verifier — gate the QA swarm

When loaded as the verifier in a QA swarm:

1. Read the root card's blackboard (comments with `[swarm:blackboard]` prefix)
2. Check that ALL workers have posted their results
3. If any worker is missing or incomplete: block with `kanban_block(reason="missing worker results")`
4. If all workers posted: complete with `kanban_complete(metadata={gate: "pass"})`
