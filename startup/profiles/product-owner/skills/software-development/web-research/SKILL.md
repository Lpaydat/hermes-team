---
name: web-research
description: Investigate a question against high-trust primary sources on the live web and capture the findings as a traceable Markdown file in the repo. Use when the user wants a topic researched, wants docs or API facts gathered, wants to compare approaches/tools/vendors, wants architecture or engineering-practice precedent, asks "how do real systems handle X", "what's the best way to do Y", "compare A vs B", or wants reading legwork done against authoritative sources rather than the model's priors. Reach this skill instead of answering from memory whenever the claim is load-bearing and a primary source exists.
---

Investigate a question against **primary sources** — official docs, source code, specs, first-party APIs, authoritative books/papers — not a secondary write-up of them. Follow every load-bearing claim back to the source that owns it. The goal is a findings file a reviewer (or future you) can trust without re-reading the sources: **short verbatim quotes + source URLs inline**.

## When to reach this skill

Reach it instead of answering from your own priors whenever the answer is **load-bearing** — it will justify a design decision, a build, a vendor choice, or a claim about how the world works — *and* a primary source exists. If it's a quick factual lookup your training covers confidently, just answer.

## Steps

1. **Name the primary sources before you fetch.** List which sources would be authoritative for this question (official docs for a tool's behaviour; the vendor's own blog for their architecture; a foundational book/paper for an established practice; the RFC/spec for a protocol). If you can't name a candidate primary source, say so and fall back to the best available secondary sources, labelling them as such.

2. **Gather in parallel, serialize on dependency.** Open independent sources concurrently. Only serialize when one source's URL/path depends on another's result (e.g. a chapter link found inside a book's TOC). For web sources, use the browser tools — their mechanics are in [`references/web-research-tactics.md`](references/web-research-tactics.md) and they materially speed up a pass (truncated snapshots, navigating dense doc pages, paywalled/moved sources). When you have many candidate URLs to screen (restructured docs, mirror triage), batch-probe them with [`scripts/probe-urls.sh`](scripts/probe-urls.sh) (tactics §9) before committing to full fetches.

3. **Quote the decisive facts, cite the source.** For each claim that drives the conclusion, capture a short verbatim quote + the source URL inline in the findings file. Quotes are what make the analysis defensible. Reserve full-paragraph quotes for the 2-4 most decisive claims; paraphrase + cite the rest.

4. **Compare and synthesize, don't just transcribe.** The deliverable is a comparison/recommendation, not a link dump. Lay out the approaches, their tradeoffs, who actually uses each, and a decision matrix. Mark any claim you couldn't trace to a primary source as such rather than papering over it.

5. **Save where the repo keeps such notes; say where.** Match the existing convention — repo has `docs/adr/` for decisions, top-level `*-analysis.md` / `*-research.md` for research writeups → put research at the top level, not in `docs/adr/`. If there's no convention, put it somewhere sensible and tell the user the path.

## Source-ranking fallback ladder

When the ideal primary source is unavailable, drop one rung — **don't** silently substitute a secondary blog for a primary source:

1. **First-party primary** — official docs, spec/RFC, the org's own engineering blog, the book/paper itself.
2. **Official open mirror** — same authors/org hosting the same content openly (e.g. a paywalled ACM paper mirrored on `research.google/pubs`; a book's free CC-licensed HTML edition on the publisher's imprint site). Verify it's first-party before citing as primary.
3. **Authoritative secondary** — a respected practitioner/community source that itself cites primaries (e.g. trunkbaseddevelopment.com). Label it as secondary in the findings.

**Copyrighted books with no free full text** break the ladder's assumption that rung 1 is fetchable. For paywalled books (Ousterhout, Hunt & Thomas, Bryar & Carr) there is no official open mirror and no free edition. Cite the book for authority (title/author/chapter/year), paraphrase from established knowledge when confident (never present a paraphrase as a verbatim quote), corroborate with an open source (author's course page, conference talk, publisher page, Wikipedia), and note the access gap in the findings. See [`references/web-research-tactics.md`](references/web-research-tactics.md) §11.

## Completion criterion

Every decisive claim in the findings file carries a short verbatim quote (or an explicit "no primary source found") and a source URL. A reviewer could spot-check any conclusion against its cited source in one click.
