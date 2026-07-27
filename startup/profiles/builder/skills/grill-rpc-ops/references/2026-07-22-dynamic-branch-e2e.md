# Dynamic Branch E2E Test Results — v0.7.1

**Test date:** 2026-07-22
**Idea tested:** "git commit-blocker that warns when you're coding too late"
**PO model:** glm-5.2 (zai)
**Result:** Grill completed end-to-end

## Key Fixes Applied During Test

### Bug 1: Branch Name Normalization
- **Symptom:** answer.sh can't resolve active branch file
- **Root cause:** add_branch.sh creates "product form" → `product-form.md` (spaces→hyphens) but answer.sh used raw name without slug conversion
- **Fix:** answer.sh now converts spaces to hyphens: `echo "$ACTIVE_BRANCH" | tr ' ' '-' | tr '[:upper:]' '[:lower:]'`

### Bug 2: Dynamic State Update
- **Symptom:** _state.md decision counts not updating
- **Root cause:** answer.sh had hardcoded `update_state 1 product / update_state 2 user / ...` calls from v0.4. Dynamic branches have no fixed numbering.
- **Fix:** Replaced with loop that reads _state.md rows dynamically: `while IFS='|' read -r _num _name ...; do ... done < <(grep '^| [0-9]' "$STATE_FILE")`

### Bug 3: Question Extraction Failure
- **Symptom:** When PO doesn't use `<Q>` tags, fallback grabs fragments instead of questions
- **Root cause:** Fallback regex too fragile for multi-paragraph PO output with embedded `?`
- **Mitigation:** `<Q>` tag compliance improved with grill-rpc skill in system context. Fallback remains as belt-and-suspenders.

## What Worked

- Dynamic branching: 4 branches emerged (product form, user profile, edge cases, deployment) — not the 8 hardcoded ones
- Auto-lock: decisions written to branch files automatically
- Branch transitions: PO didn't re-ask resolved questions
- `<Q>` tag compliance: improved with grill-rpc skill (system context > launch prompt)
- State injection: PO read [GRILL STATE] and referenced branch structure

## Grill Quality

PO caught real design contradictions:
1. "JSON config" vs "zero dependencies" (was planning JSON parse but claimed zero deps)
2. "Hard block" vs "--no-verify accepted" (git hooks can always be bypassed)

Both led to design revisions — exactly what the grill is for.
