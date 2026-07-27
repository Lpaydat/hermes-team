# AI Code-Quality / Linting / Refactoring Landscape (captured 2026-07-25)

Reusable competitive landscape for any venture dossier on AI code review,
AI-era linting, refactoring enforcement, AI-code-bloat detection, or agent
guardrails. Re-verify pricing and GitHub stars before citing in a fresh
dossier — this field is moving fast (multiple acquisitions and pricing-model
changes in mid-2026). Captured during the "AI Always-Adds-Code Fixer"
(refactor-don't-append enforcement) competitor sweep.

## Verified price ladder (per seat/month, live 2026-07-25)

All extracted via curl + JSON-LD-first / regex-second on the vendor pricing
page (HTTP 200 unless noted). Extraction method follows the parent SKILL.md.

| Tool | Free | Mid | Top | Unit / notes | Source |
|------|------|-----|-----|--------------|--------|
| **CodeRabbit** | $0 | Pro **$24** | Pro Plus **$48** | per user/mo; Slack agent $0.50/min | coderabbit.ai/pricing (regex) |
| **Sourcery** | — | Pro **$12** | Team **$24** | per seat/mo | sourcery.ai/pricing (regex) |
| **Greptile** | $0 (individual) | Pro **$30** | Enterprise (custom) | per seat/mo; 50 review credits/seat; $1/extra credit; 50% off pre-Series A | greptile.com/pricing (JSON-LD + regex) |
| **Bito** | — | Team **$12**/15 mo | Professional **$20**/25 mo | per seat/mo; **5K LOC/seat included, $5/1K after** (LOC-overage pricing) | bito.ai/pricing (regex) |
| **DeepSource** | trial | Team **$24** | — | per dev/mo + **$8-15 per 10K LOC** usage (LOC-based pricing) | deepsource.com/pricing (regex) |
| **SonarQube** | — | Team **$34** (≤100K LOC) | Enterprise (custom) | per month, LOC-tiered | sonarsource.com/plans-and-pricing (regex) |
| **SonarCloud** | — | **$20** (public) / **$25** (private) annual | $40/$50 monthly | per user/mo, ≤50 users | sonarsource.com/plans-and-pricing (regex) |
| **Cursor** | Hobby | Individual **$20** | Teams **$40** | per user/mo | cursor.com/pricing (regex) |
| **GitHub Copilot** | Free tier | Pro **$10** / Pro+ ~$15 | Max ~$200 / Business pooled | bundled; now also consumes Actions minutes (Jun 2026) | github.com/features/copilot (regex) |
| **CodiumAI / PR-Agent** | OSS PR-Agent | — | — | **HTTP 403 — could not verify live** (WAF-blocked) | codium.ai/pricing |

**Market-clearing per-seat band for AI code review: $12–$48/seat/mo.**
A new entrant should land at or below this. $10–15 reads as a focused
enforcement tool undercutting the generalist reviewers.

## Pricing-model structural misalignment (competitive wedge signal)

**This is a reusable analytical lens, not specific to this dossier.** Two
incumbents in this category charge **by lines-of-code processed** — meaning
their revenue *grows* with code volume / bloat:

- **DeepSource:** $8 per 10K LOC (standard), $15 per 10K LOC (advanced), on
  top of the $24/dev/mo seat fee.
- **Bito:** 5K LOC/seat/month included, then **$5 per 1K LOC overage**.

A venture whose thesis is *reducing* code (refactoring, deduplication,
enforcing "delete-don't-append") is **structurally misaligned** with the
revenue model of LOC-priced incumbents: every line they remove is revenue the
incumbent loses. This makes the incumbent a poor fit to build the
code-reduction feature themselves — an opening for a focused entrant.

**Generalize:** whenever scanning a competitive set, check whether the
incumbent's *pricing unit* is aligned or misaligned with your thesis. If
their revenue metric is the thing your product reduces, that is both (a) a
wedge the incumbent won't easily close and (b) a positioning argument
("they profit from the problem we solve"). Record it in the dossier's
net-gap as a structural advantage, not just a feature gap.

## The thesis gap (why no one owns refactor-enforcement)

HN searches (2026-07-25) for "enforce refactor," "prevent code bloat," "code
reduction tool AI," "refactor don't append," "LOC reduction tool" returned
**zero tools** that address refactor-discipline enforcement. Every adjacent
tool falls into one of four categories, each with a gap:

1. **Generic AI code review** (CodeRabbit, Sourcery, Greptile, Bito,
   DeepSource) — detects *symptoms* of bloat (duplication, complexity)
   post-hoc, not the *behavior* (appending vs refactoring) in real time.
2. **LOC-priced tools** (DeepSource, Bito) — structurally disincentivized
   to reduce code (see lens above).
3. **The AI assistants themselves** (Cursor, Claude Code, Copilot) —
   **incentive conflict**: the tool creating the append-problem won't
   enforce against it. Cursor `.cursorrules` is advisory (prompt-level),
   not enforced.
4. **Agent guardrails** (AgentLint x3 — see below) — focus on
   secrets/force-push/file-scope, explicitly NOT refactor discipline.

## Closest encroachment: "ESLint for AI agents" (nascent, crowded at bottom)

Three near-identical "AgentLint" OSS projects launched in <6 months — a
low-differentiation land grab. **None cover refactor-don't-append** (GitHub
code search for "refactor" = 0 matches in the most-detailed repo).

