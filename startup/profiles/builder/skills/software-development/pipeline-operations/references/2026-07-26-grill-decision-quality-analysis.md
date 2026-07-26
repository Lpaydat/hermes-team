# Grill Decision Quality Analysis — The Log is the Agent (478 decisions)

## Context

The 2026-07-26 livetest produced a 478-decision grill across 5 branches. This raised the question: are all 478 decisions valid, or is the grill padding? The user asked to analyze before deciding on a cap.

## Decision distribution by branch

| Branch | Decisions | Assessment |
|--------|-----------|------------|
| wedge-and-moat | 20 | Tight, focused, no redundancy |
| replay-semantics | 34 | All valid UX/implementation decisions |
| side-effects-divergence | 10 | Compact, essential, every decision load-bearing |
| capture-contract | 182 | Technically dense, ~20-30 over-specified for prototype |
| sustainability-oss-strategy | 232 | Deepest, breakthrough insights at 200+ |

## Valid patterns found

1. **Every decision resolves a specific ambiguity PO identified** — no padding questions
2. **PO caught real contradictions**: D127 ("network effect" was actually data lock-in), D198 (recovery test collides with user-care obligation)
3. **Sustainability branch has a clear narrative arc**: optimistic model → systematic challenge → honest recalibration → part-time recommendation (D234: "this is an OSS project, not a business")
4. **Technical decisions (capture-contract) are implementable directly** — event taxonomy, concurrency model, blob store, delta encoding

## Redundancy/drift found

1. **Capture-contract has ~20-30 over-specified durability decisions** (D87, D88, D91, D90, D92) — production-grade retry/fsync patterns premature for a prototype
2. **Sustainability has circular revisiting** of the conversion problem (D171 → D183 → D189 → D231 → D232 → D233) — each angle revealed something new, but diminishing returns after D231
3. **Some decisions supersede earlier ones** (D236 supersedes D155/D159/D160/D163/D172) — healthy correction but indicates early decisions were premature

## Conclusion: NO fixed cap

A 60-decision cap would have missed the sustainability breakthrough at D234. A 100-decision cap would have missed the conversion analysis at D231. The grill SHOULD run deep when the idea has many design dimensions.

## Dynamic stop condition designed

Instead of a cap, detect convergence via 4 signals:
1. Supersession rate >20% of recent decisions
2. Question depth decay (fundamental → refinement)
3. Branch exhaustion (15+ Qs without new branch)
4. Founder convergence (5+ consecutive "Agree/Accept")

When all 4 fire, wrap up. When they conflict, keep going.
