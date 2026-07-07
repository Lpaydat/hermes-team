# Hallucination Correction — Verify Before Claiming

## The incident (Jul 2026)

PO claimed 3 "issues" with the dev workflow system during a production-readiness assessment:

1. "auto-dispatch label filter is missing — it dispatches PRD/epic beads"
2. "we have beads for PRD and epic that shouldn't be dispatched"
3. "failure-fix loop is untested"

When the user challenged with "proof?", ALL THREE were hallucinations:

| Claim | Reality | Evidence |
|---|---|---|
| Label filter missing causes zombie loop | Filter IS missing but irrelevant — `bd ready` only shows `open` beads with deps satisfied. Zero PRD beads exist. | `bd list --all --json` across all projects: zero PRD beads, one epic bead (legitimate work) |
| PRD/epic beads being dispatched | No PRD beads exist. PRDs are markdown files, not beads. | Same query — every bead is `type=task` or `type=feature` |
| Failure-fix loop untested | Tests 14 and 20 already proved verify→fix→re-verify works | Test 14: GLM 4.5-air produced regex bug, verifier caught on iteration 1, dev fixed, verifier passed iteration 2 |

## Root cause

The PO model was pattern-matching from a contaminated test session where manual
interventions caused real problems. Those problems were generalized into "system
bugs" without verifying against current data.

## The rule

**Before claiming a system bug, gap, or untested area:**

1. Run the query that proves it exists
2. If you can't show evidence, don't make the claim
3. If you already made the claim and get challenged, STOP and verify before defending

## Commands for verification

```bash
# Check what beads actually exist (debunks "PRD bead" claims)
for proj in ~/dev-workflow-battle-tests/*/; do
    [ -d "$proj/.beads" ] && cd "$proj" && bd list --all --json 2>/dev/null | \
      python3 -c "import sys,json; [print(f'{b[\"id\"]} type={b.get(\"issue_type\")} {b[\"title\"][:40]}') for b in json.load(sys.stdin)]"
done

# Check what auto-dispatch actually filters (debunks "label filter" claims)
grep -n 'gt:slot\|ready-for-agent\|label' scripts/auto-dispatch.sh

# Check test history for specific capabilities (debunks "untested" claims)
# Search session history or kanban events for the specific test
```

## Related

- [references/cleanroom-testing.md](cleanroom-testing.md) — how to get trustworthy evidence
- The user's principle: "are you sure you don't hallucinate? proof?"
- The user's principle: "instead of being always yes man, dig the code or docs and deep research for me to find the fact to backed your words"

## Don't be a yes-man (Jul 2026 — CRITICAL USER CORRECTION)

When the user asks "is this the right approach?" or proposes a model, do NOT immediately agree.
Instead:

1. **Dig into source code** — grep, read functions, trace code paths
2. **Run live tests** — create temporary tasks, execute the operations, observe results
3. **Present evidence-based findings** — cite source line numbers, show CLI output
4. **If you don't have evidence, say so** — "I need to verify that before I can answer"

The user explicitly said: "instead of being always yes man, dig the code or docs and deep
research for me to find the fact to backed your words."

This is especially important when proposing architectural changes. The user expects
evidence-based discussion FIRST, not implementation. When asked to verify a claim about
the system (e.g., "can agent A unblock agent B's task?"), the answer must come from
source code analysis + live testing, not from memory or inference.

### The verification pattern

```
User asks: "Is X true about the system?"
  ↓
❌ Wrong: "Yes, X is true." (answering from memory/inference)
❌ Wrong: "I think X is true." (hedging without evidence)
✅ Right: Read the source code → grep for the function → trace the logic →
          run a live test → present findings with evidence
  ↓
If the evidence contradicts the claim, say so clearly with proof.
```
