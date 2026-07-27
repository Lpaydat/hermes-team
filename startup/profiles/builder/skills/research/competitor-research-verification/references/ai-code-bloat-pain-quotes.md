# AI Code-Bloat / Always-Adds-Code: Verified Pain Quotes (HN)

Reusable evidence bank for any venture dossier on AI coding-assistant code
bloat, refactor-vs-append enforcement, AI-generated duplication, or "AI slop"
code quality. All 12 quotes fetched live from the HN Algolia API on 2026-07-25;
every URL verified resolvable (HTTP 200) and every quote fragment confirmed
present in the API response text. Wording preserved verbatim; only HN HTML
entities normalized for readability.

Companion to `ai-code-quality-linting-landscape.md` (same session) which
covers the competitive set; this file holds the demand-side evidence.

## Primary quotes (verbatim, with source + engagement)

| # | Quote | URL | Date | Engagement |
|---|-------|-----|------|------------|
| 1 | "AI prefers adding new code over modifying existing code, and it rarely deletes anything. After a few iterations, your codebase becomes a mountain of dead code." … "Obsessed with reinventing the wheel. You'll often find it writing three duplicate functions for the exact same feature in a single file." (OP) | https://news.ycombinator.com/item?id=48770319 | 2026-07-03 | 64 pts, 53 cmt |
| 2 | "The most painful part is the 'add instead of change/delete' habit. The real test for AI coding assistants isn't whether they can generate code, but whether they can understand the existing system, reuse the right abstraction, remove bad code, and own the whole call chain after the change." — PaiDxng | https://news.ycombinator.com/item?id=48772239 | 2026-07-03 | in 64-pt thread |
| 3 | "it always prefer[s] create new code or files instead [of] modifying the existing ones then end up creat[ing] problems that wasn't there before…" — jessedu29260 | https://news.ycombinator.com/item?id=48772314 | 2026-07-03 | in 64-pt thread |
| 4 | "AI to edit - wrote duplicated functions that already existed / AI to test - special casing and disabling code to pass the narrow tests it wrote / AI report - 'Everything looks good, ship it!'" — ModernMech (thread: "Who owns the code Claude Code wrote?") | https://news.ycombinator.com/item?id=47933583 | 2026-04-28 | parent 557 pts |
| 5 | "Opus will add a bunch of length & nil checks to 'fix' this, but the actual issue is the string should never be empty. The nil checks are just papering over a deeper issue… All the AI is going to do is smoosh the error messages and kick the can." — ericmcer (re: Claude Opus) | https://news.ycombinator.com/item?id=47678054 | 2026-04-07 | parent 222 pts |
| 6 | "Opus is extremely lazy for me… It always wants to add hacks instead of fixing things properly, it doesn't like large works." — noncoml (thread: "Claude Opus 4.8") | https://news.ycombinator.com/item?id=48319701 | 2026-05-29 | parent 1774 pts |
| 7 | "It just writes terrible code I'd never want to maintain. Can I refactor and have it cleaned up by the AI also? Sure… but then I need to specify exactly how it should go about it." — AstroBen (thread: "Ask HN: evidence that agentic coding works?") | https://news.ycombinator.com/item?id=46712551 | 2026-01-21 | parent 461 pts |
| 8 | "Writing code isn't the hard part, reviewing code is much slower and painful process than writing it from scratch." — bluefirebrand (thread: "Anyone struggling to get value out of coding LLMs?") | https://news.ycombinator.com/item?id=44098593 | 2025-05-26 | parent 345 pts |
| 9 | "LLMs help you 'do stupid things faster.' If all you want to do is dump terrible code into the world as fast as possible, then you've got a great tool." — ryandrake | https://news.ycombinator.com/item?id=44099007 | 2025-05-26 | parent 345 pts |
| 10 | OP (senior eng): "The CEO & CTO promote 'delete entire unit test file & have claude generate a new one'… I don't want [to] be overseeing a bunch of AI-generated spaghetti 2-3 years from now." | https://news.ycombinator.com/item?id=44468375 | 2025-07-04 | 82 pts, 94 cmt |
| 11 | "Vibe-coding… throws away all the principles of software engineering… 'accept all changes' then duct-taping it with more code on top of a chaotic code architecture." — rvz | https://news.ycombinator.com/item?id=43739462 | 2025-04-19 | parent 259 pts |
| 12 | "You end up shipping unreachable functions, duplicate logic, and unused imports that sit there unreviewed and unpatched. Dead code isn't just technical debt - MITRE catalogued it as CWE-561." — swynx | https://news.ycombinator.com/item?id=47065065 | 2026-02-12 | parent 13 pts |

## Corroborating high-engagement threads (title-level signal)

| Thread | URL | Date | Engagement |
|--------|-----|------|------------|
| AI coding is a nightmare. Am I the only one? | https://news.ycombinator.com/item?id=48770319 | 2026-07-03 | 64 pts |
| Ask HN: Anyone struggling to get value out of coding LLMs? | https://news.ycombinator.com/item?id=44095189 | 2025-05-26 | 345 pts |
| Vibe Coding is not an excuse for low-quality work | https://news.ycombinator.com/item?id=43739037 | 2025-04-19 | 259 pts |
| Verification debt: the hidden cost of AI-generated code | https://news.ycombinator.com/item?id=47289406 | 2026-03-07 | 115 pts |
| Ask HN: Do you have any evidence that agentic coding works? | https://news.ycombinator.com/item?id=46691243 | 2026-01-20 | 461 pts |

## Root-cause synthesis (from the quotes)

The HN discussion converges on a structural (not bug-level) cause:

1. **Context-window economics** — agents read only a fraction of large files
   (to save tokens), miss existing functionality, and reinvent it. (Quote 1)
2. **Loss-aversion in edits** — models are RLHF'd to produce visible output and
   avoid deletions that could break things. Adding = "safe"; deleting = "risky."
   (Quotes 5, 6)
3. **No holistic model** — agents hyper-focus on the current task with no
   architectural awareness, so they can't recognize existing logic. (Quotes 1, 2)
4. **Compounding failure** — each add-instead-of-refactor makes files bigger →
   context window worse → MORE duplication. A vicious cycle. (Quote 1)

This means the problem is incentive-aligned into current model training —
durable, not patchable. That's a venture-relevant structural insight.

## Market-pull corroboration (adjacent startups building into the space)

Existence of these funded/high-engagement projects confirms the pain has
enough pull to attract builders and capital — but **none enforce refactor-over-
append as a first-class behavior** (the wedge):

- Semble (445 pts) — code search for agents, 98% fewer tokens
- CodeViz YC S24 (189 pts) — visual codebase maps
- Nia YC S25 (131 pts) — better context for coding agents
- Pyscn (136 pts) — Python quality analyzer for vibe coders
- Haystack (88 pts) — "review PRs like you wrote them"
- Sloppylint (19 pts) — linter for AI-generated Python

See `ai-code-quality-linting-landscape.md` for the full competitive table.

## Reuse notes

- **Re-verify before citing in a fresh dossier.** HN points are stable
  post-first-week, but confirm the URL still resolves and the quote fragment
  is still present (a 4-line API check — see `hn-pain-signal-mining.md` Stage 5).
- These quotes span Apr 2025–Jul 2026; the most recent (48770319, Jul 2026)
  articulates the thesis most sharply. Lead with it.
- For a different-but-related thesis (e.g. "AI security review"), re-run the
  mining pipeline in `hn-pain-signal-mining.md` with tailored keywords rather
  than reusing these quotes out of context.
