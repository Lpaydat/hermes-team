---
name: competitor-research-verification
description: > 
  Live-verification techniques for researching competitors during venture
  dossier builds. Covers detecting competitor repositioning/pivots via
  browser, multi-source triangulation (GitHub landscape → HN funding →
  browser verification → pricing), and the pattern of cross-referencing
  known competitor claims against live evidence rather than citing stale
  comparison data.
tags:
  - research
  - competitor-analysis
  - market-research
  - due-diligence
---

# Competitor Research Verification

## When to use

- During the competitive-landscape section of any venture dossier
- After initial competitive scanning to verify each known competitor still
  exists in its stated category
- Before citing a competitor's pricing, funding, or product claims

## Core principle: verify every competitor live, every session

A competitor cited in a prior dossier, scan, or comparison table may have
pivoted, raised (or run out of) funding, changed pricing, or exited the
category entirely. The half-life of a startup competitor's positioning is
~6 months. Always verify before citing.

## Verification workflow

### Step 1: Cross-reference with HN Algolia for market presence

Search for the competitor name on HN to see their last significant signal
(funding announcement, launch, Show HN, or complaint):

```
curl -sL "https://hn.algolia.com/api/v1/search?query=COMPETITORNAME&tags=story&hitsPerPage=5"
```

Check: When was their last HN post? How many points did it get? If their
last appearance was 12+ months ago despite having significant VC funding
($9M+), a pivot or sunset is possible.

### Step 2: Browser homepage verification

After curl fails to return meaningful pricing/structure, use the browser
to check the homepage:

1. `browser_navigate("https://competitor.com")`
2. Read the accessibility tree snapshot — does the positioning match
   what you expect?
3. If skeptical, `browser_console(expression="document.body.innerText")`
   to see fully rendered content curl might have missed.

**Pivot signals:**
- Homepage describes a research lab, foundation, adjacent category, or
  completely different value proposition
- No pricing page exists (or redirects to a generic about page)
- No login / dashboard / "Get started" entry
- Messaging emphasizes research outputs (papers, blog posts) over product
- "About" section dominates over "Product" section

### Step 3: GitHub repo check (for OSS competitors)

If the competitor has an OSS project or SDK:

```
curl -sL -A "Mozilla/5.0" "https://api.github.com/repos/ORG/REPO"
```

Check for: stale commits (>6 months without push), archived repo, or a
README that describes a different product than expected.

### Step 4: Multi-source triangulation

Combine findings from Steps 1-3 into a verdict:

| Source | If healthy | If pivoted |
|--------|-----------|------------|
| HN Algolia | Recent launch/funding (last 6 mo) | No HN presence in 12+ mo |
| Browser homepage | Clear product + pricing | Research lab / switched category |
| GitHub activity | Active pushes in last 60 days | Archived or dormant (>6 mo) |

## Example: Martian detection (2026-07-24)

- **Known as:** Martian (withmartian.com) — model router startup, $9M raised
- **HN check:** Last HN post was low-engagement from May 2024 (2pts, 0c)
- **Browser check:** No model router product found; homepage described
  "Thesean AI" — an interpretability research lab studying "model minds"
- **GitHub:** No active router-related repos
- **Verdict:** Pivoted out of router category. This detection meaningfully
  thinned the competitive landscape for the AI Cost Optimization dossier,
  contributing to a score uplift from 17→19/25.

## Pitfalls

- Do NOT cite a competitor as an active market participant based on a
  stale comparison table or prior dossier. Always verify live.
- A short HTML body from curl does NOT mean the site is JS-rendered — it
  could mean there's nothing there anymore. Use the browser to distinguish.
- HN silence is not definitive proof of a pivot — some successful companies
  stop posting to HN. But combined with a homepage that no longer matches
  the expected category, it's strong evidence.
- If a competitor's homepage has a product tour + pricing + login but the
  messaging is stale/unchanged, they're likely still operating even if
  their HN presence is quiet.
- Funded competitors ($5M+) are more likely to pivot than shut down — they
  have the runway to try a new direction. Track their homepage, not just
  their Crunchbase profile.