| Project | GitHub | Rules | Covers refactor? | Updated |
|---------|--------|-------|------------------|---------|
| AgentLint (mauhpr) | 28★ | 77 rules, 8 packs | No. Closest: `no-large-diff` (>200 lines added), `no-file-creation-sprawl` (>10 new files) — proxy heuristics, not semantic | 2026-07-08 |
| AgentLint (0xmariowwu) | 48★ | "Linter for agent harness" (Claude Code/Codex/Cursor) | Not investigated in depth | 2026-07-24 |
| AgentLint (samilozturk) | "ESLint for coding agents" | — | Not investigated | — |

**mauhpr/agentlint rule inventory (most detailed, worth reusing):**
77 rules across 8 packs — universal (24: secrets, force-push, debug
artifacts, `max-file-size` 500 lines, `drift-detector`, `token-budget`),
quality (7: `no-error-handling-removal`, `no-large-diff`,
`no-file-creation-sprawl`, `no-dead-imports`, `self-review-prompt`),
plus Python (6), Frontend (8), React (3), SEO (4), Security (opt-in),
Autopilot (experimental infra-safety). The quality pack's proxy heuristics
are the closest existing rules to refactor-discipline — a future entrant
should explicitly differentiate from these.

## Strongest same-category competitor: Sourcery

Sourcery's homepage (verified live 2026-07-25) **explicitly names the
exact problem** the refactor-enforcement thesis targets:

> "AI produces more code, faster. Normal peer reviews can't really keep up.
> PRs pile up. More code, longer queues, slower merges. Hidden risks slip
> through... Mounting tech debt. AI patterns drift from your standards."

But Sourcery solves it with **generic AI code review** ($12/$24/seat/mo), not
semantic refactor-vs-append enforcement. **Highest encroachment risk** — a
feature pivot could close the gap. Record this in any future dossier on the
same thesis.

## Problem-validation signals (HN, verified 2026-07-25)

The "AI always adds code / code bloat / AI slop" problem is actively
discussed and escalating. Useful evidence threads (objectID / pts / comments):

- **48841446** (103/108) — "AI changes the economics of software rewrites"
  (2026-07-09). Direct: argues clean/refactored codebases get AI leverage;
  bloat kills AI ROI. Linked article: "AI slop starts with the codebase
  itself."
- **48770319** (64/53) — "AI coding is a nightmare. Am I the only one?" (2026-07-03).
- **47932028** (312/207) — "GitHub Copilot code review will start consuming
  Actions minutes" (2026-04-28). Backlash = opening for third-party tools.
- **47966075** (17/3) — "Greptile's New Pricing Is Predatory" (2026-04-30).
  Pricing-controversy = room for transparent alternative.
- Godot "drowning in AI slop" threads (2026-02/03, 16pts + 2pts) —
  maintainer pain from AI-generated PRs.
- "How do you measure 'AI slop'?" (4/1, 2025-07-31) — **open question; no
  tool exists to measure it.**
- "Mesa Project Adds Code Comprehension Requirement After AI Slop Incident"
  (2025-10) — policy workaround, not tooling.

## Defunct / acquired (structural signal)

- **Continue.dev** — **acquired by Cursor** (2026-06-15, HN 13/10).
  Homepage is now a sunset notice ("Continue has joined Cursor"); OSS
  codebase remains. Was the leading OSS coding-agent. **No longer a
  competitor.** Same "standalone players get absorbed" structural pattern
  seen in subscription-cancellation (Truebill→Rocket, Cushion→LendingClub).

## Native AI-assistant enforcement surfaces (distribution opportunities)

- **Cursor `.cursorrules` / rules** — advisory prompt-level, not enforced.
  `awesome-cursorrules` repo: **40,421★ / 3,450 forks** (large ecosystem).
  GitHub search of the canonical rules repo for "refactor" = **0 matches**.
- **Claude Code hooks** — PreToolUse/PostToolUse hooks exist; no native
  refactor-discipline rule ships. **Build-distribution opportunity** (ship as
  a Claude Code hook / MCP tool).
- **Copilot review** — focuses on bugs/security; moved to Actions-minutes
  billing June 2026 (backlash).
