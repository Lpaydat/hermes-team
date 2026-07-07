# C6 R3 Timeline — Duplicate Fix Card Root Cause

## The Problem

In C6 R3 (slugify + truncate_text, both modifying utils.py), the truncate tech-lead did NOT use `kanban_delegate`. It manually created dev/verifier cards via `kanban_create`, then polled in a sleep-loop. When the verifier PASSed but hit a merge conflict, BOTH the verifier AND the still-running tech-lead independently created fix cards — producing two parallel fix chains.

## Timeline Tree

### Chain A: Slugify (clean — first to merge, CORRECT behavior)

```
[15:16] tech-lead (t_d86150bf) — [auto] C6R3 slugify()
  ├─ [15:17] claimed
  ├─ [15:20] linked → blocks on verifier t_3204d4c6  ← kanban_delegate WORKED
  ├─ [15:20] dependency_wait: "Waiting on verifier..."
  ├─ [15:32] promoted (verifier done)
  ├─ [15:33] claimed (re-dispatched)
  └─ [15:33] completed: "slugify() bead complete"
      │
      ├── [15:19] developer (t_92736610) — [dev] slugify()
      │     ├─ [15:20] claimed
      │     └─ [15:25] completed: "Added slugify()"
      │         │
      │         └── [15:20] verifier (t_3204d4c6) — [verify] slugify()
      │               ├─ [15:25] promoted (dev done)
      │               ├─ [15:25] claimed
      │               └─ [15:32] completed: "VERDICT: PASS"
      │                  └─ merged to main as af0d55c ✅
```

### Chain B: Truncate (conflicts with slugify, INCORRECT behavior)

```
[15:16] tech-lead (t_8dc3b626) — [auto] C6R3 truncate_text()
  ├─ [15:17] claimed
  ├─ ⚠️ NO dependency_wait event!  ← did NOT use kanban_delegate
  ├─ ⚠️ NO linked event!
  └─ [15:57] completed: "truncate_text() complete"
      │
      ├── [15:19] developer (t_a365fdf1) — [dev] truncate_text()
      │     ├─ [15:19] claimed
      │     └─ [15:24] completed: "Added truncate_text()"
      │         │
      │         └── [15:19] verifier (t_319a891b) — [verify] truncate_text()
      │               ├─ [15:25] promoted (dev done)
      │               ├─ [15:25] claimed
      │               ├─ [15:36] completed: "VERDICT: PASS (4/4 ACs)"
      │               │         BUT merge failed — slugify landed first!
      │               │
      │               ├── [15:36] FIX CHAIN 1 (verifier-created) ✅
      │               │     │
      │               │     ├── [15:36] developer (t_e04e7c13) — [fix] resolve conflict
      │               │     │     (parent: t_319a891b — verifier created this)
      │               │     │     ├─ [15:36] claimed
      │               │     │     └─ [15:47] completed: "Rebased, resolved conflict"
      │               │     │         │
      │               │     │         └── [15:36] verifier (t_509a64f2) — [verify] re-check
      │               │     │               (parent: t_e04e7c13)
      │               │     │               ├─ [15:47] promoted (fix done)
      │               │     │               ├─ [15:47] claimed
      │               │     │               └─ [15:54] completed: "VERDICT: PASS"
      │               │     │                  └─ merged to main as a014fea ✅
      │               │
      │               └── [15:37] FIX CHAIN 2 (tech-lead-created) ⚠️ REDUNDANT
      │                     │
      │                     ├── [15:37] developer (t_127331f5) — [fix] resolve conflict
      │                     │     (NO parent! created_by=tech-lead)
      │                     │     ├─ [15:37] claimed
      │                     │     └─ [15:49] completed: "Resolved conflict"
      │                     │         │
      │                     │         └── [15:37] verifier (t_fbd91ff9) — [verify] re-check
      │                     │               (parent: t_127331f5)
      │                     │               ├─ [15:49] promoted
      │                     │               ├─ [15:49] claimed
      │                     │               └─ [15:54] completed: "VERDICT: PASS"
      │                     │                  └─ no-op (already on main) ⚠️
```

## Two Problems

### Problem 1: Tech-lead didn't use `kanban_delegate`

Slugify tech-lead: correctly used `kanban_delegate` → blocked at 15:20 → promoted at 15:32.

Truncate tech-lead: NO `dependency_wait`, NO `linked` events. It created dev/verifier cards manually via `kanban_create` and then polled in a sleep-loop (`sleep 60` + `kanban_show` repeated 20+ times).

The session DB shows tech-lead calling `kanban_show` every 60 seconds for 20+ minutes instead of blocking. It treated itself as a live supervisor watching the verifier.

### Problem 2: Duplicate fix chains

Because tech-lead was still running (not blocked), it saw the verifier's completion via `kanban_show` at 15:36. The verifier had PASSed the code but couldn't merge (conflict). The verifier created fix card `t_e04e7c13` at 15:36:32. Tech-lead saw the same situation and created its OWN fix card `t_127331f5` at 15:37:20 — 48 seconds later, with no parent link.

**If tech-lead had used `kanban_delegate`, it would have been blocked (in todo) when the verifier completed. It wouldn't have been running to see the conflict and create a duplicate.**

## Root Cause

Both problems trace to one issue: **the tool name `delegate_and_wait` was unclear**. The model saw the name and didn't understand it was supposed to USE it instead of manual `kanban_create` + polling. It defaulted to the old manual pattern.

## Fix Applied

1. Renamed `delegate_and_wait` → `kanban_delegate` (clearer: "delegate" = create cards + block)
2. Added 3-step checklist to SKILL.md with explicit:
   - "STOP HERE. Do NOT poll. Do NOT sleep. Do NOT call kanban_show in a loop."
   - "NEVER create fix cards yourself — the verifier handles FAIL routing."
3. Tool description now says "This is the ONLY way to create dev/verifier cards"
