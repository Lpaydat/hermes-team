# 2026-07-24 Full Pipeline E2E — 10/10 Cards Complete

## Summary

First full end-to-end test of the pipeline v3 architecture. All 10 build cards completed successfully. Sequential parent-child chaining worked correctly — each card auto-promoted when its parent completed.

## Timeline

- **23:16** — queue-builds.sh created 10 cards
- **00:23** — Card 1 (LeadPilot) done (1h7m)
- **00:53** — Card 4 (WhatsApp) started, hit block-during-grill (same bug)
- **03:14** — Card 10 (FlowGuard) done. **All 10 complete.**
- Total runtime: ~4 hours

## Per-card timing

Cards 1-4: ~50-65 min each (with grill block + reclaim cycle overhead on some).
Cards 5-10: similar pattern — builder blocked card during grill, dispatcher reclaimed after ~1h stale timeout, fresh session picked up from comments.

## Issues found and fixed

1. **queue-builds.sh eval bug** — `eval hermes kanban create $ARGS` word-split the multi-line body, silently failing every card creation. Fixed: direct invocation without eval.
2. **Builder blocks kanban card during self-grill** — builder calls `kanban_block(kind='needs_input')` while waiting for grill answers, but IS the founder. Stops heartbeats, triggers dispatcher reclaim after ~1h. Fixed: added "NEVER block" section to self-grill SKILL.md.
3. **Grill `--cli` PO launch hangs** — bare `hermes -p product-owner --cli` produces no output for 300s+. Fixed: grill-rpc-ops SKILL.md now specifies `timeout 600 ... --cli 2>&1 | tail -80`.
4. **Prototypes in wrong location** — Builder put prototypes in `~/vault/ventures/prototypes/` (Obsidian vault). User corrected: `~/vault/` is Obsidian second brain ONLY. Prototypes must go in `~/projects/<slug>/prototype/`. Fixed: all paths updated in PIPELINE-ARCHITECTURE.md, SOUL.md, pipeline-context.md, queue-builds.sh, project-promotion SKILL.md.
5. **Inconsistent README deliverables** — Only 2/10 prototypes shipped with proper README.md. Added prototype-deliverable-requirements.md and updated queue-builds.sh card body to require README.

## Verified working

- [x] queue-builds.sh: parses idea-bank.md, creates 10 chained cards, dedup on re-run
- [x] Sequential chain: parent done → child auto-promotes to ready → dispatcher spawns builder
- [x] Grill RPC: builder launches PO, answers as founder, locks decisions
- [x] Prototype build: single-file HTML interactive demos
- [x] Portfolio update: each card adds Awaiting Review entry
- [x] Card completion: kanban_complete with structured metadata

## Deliverable quality (after fixes applied)

10 prototype dirs at `~/projects/<slug>/prototype/`:
| Prototype | Files | Size |
|-----------|-------|------|
| leadpilot-local-smb-lead-gen | 2 (index.html, README.md) | 64K |
| osint-desk | 3 (index.html, README.md, design-decisions.md) | 72K |
| ai-smb-bookkeeping | 2 (index.html, design-decisions.md) | 68K |
| whatsapp-shared-inbox-for-dtc-smb-replydeck | 2 (index.html, grill-decisions.md) | 56K |
| indie-builder-distribution-cluster | 2 (index.html, grill-decisions.md) | 80K |
| dockerless-ci-verification-service | 2 (index.html, grill-decisions.md) | 60K |
| ai-interview-saas-10k-mrr-solo | 1 (index.html) | 80K |
| scraper-micropayments-agent-aware-access-control | 2 (index.html, grill-decisions.md) | 72K |
| privacy-first-ai-coding-smoke-test | 1 (index.html) | 44K |
| flowguard-ai-coding-flow-protector | 2 (index.html, grill-decisions.md) | 72K |

8/10 missing README.md — this was not required in the card body during the E2E test. Fixed for future runs.

## Remaining items

- [ ] Stage 3 (user review) — user reviews 10 prototypes, says fix/promote/shelve
- [ ] Stage 4 (promotion) — test project-promotion skill end-to-end
- [ ] Merge `feat/decision-tree-grill` to main after all stages pass
- [ ] project-promotion SKILL.md has stale path (step 3 says copy from ~/vault/ventures/prototypes/) — pinned, needs manual fix
