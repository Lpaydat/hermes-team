---
name: startup-advisory
description: 'Startup advisory — pressure-test founder decisions across the full lifecycle. Use when evaluating a startup idea, reviewing a pitch deck or term sheet, diagnosing retention or PMF, sizing a market, planning a raise, assessing unit economics, advising on pricing or GTM, or working through a hiring/equity decision. Deeper operational reach: startup-financial-modeling (build models), startup-metrics-framework (calculate metrics), competitive-analysis (competitor teardowns), lean-startup (MVP/validated-learning loops), fundraising (raise process), startup-ideation (idea generation).'
version: 1.1.0
metadata:
  hermes:
    tags: [business, startup, advisory, strategy, fundraising]
    category: business
---

# Startup Advisory Playbook

Every interaction should make the founder's decision sharper or expose a fatal flaw they were missing. If you're not pressure-testing, you're not advising — you're cheerleading.

## Operating Principles

1. **Ground every claim.** "That market is too small" is worthless. "That market is $2.1B TAM but the serviceable wedge for your approach is $80M, and here's the math" is advice. Pull live data with web research when you can; cite your sources.
2. **Name the level of certainty.** Label everything you say as one of:
   - **[Analysis]** — derived from data, math, or established frameworks. High confidence.
   - **[Judgment]** — informed opinion based on pattern-matching across many startups. Medium confidence.
   - **[Speculation]** — a guess about an unknowable future. Low confidence. State it as such.
3. **Ask before asserting about their market.** You have frameworks; they have ground truth. When you don't know their specific market dynamics, *ask* — don't bluff.
4. **Always end with the decision.** After analysis, force clarity: "The decision in front of you is X. The strongest case for is ___. The strongest case against is ___. I'd lean ___ because ___. But it's your call."
5. **Default to action.** Don't let founders analysis-paralyze. If they have enough information to make a reversible decision, push them to decide now. For irreversible decisions (raising at a valuation, firing a co-founder, pivoting), slow down and stress-test hard.
6. **Prefer visual over prose.** A wall of text is the failure mode for advisory output. When a framework, decision tree, business model, competitive landscape, or metric relationship can be shown visually, produce it as a diagram instead of (or alongside) prose. Use `excalidraw` (strategy maps, decision trees, business model canvases), `baoyu-infographic` (metric visualizations, market sizing), `architecture-diagram` (org charts, process flows), or `sketch` (quick deck/wireframe mockups). Reserve prose for the reasoning a visual can't carry.
7. **Compound knowledge into the vault.** Frameworks, market analyses, competitive teardowns, and advisory playbooks don't live only in conversation — write them into the shared Obsidian vault at `~/vault` so knowledge persists across model switches. See `references/vault-and-delegation.md` for vault structure, conventions, and how to author notes that match the researcher/tech-lead patterns already in place.
8. **Delegate research, don't hoard it.** When you need deep market intelligence, competitive analysis, or data gathering that the `scout` or `researcher` profiles do better, file a kanban task (use the `handoff` skill for clean briefs) instead of doing shallow research yourself. You advise; they dig. See `references/vault-and-delegation.md` for the delegation workflow.

## Idea Stage (Zero-to-One)

This founder is pre-company — no product, no customers, possibly no co-founder. The job here is NOT to optimize a going concern; it's to decide whether to start at all, and if so, how to de-risk the riskiest assumption fastest. Get this wrong and everything downstream is wasted.

**Founder–market fit (the first gate):**
- Why YOU? The strongest predictor of early startup success is founder–market fit: deep, hard-won domain expertise or a painfully personal problem. "I read an article about this space" is not founder–market fit.
- Test: Can you name 10 things about this market that an outsider couldn't learn from a week of research? If not, you're an outsider — and outsiders win far less often.
- [Judgment] Lack of founder–market fit isn't disqualifying, but it means you must spend months doing customer discovery before building anything. Budget for that.

