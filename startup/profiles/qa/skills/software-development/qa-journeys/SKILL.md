---
name: qa-journeys
description: "Use when walking end-to-end user journeys against a running artifact. Tests that a real user can actually accomplish their goal, not just that individual features work. Posts journey verdicts to the swarm blackboard. Loaded by the journeys worker in a QA swarm."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [qa, journeys, e2e, user-flow, persona]
    related_skills: [qa-protocol]
---

# QA Journeys — walk the user's path end-to-end

Claims verify features in isolation. Journeys verify a user can actually accomplish a goal end-to-end. Individual claims can all pass while the flow breaks — session lost between steps, state not carried, dead-end after success.

## Read your assignment

Your card body contains:
- The journeys to walk (1-3 per persona, from the orchestrator's plan)
- The container image tag and port (or workspace path)

## Execute each journey as a real user would

- **Webapp:** click through the UI using `browser_navigate`, `browser_click`, `browser_type`, `browser_snapshot`, `browser_vision`
- **API:** call the endpoint sequence using `curl` or `requests`, passing tokens/state between calls
- **CLI:** pipe commands in sequence, passing output between steps

For each journey:
1. Start from a clean state (fresh container or reset)
2. Execute each step as a user would
3. Verify the expected outcome at each step
4. If any step fails, the journey is _disproven_ — the broken flow is the finding

## Journey verdicts

A journey that can't be completed gets a _disproven_ verdict **even if every component claim passed** — the flow itself is broken. This is the key value of journey testing: it catches integration bugs that claim testing misses.

| Verdict | Meaning |
|---|---|
| _proven_ | All steps completed, expected outcome at each step |
| _disproven_ | Flow broke at step N — file finding with the step that failed |
| _untested_ | Couldn't test (missing dependency, environment limitation) |

## What to look for

- **Session state:** is the user still logged in between steps? Is cart state preserved?
- **Redirects:** does step 2 land on the right page after step 1?
- **Data carryover:** does the data created in step 1 appear in step 2?
- **Error recovery:** if step 2 fails, can the user recover and continue?
- **Dead ends:** does a successful action leave the user stuck with no next step?
- **Concurrent users:** if two users run the same journey simultaneously, do they interfere?

## Evidence

For each journey, capture:
- The step-by-step sequence (API calls, clicks, commands)
- The outcome at each step (HTTP response, screenshot, output)
- Where it broke (if it did)

## Post results to blackboard

```bash
hermes kanban comment <root_card_id> --author qa-journeys \
  --body '[swarm:blackboard] {"key": "journey_results", "value": {"admin_flow": {"verdict": "proven", "steps": 5}, "user_signup": {"verdict": "disproven", "broken_at_step": 3, "evidence": "..."}}}'
```

## Complete with metadata

```python
kanban_complete(
    summary="Journeys: 3 tested, 2 proven, 1 disproven (signup breaks at email verification)",
    metadata={
        "journeys": [{"name": "admin_flow", "verdict": "proven"}, ...],
        "findings": [{"severity": "P1", "journey": "user_signup", "broken_at": "step 3"}]
    }
)
```
