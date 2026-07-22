# SOUL.md ↔ Grill Script Drift — Session Finding

**Date:** 2026-07-22
**Trigger:** User asked "did you fix that yet?" about dynamic branches. Builder quoted hardcoded 8 branches from SOUL.md, but the actual scripts already implemented dynamic branching.

## What Happened

1. In a prior session, the grill system was upgraded from 8 hardcoded branches to dynamic branching (v0.7+).
2. The scripts (`init_branches.sh`, `add_branch.sh`) were updated to start empty and create branches dynamically.
3. SOUL.md was NEVER updated — it still said "8 design branches (product, user, mechanism, data, edges, output, deployment, constraints)".
4. Memory also carried stale info.
5. The builder confidently described the old system to the user because it was reading from SOUL.md, not from the actual code.

## Root Cause

No sync check was part of the grill upgrade workflow. When you change the grill system, you must verify that SOUL.md, memory, and the skill SKILL.md all describe the same system.

## Fix Applied

- SOUL.md: replaced "8 design branches" with "DYNAMIC design branches (created during the grill, not pre-defined)" in two locations.
- Memory: updated to reflect dynamic branching as current state.
- grill-rpc-ops SKILL.md: added "SOUL.md ↔ Skill Code Sync" pitfall section.

## Lesson

Identity files (SOUL.md) and operational skills describe the same system from different angles. Changes to one without the other create a credibility gap — the builder describes a system that doesn't match reality. Always patch both in the same session.