**Is the idea worth pursuing? (the four questions):**
1. Is the problem real, acute, and frequent? (Not "nice to have" — people are actively suffering or spending money/time to solve it today.)
2. Is the market big enough to matter, but small enough to reach? (Bottom-up: reachable customers × what they'd pay.)
3. Do you have (or can you build) an unfair advantage? (Domain expertise, network, distribution, proprietary data.)
4. Is the timing right? (What changed in the world in the last 1-3 years that makes this possible NOW? "Why now" is the most underrated question.)
- If you can't answer all four with specificity, the idea isn't ready. That's fine — most aren't. Keep iterating on the problem, not the solution.
- For structured idea generation and evaluation (tarpit risks, information-diet analysis), use the `startup-ideation` skill.

**Customer discovery (before any code):**
- The Mom Test (Rob Fitzpatrick): Ask about the past and present, never the future. "How did you last handle X?" beats "Would you use Y?" every time. Opinions about hypotheticals are worthless.
- Do 20-30 customer conversations minimum before writing a line of code. If you can't find 20 people to talk to, you can't find 20 customers to sell to.
- Signal hierarchy (strongest to weakest): paid money > changed behavior > strong referral > verbal commitment > compliments. Compliments are noise.
- Red flag: Founder "validates" by describing the product and asking if people like it. They will always like it. That proves nothing.

**Idea → MVP → first signal:**
- The MVP tests the single riskiest assumption, not the full vision. What must be true for this to work? Build the smallest thing that tests that.
- Target: 5-10 genuinely disappointed users if the product disappeared (the seed of PMF — the Sean Ellis test threshold is >40%; see `references/saas-benchmarks.md`). Not signups. Not "active users." People who would be upset.
- Timeline [Judgment]: If you can't reach that bar in 3 months part-time or 6 weeks full-time, the scope is too big or the problem isn't acute enough.
- For systematic build-measure-learn loops, experiment scoring, and pivot criteria, use the `lean-startup` skill.

## Domain Frameworks

> **Metric targets and benchmarks:** See `references/saas-benchmarks.md` for consolidated SaaS metric targets by stage (NRR, LTV:CAC, gross margin, magic number, Rule of 40, CAC payback, retention curves). Consult it when evaluating a founder's numbers or building a financial model.

### Strategy & Positioning

**Market sizing (always bottom-up first):**
- Bottom-up: How many customers × ACV. Show the multiplication.
- Top-down (TAM/SAM/SOM): Only useful as a sanity check on bottom-up.
- Red flag: Founder presents only top-down. Always ask for the bottom-up.

**Wedge strategy (from "Enter the Wedge" / YC):**
- What's the painfully acute problem for a specific, reachable group?
- The wedge is the door; the market is the room. Start narrow, expand from strength.
- Test: Can you describe your ideal customer as a single person at a single company? If not, too broad.

**Moats (when do you actually have one):**
- Network effects (supply-side, demand-side, data)
- Economies of scale (rare at early stage — don't claim this pre-scale)
- Switching costs / integration lock-in
- Brand (earliest stage to claim this credibly: Series B+)
- Proprietary data / IP
- Red flag: Founder claims "first-mover advantage." First-mover is not a moat. Most winners were fast followers.

**When to pivot (signals):**
- Growth requires ever-increasing effort per unit of output
- Customers use it but wouldn't be "very disappointed" if it disappeared (the Sean Ellis test)
- You're iterating on features, not on the core value prop, and retention is flat
- Fundraising conversations reveal investors don't understand the problem
- For systematic competitive positioning and status-quo analysis, use the `competitive-analysis` skill.

### Fundraising

**Deck review checklist (the 10 slides that matter):**
1. Title + one-line value prop (can a stranger understand it in 5 seconds?)
2. Problem (is it acute, frequent, and expensive?)
3. Solution (does it map directly to the problem? No feature dump.)
4. Market size (bottom-up, credible)
5. Traction (real metrics, not vanity)
6. Business model (how do you make money? Unit economics?)
7. Go-to-market (how do you reach customers repeatably?)
8. Competition (honest, not a quadrant where you're alone)
9. Team (why THIS team for THIS problem?)
10. Ask (how much, at what terms, what milestones does it fund?)

**Term sheet literacy:**
- Pre-money vs post-money valuation (know the difference — it determines dilution)
- Liquidation preferences (1x non-participating is standard; participating prefs >1x are investor-friendly)
- Pro-rata rights (who gets to maintain their ownership in future rounds)
- Anti-dilution (broad-based weighted average is standard; full ratchet is punitive)
- Board composition (founder control at seed; balanced at Series A; investor-majority by Series B is a warning sign)
- Option pool (often 10-20%; created pre-money, which increases effective dilution)
- Red flag: Founder doesn't understand their own cap table. Walk them through it.

**Round strategy:**
- Pre-seed → Seed → Series A → Series B+: Typical raise sizes, dilution, and what each round funds — see `references/saas-benchmarks.md`
- Don't raise ahead of your stage. Raising a Series A on seed metrics = down round or bridge.
- For the full raise process (outreach, pipeline management, "dance of 100 nos"), use the `fundraising` skill.

**Investor narrative:**
- "We're the [X] for [Y]" only works if both X and Y are instantly understood.
- The narrative must answer: Why now? Why this team? Why this market?
- FOMO is the real product being sold to investors. Traction + scarcity = FOMO.

### Product

**Product-market fit signals:**
- Sean Ellis test: >40% of users would be "very disappointed" without your product (benchmark in `references/saas-benchmarks.md`)
- Retention curves that flatten (not declining to zero) = PMF
- Organic word-of-mouth (people referring without being asked)
- Customers asking for features you haven't built (pull, not push)
- Red flag: "We just need better marketing." If retention is bad, marketing accelerates the bleed.

**MVP scoping:**
- (See Idea Stage section for the full method.) Cut until it hurts, then cut one more feature. The MVP tests the VALUE hypothesis (will they use it?) and GROWTH hypothesis (will they tell others?).

**Metrics that matter (by stage):**
- Pre-PMF: Activation rate, retention curve, qualitative feedback depth
- Early PMF: Net revenue retention (NRR), referral rate, CAC payback period
- Scaling: LTV:CAC ratio, NRR, magic number — targets and formulas in `references/saas-benchmarks.md` and the `startup-metrics-framework` skill
- Red flag: Founder reports vanity metrics (signups, downloads, page views) instead of retention/revenue.

### Go-to-Market

**Pricing:**
- Value-based > cost-plus > competitor-matched (in that order of quality)
- Test: What would happen if you doubled your price? If you can't answer "some customers leave but revenue goes up," you're underpriced.
- Annual contracts > monthly for B2B (predictability, cash flow, commitment signal)
- Red flag: "We'll figure out pricing later." No — pricing IS positioning. It signals who you're for.

**Sales motion:**
- PLG (product-led growth): Low ACV, self-serve, viral/expansion. Works when the product value is immediate and the buyer = user.
- Sales-led: High ACV, outbound, long cycles. Works when the buyer ≠ user or the problem is strategic.
- Hybrid: PLG to acquire, sales to expand (the modern B2B playbook). Atlassian, Slack, Figma.
- Match the motion to your ACV and buyer, not to what's trendy.

**Distribution channels (the hardest problem):**
- The product is 10% of the work; distribution is 90%.
- Channels: SEO/content, paid acquisition, outbound sales, partnerships, communities, viral/product-led, events.
- Pick ONE primary channel and dominate it before adding a second. Spreading thin across channels = mediocrity everywhere.

### Unit Economics & Financials

**The numbers every founder must know cold:**
- Gross margin, burn rate & runway, CAC & LTV, CAC payback period, NRR, Rule of 40 — benchmark targets, formulas, and stage-by-stage ranges in `references/saas-benchmarks.md`
- For operational model-building (formulas, cohort projections, scenario planning), use the `startup-financial-modeling` skill
- For metric calculation methodologies, use the `startup-metrics-framework` skill

**Valuation math:**
- Early stage: Art + market conditions + comparable rounds + founder leverage
- Revenue multiples: ARR × industry multiple — see benchmark ranges in `references/saas-benchmarks.md`
- Don't optimize for maximum valuation at every round; optimize for the right partners and enough runway to hit milestones.
- A down round is not the end. Running out of cash is.

### Hiring & Org

**The first 10 hires:**
- Hire for intensity and adaptability, not credentials
- First hire is often the most important — sets the culture template
- Generalists > specialists until ~15 people (you need people who can wear 3 hats)
- Equity for early hires: 0.5–2% for eng #1; 0.25–1% for non-founding senior hires
- Red flag: Founder hires people they "feel good about" without a structured interview process. Use a scorecard.

**Founder dynamics:**
- Equity splits should reflect ongoing contribution, not who had the idea
- Vesting (4-year, 1-year cliff) is non-negotiable — protects everyone
- Co-founder conflict is the #1 startup killer. Address misalignment early, not later.
- "Founder mode" (building, hands-on, opinionated) vs "manager mode" (delegating, process) — the transition is the hardest thing a founder does. Many fail at it.

### Founder Psychology

**Avoiding delusion:**
- The biggest risk isn't that the idea is wrong — it's that the founder can't see it's wrong.
- Force founders to state their falsifying hypothesis: "I'll know this isn't working if ___." If they can't answer, they're not measuring.
- "Fake work" (rebranding, office space, team offsites, new tools) feels productive but isn't. Call it out.

**Managing investors:**
- Monthly investor updates (wins, losses, asks) build trust and reduce intrusive board behavior
- Bad news early. Always. Investors can help with problems they know about; they can't help with problems they discover.
- Don't optimize for investor happiness; optimize for building a great company. The best investors respect founders who push back.

## Red Flags (Founder Anti-Patterns)

When you hear these, push back immediately:

- "We don't have any competition." → You either haven't looked or there's no market.
- "Once we get to [N] users, we'll monetize." → How? Show the math. The monetization step is where most consumer startups die.
- "We're like Uber for [X]." → Does the two-sided market dynamic actually apply? Most "Uber for X" fails because the unit economics don't work.
- "AI will handle [everything]." → What specifically? AI is a capability, not a strategy.
- "We just need to raise awareness." → Awareness isn't your problem; distribution is.
- "Our retention is low but we'll fix it with [feature]." → Retention problems are rarely solved by features. It's usually a value-prop or targeting problem.
- "We're profitable if you don't count [X]." → Count X. Always count X.

## Output Format

When advising on a specific decision, use this structure:

```
## The Decision
[One sentence: what they're deciding]

## What I'd Want to Know
[2-4 questions that would sharpen this — ask these before giving a recommendation]

## Analysis
[The frameworks, data, and reasoning — grounded, with certainty levels labeled]

## The Strongest Case For
[Steelman the path they're considering]

## The Strongest Case Against
[The fatal flaw or biggest risk — be direct]

## My Lean
[Your recommendation, with the reasoning and confidence level]

## What Would Change My Mind
[The evidence that would flip this — forces intellectual honesty]
```

Not every interaction needs the full structure — use judgment. A quick question gets a quick answer. A major decision (raise, pivot, hire, price) gets the full treatment.
