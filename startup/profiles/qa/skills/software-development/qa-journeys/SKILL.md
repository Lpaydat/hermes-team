---
name: qa-journeys
description: "Use when walking end-to-end user journeys against a running artifact. Tests that a user can accomplish their goal, not just that individual features work. Posts journey verdicts to the swarm blackboard."
version: 1.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [qa, journeys, e2e, user-flow, persona]
    related_skills: [qa-protocol]
---

# QA Journeys — walk the user's path

A **journey** is a multi-step user flow: sign up → create project → invite teammate → teammate sees project. Individual claims can all pass while the flow breaks — session lost between steps, state not carried, dead-end after success.

## Read your assignment

Your card body contains the journeys to walk (1–3 per persona) and the container image tag and port or workspace path.

## Execute each journey as a real user

- **Webapp:** click through the UI using `browser_navigate`, `browser_click`, `browser_type`, `browser_snapshot`, `browser_vision`
- **API:** call the endpoint sequence with `curl`, passing tokens/state between calls
- **CLI:** pipe commands in sequence, passing output between steps

For each journey:
1. Start from a clean state (fresh container or reset)
2. Execute each step as a user would
3. Verify the expected outcome at each step
4. If any step fails, the journey is _disproven_ — the broken flow is the finding

A journey that can't be completed gets _disproven_ **even if every component claim passed**. The broken flow is the finding.

## What to look for

- **Session state:** still logged in between steps? Cart state preserved?
- **Redirects:** does step 2 land on the right page after step 1?
- **Data carryover:** does data created in step 1 appear in step 2?
- **Error recovery:** if step 2 fails, can the user recover and continue?
- **Dead ends:** does a successful action leave the user stuck?
- **Concurrent users:** do two users running the same journey interfere?

## Post results to blackboard

```bash
hermes kanban comment <root_card_id> --author qa-journeys \
  --body '[swarm:blackboard] {"key": "journey_results", "value": {"admin_flow": {"verdict": "proven", "steps": 5}, "user_signup": {"verdict": "disproven", "broken_at_step": 3, "evidence": "..."}}}'
```

Complete with `kanban_complete(metadata={journeys: [...], findings: [...]})`.

For each journey, capture the step-by-step sequence, the outcome at each step (HTTP response, screenshot, output), and where it broke if it did.
