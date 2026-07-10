# kanban_chains E2E Test Comparison — Option A (CLI) vs Option B (Plugin)

Tested against cross-browser-ai MVP (Next.js + Supabase + Stripe + Playwright).

## Option A — `hermes kanban swarm` CLI

### What worked
- Topology creation: root + 4 workers + verifier + synthesizer with correct parent/child wiring
- Blackboard posting by orchestrator after swarm creation
- Worker execution: all 4 workers completed with real findings

### What failed (test 1)
- **Bracket syntax bug:** skill showed `[:qa-functional]` but CLI parser captured `qa-functional]` as skill name → all 4 workers crashed on startup
- **Hardcoded verifier/synthesizer skills:** platform `kanban_swarm.py` hardcodes `requesting-code-review` and `humanizer` — neither exists on QA profile → verifier crashed
- Fix: changed skill to `:qa-functional` (no brackets) + installed stub skills for `humanizer` and `requesting-code-review`

### What failed (test 2, after fix)
- **Orchestrator created duplicate swarm on re-dispatch** — didn't check if synthesizer already completed
- **Orchestrator blocked with `kind=null`** instead of `kind=dependency` — card stuck in `blocked` status, never auto-promoted
- **Card bodies were generic boilerplate** — workers had to parse blackboard to find their task assignment

## Option B — `qa_swarm` plugin (predecessor to kanban_chains)

### What worked
- Tailored card bodies with specific checklists (claims, endpoints, container commands)
- Auto-allocated ports baked into worker bodies
- Clean skill names (no bracket bug)
- All 4 workers completed without crashes
- Synthesizer filed deduped findings

### Limitation
- Profile-scoped plugin — only QA could use it
- Hardcoded artifact-type-to-worker mapping (not dynamic)

## kanban_chains (final unified plugin)

### What worked
- One tool for both topologies (tech-lead dev+verifier chains, QA worker+synthesizer)
- Dynamic worker selection (model chooses, tool creates)
- Blackboard optional (tech-lead chains don't need it)
- Auto port allocation when `image_tag` set
- Global plugin — all profiles discover it

### Key lessons
1. The tool should handle ALL linking and blocking — skills should never teach manual `kanban_link`/`kanban_block` for topology the tool manages
2. Skills must show the actual call shape (object structure), not just prose
3. Orchestrator should complete after filing verdict, not block waiting for tech-lead fixes
4. Re-test is a separate QA card, not a continuation
5. Stale claim_locks can strand ready cards for hours — clear them manually if dispatch dry-run shows 0 spawned
