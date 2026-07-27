# E2E Pipeline Test Lessons

## Test 2: AI Pen Testing Service (2026-07-24, 18/25)

Build time: ~38 min (05:30 → 06:08). Card blocked during grill, builder self-healed.

### What passed

- Grill persisted to ~/projects/ai-pen-testing-service/grill/ (6 branches, 24 decisions)
- validate-grill-output.sh: PASS (23 checks, 0 failures)
- Prototype: single-file HTML dashboard with live two-agent simulation
- README: full 9-section template, 8 click-by-click "How to Review" steps
- Portfolio: rich entry with correct ~/projects/ path
- No artifacts in ~/vault/ (vault isolation enforced)

### What failed

1. **Builder blocked the card during grill** — same reflex as first E2E test.
   NEVER-block instruction overridden by dispatcher's kanban task protocol.
   Builder self-healed via CLI (claim + complete). Root cause documented in
   self-grill/references/blocking-behavior.md.

2. **Builder skipped loop_engine** — judged the build "simple enough" despite
   the skill saying to use it for quality. Fix: made loop_engine the DEFAULT
   in venture-prototype skill (not opt-in).

3. **Duplicate grill files** — builder created both short names (build.md)
   AND long names (build-vs-wrap-&-technical-moat.md). 6 branches → 12 files.
   Cosmetic — the persistence step copies everything in /tmp/.

## Test 1: 10 prototypes (2026-07-23)

### What worked
- 10 prototypes built end-to-end through grill → build → portfolio
- Sequential kanban chain (parent→child) auto-promoted correctly
- Grill RPC produced real design decisions (PO caught math errors, false competitive claims)

### What failed (and fixes applied)

**Grill docs lost (ROOT CAUSE)**
- Grill scripts write to `/tmp/grill-<slug>/context/` — ephemeral
- Builder sessions never persisted output to `~/projects/<slug>/grill/`
- 3/10 projects had ZERO grill docs; 7/10 used inconsistent names
- FIX: self-grill skill has per-branch persistence section + validate-grill-output.sh gate

**Builder blocked card during self-grill (STILL UNRESOLVED)**
- Happened on 3/10 E2E builds AND on the AI Pen Testing E2E test
- Root cause: kanban task protocol in system prompt overrides skill instruction
- kanban_block cannot be disabled per-tool (only per-toolset)
- Builder self-heals via CLI — accept the behavior

**PO launch via --cli hangs silently**
- glm-5.2 takes 300s+ for first response (thinking alone)
- FIX: grill-rpc-ops PO launch recipe wrapped in `timeout 600`

**Prototype type defaulted to HTML for everything**
- FIX: venture-prototype skill has prototype type selection table

**READMEs inconsistent or missing**
- Only 2/10 had proper READMEs
- FIX: venture-prototype skill has mandatory README template

**Prototypes in wrong location (~/vault/)**
- Migrated all 10 from ~/vault/ventures/prototypes/ to ~/projects/<slug>/prototype/

## Performance characteristics
- ~38 min per idea with new workflow (grill + build + README)
- ~1.5-2 hours per idea with one reclaim cycle (old workflow)
- Block/reclaim adds ~1h per occurrence but builder self-heals
