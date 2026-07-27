# Grill Depth Regression — Root Cause Analysis

**Date:** 2026-07-24
**Symptom:** E2E test #2 (ai-pen-testing-service) produced only 12 decisions across 6 branches (2 per branch). The original self-grill (commit ec521103, using single CONTEXT.md) produced 50+ questions naturally.

## Root cause: Builder self-plays both roles

The builder short-circuits the PO RPC loop. Instead of:
1. Launch PO as a real separate session
2. Wait for PO to ask ONE question (60-200s)
3. Answer as founder
4. Wait for next question
5. Repeat

The builder does:
1. Reads the dossier
2. Writes both PO questions AND founder answers in a single pass
3. Never launches PO at all (or launches it but doesn't wait for responses)

**Evidence from PO session DB (20260724_053111_823fc4):**
- PO session has 56 messages but 0 `<Q>` tags
- PO messages show confusion: "I need to correct course — I jumped ahead and asked a question as PO, but I'm the builder"
- PO session ends with: "I'll run the full grill across all 6 branches. I'm the builder playing both roles"

## Secondary cause: PO grill-rpc skill has wrong limits

The shared `grill-rpc` skill (at `shared-skills/grill-rpc/SKILL.md`) tells PO:
- "The grill is done when all **8 branches** are resolved" — but we use dynamic branches
- "Don't stop early — **20+ questions** is normal" — should be 50+
- "Stay on the active branch. Don't jump to other categories" — prevents natural design-tree walking

Compare with mattpocock's original `grilling` skill (855 bytes, 7 lines):
- "Walk down each branch of the design tree, resolving dependencies between decisions one-by-one"
- "Push past easy answers"
- No branch limits, no question count limits
- This produced 50+ questions naturally

## Tertiary cause: Branch complexity

The per-branch file system (init_branches.sh, add_branch.sh, set_active.sh, state management) adds cognitive overhead. The builder spends tool calls managing branch state instead of grilling. The original ec521103 version used a single CONTEXT.md — simpler, deeper.

## Version comparison

| Version | Bytes | Output storage | Branches | PO skill | Questions produced |
|---------|-------|---------------|----------|----------|-------------------|
| ec521103 (original) | 5,469 | Single CONTEXT.md | None | grill-with-docs | 50+ |
| fb36861f (dynamic) | 4,512 | Per-branch files | Dynamic | grill-rpc | ~20 |
| Current | 5,942 | Per-branch in context/ | Dynamic | grill-rpc | 12 (self-played) |

## Fix needed (blocked by pinning)

1. **self-grill (PINNED):** Add "CRITICAL: You must actually launch PO — never self-play" section with detection method
2. **grill-rpc-ops (PINNED):** Add self-play detection and the PO grill-rpc skill limitation
3. **grill-rpc (shared, not in builder profile):** Remove "8 branches" and "20+" limits, change to "50+ questions is normal"
4. Consider reverting to single CONTEXT.md instead of per-branch files

Both self-grill and grill-rpc-ops are pinned. Run `hermes curator unpin self-grill` and `hermes curator unpin grill-rpc-ops` to enable patching.