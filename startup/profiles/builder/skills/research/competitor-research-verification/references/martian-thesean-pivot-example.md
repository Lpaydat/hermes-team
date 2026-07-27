# Martian → Thesean AI: a documented competitor pivot

## Background

Martian (withmartian.com) was a well-known model-router startup. The
original AI Cost Optimization / LLM Router Service kill record (2026-07-08)
cited them as one of several funded entrants in the router space ($9M
raised). Multiple references in the venture pipeline (idea-bank.md,
killed-ideas.md) assumed Martian was an active competitor.

## Detection (2026-07-24)

During competitor pricing research for the AI Cost Optimization dossier:

1. **curl attempt:** `curl -sL https://withmartian.com/pricing` returned
   a short HTML page that redirected to the homepage with no prices.
   Standard JS-rendered behavior — not immediately suspicious.

2. **Browser navigation:** Navigated to the homepage. The accessibility
   tree revealed a completely different positioning: "Understanding
   Intelligence" as a research mission, sections on "ARES (Online RL for
   Coding Agents)", "Code Review Bench", "K-Steering" — all
   interpretability research artifacts, not a router product.

3. **Confirmation:** The homepage described "Thesean AI" as a research
   lab spun out of their work. Navigation links: "THE SEAN", "BLOG",
   "RESEARCH", "ARTIFACTS", "CONTACT" — no "Product", "Docs", "Pricing",
   or "Login". The router product had been fully decommissioned.

4. **Cross-reference:** HN Algolia had no significant Martian posts since
   early 2024 (a 2-point Ask HN). Their last market signal was before the
   router category explosion.

## Impact on dossier scoring

The original kill record's "Competition = 1/5" was based in part on
Martian's presence in the space. Removing them from the active competitor
list reduced density meaningfully. Combined with the self-hosted wedge
(HIPAA/legal privacy routing that no incumbent addresses), the score
lifted from 17→19/25.

## Lesson for future research

This pattern — a funded startup pivoting out of a category without an
announcement — is likely common in fast-moving AI markets. Always verify
competitors via browser homepage before citing them as active. Do not
rely on stale comparison data or VC announcements.
