# QA Orchestration Research — Condensed Findings

Grounding for the QA protocol design. Consult when justifying the protocol's shape or deciding whether to adjust the workflow.

## Big tech QA patterns (Google, Meta, Netflix, Amazon, Microsoft, Spotify)

Five universal patterns every company converges on:

1. **Developers own testing.** The dedicated "throw over wall to QA" role was dissolved everywhere. Developers own unit/integration. QA's surviving value is exploratory + testability review + verdict.
2. **Test pyramid is backbone.** Google's small/medium/large size taxonomy (~70/20/10 split). QA works at the medium+large level against the assembled system.
3. **QA = advocacy + exploratory + tooling.** Not manual script execution. The QA agent's phases 4-6 (journeys, non-functional smoke, explore) hit this exact value.
4. **Testing intensifies post-release.** Canaries, feature flags, shadow/dark launches (Meta), chaos in prod (Netflix). The QA agent = the "ring-1 / staging assembled-system" band.
5. **Automated CI gates replaced human sign-off.** Fix→retest is universally automated. The QA verdict IS the gate.

### Severity system (Google P0-P4, adopted)
- P0: launch blocker / data loss / security hole
- P1: major journey broken, no workaround
- P2: journey broken, workaround exists
- P3: minor / cosmetic
- P4: suggestion / nice-to-have

### Testability review at design time (Google TE pattern)
The highest-leverage QA-survivor skill: flag design decisions that made testing hard, fed back to tech-lead. Encoded in the QA protocol's Step 5 (verdict) as "testability feedback."

## Hermes platform orchestration mechanisms

### `hermes kanban swarm` CLI (platform-native)
Creates: root card (blackboard) + parallel worker cards + verifier + synthesizer. Each worker can have specific skills loaded via `--worker PROFILE:TITLE[:SKILL,SKILL]`. Workers post structured JSON to root card comments (blackboard pattern). Verifier gates. Synthesizer reads all and completes.

### `kanban_delegate` plugin (tech-lead only)
Profile-scoped plugin at `tech-lead/plugins/dev_workflow/`. Atomically creates dev+verifier cards, links caller as dependent, blocks with kind=dependency. NOT available to other profiles. QA uses `hermes kanban swarm` CLI instead.

### Blackboard pattern
Workers post structured JSON to root card: `[swarm:blackboard] {"key": "verdicts", "value": {...}}`. The `latest_blackboard()` function merges all comments. This is the evidence-flow mechanism — no ~/vault/ needed.

### `max_in_progress_per_profile` constraint
Global dispatcher setting (root `~/.hermes/config.yaml`). Caps each profile to N concurrent tasks. If all swarm workers are `assignee=qa`, they execute serially unless the cap is raised. Configurable — the user confirmed they can change it.

### delegate_task fragility
Ephemeral, dies with session, shares parent's API rate limits. Under sustained load (3+ subagents), frequently hits HTTP 429 and fails silently. Recovery: check `state.db` for sessions with 1 message + 0 tool_calls + no end_reason = stuck. Kill sandbox, re-dispatch or do it yourself.

## QA vs verifier boundary

| | Verifier (pre-merge) | QA (post-merge) |
|---|---|---|
| Operates on | The diff (code-level) | The running artifact (system-level) |
| Core question | "Is this code correct and safe to merge?" | "Does the assembled thing work for a user?" |
| Evidence | Unit tests, lint, mutation testing | Live output, HTTP responses, screenshots |
| Finds | "This function doesn't handle None" | "The signup flow crashes on emoji names" |

They don't overlap. Verifier proves code is built right. QA proves the right thing was built and survives contact with reality.

## Testing landscape — 36 edge case categories

Original 10 (universal) + 14 expanded (type-specific) + 12 security/distributed (in qa-security and qa-exploratory skills). Full taxonomy in `references/testing-landscape.md` in the `live-testing` skill directory.

## Risk-based planning

Risk = likelihood (complexity × novelty × change volume) × impact (data loss × security × revenue × user-facing). High-risk claims get full depth (10+ edge cases). Low-risk get smoke only. Most predictable planning methodology for an AI agent — the ranking is algorithmic and reproducible.
