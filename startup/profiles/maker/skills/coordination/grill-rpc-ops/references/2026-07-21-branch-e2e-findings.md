# Branch-Based E2E Test Findings — 2026-07-21 (v0.4)

## Test 1: "too-late-to-code" CLI grill (initial, stopped early)

**Idea**: A CLI tool that tells you if it's too late to start a new coding project tonight.

**Result**: 3 questions completed across the "product" branch before stopping to fix bugs (Q_NUM, timestamp, sed). Branch structure confirmed working — PO explicitly referenced the state table and stayed on branch.

## Test 2: "too-late-to-code" CLI grill (full E2E, after bug fixes)

**Result**: COMPLETE. All 8 branches grilled through. 20 questions asked. 22 decisions locked (D1-D22). PO declared grill complete.

**Branch completion**: product (5D, 6Q) → user (3D, 4Q) → mechanism (4D, 4Q) → data (0D, merged into mechanism) → edges (2D, 2Q) → output (2D, 2Q) → deployment (2D, 2Q) → constraints (4D, 1Q).

**Key outcomes**:
- PO transitioned between branches naturally when orchestrator said "branch done"
- PO caught a real formula inconsistency (D9 said 3 inputs but D10's formula only used 2)
- PO pushed to genuine depth: unfalsifiability of the tool, mechanism of behavioral change, prep-time gap in the formula
- NO re-asking of resolved questions across 20 questions — branch system worked
- `<Q>` tag compliance ~50% (stderr fallback handled the rest)
- Orchestrator locked decisions manually (PO never used LOCK tags — 0% compliance)

## What worked

- **Branch injection**: PO saw `[GRILL STATE]` prefix with branch table + active branch questions. It explicitly said "branch: product, round 1" and "Branch 1: PRODUCT FORM" — it was reading and following the structure.
- **Re-asking prevention**: PO did NOT re-ask questions that were logged in the branch file's "Questions already asked" section.
- **Question quality**: PO found genuinely hard angles (cost currency, unfalsifiability problem, escape hatch built into the vision).
- **`<Q>` tag extraction**: worked when PO used tags (~50% compliance). Fallback to stderr worked for the other 50%.

## Bugs found and fixed

### 1. Q_NUM increment with `bc` not installed
`grep -c "^Q[0-9]" | paste -sd+ | bc` failed silently because `bc` is not installed on this system. Fix: use direct arithmetic — `Q_NUM=$(grep -c ... || true); Q_NUM=${Q_NUM:-0}; Q_NUM=$((Q_NUM + 1))`.

### 2. Timestamp locale (year 2569)
`date -u` used Thai Buddhist calendar locale → year 2569 instead of 2026. Fix: `LC_ALL=C date -u +%Y-%m-%dT%H:%M:%SZ`.

### 3. Fragile sed for _state.md updates
`sed -i "s/.../.../"` for updating question count in _state.md broke on multi-line content. Fix: removed entirely — orchestrator manages _state.md manually.

### 4. Early surrender with `<DONE>` tag (v0.3 test)
PO wrote `<DONE>` after Q1. answer.sh had a duplicate `<DONE>` check with a `<DORF>` typo that compounded the issue. Fix: removed duplicate check, single `grep -q '<DONE>'`.

## Tag compliance rate (glm-5.2 via zai)

| Tag | Compliance | Notes |
|-----|-----------|-------|
| `<Q>` | ~50% | Sometimes on launch, sometimes not. No pattern. |
| `<LOCK>` | 0% | PO never used LOCK tags across 3 E2E tests. |
| `<DONE>` | 100% when surrendering | PO uses DONE to escape early, never legitimately. |

**Conclusion**: The tag-based protocol is unreliable with glm-5.2. The orchestrator must handle all structured state. PO just outputs prose.

## What was NOT tested (still open)

- Export to SUMMARY.md via branch file concatenation (designed but not exercised in the test).
- Multiple outer-loop sessions (fresh PO session reading accumulated branch state).
- `_state.md` auto-updating decision counts — orchestrator maintained it manually during the test. The `sed` approach was removed as fragile. A helper script for branch transitions + _state.md updates would reduce orchestrator overhead.
