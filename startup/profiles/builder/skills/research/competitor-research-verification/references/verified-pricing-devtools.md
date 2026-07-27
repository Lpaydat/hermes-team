# Verified Pricing — Developer Tools / AI Coding (2026-07-25)

Live-verified pricing for AI-coding, code-quality, code-review, and adjacent
developer-tool ventures. Captured 2026-07-25 by scraping live pricing pages
with curl + regex on server-rendered HTML (CodeRabbit, SonarQube, Cursor,
Sourcery all SSR cleanly; Qodo is JS-rendered and needs the browser path).
Reusable for any devtools, AI-coding-assistant, code-quality, or developer-
platform dossier. **Re-verify before quoting in a new dossier** — pricing drifts.

## The settled band

The market has converged on **$12–$48 / seat / month** for AI-adjacent
code-quality / review SaaS. Use this band to sanity-check a new venture's
pricing. Specialized or niche tools sit at the low end; AI-native or
enterprise-feature tools at the high end.

- **Floor (free / OSS):** ESLint, Prettier, standard linters. Commoditized
  quality tooling is free — a new tool must justify why it is not just a linter.
- **AI code review / quality:** $12–$48/seat/mo (CodeRabbit, Sourcery, Qodo).
- **AI coding itself (often the *cause* of the quality problems a new tool
  targets):** $20–$40/seat/mo (Cursor). This is the pricing anchor buyers
  implicitly compare against.

## Verified vendor prices

| Vendor | Category | Pricing (annual billing) | Model | Source / notes |
|--------|----------|--------------------------|-------|----------------|
| **CodeRabbit** | AI code review | Free (OSS) / **$24/seat/mo** (Pro) / **$48/seat/mo** (Pro Plus) / Enterprise (custom) | per-seat; PR reviews/hr rate-limited (5→10→12→custom) | coderabbit.ai/pricing — SSR, curl+regex works. Pro monthly $30, Pro Plus monthly $60. |
| **SonarQube Cloud** | Code quality / security | **$20–$25/user/mo** (Team, ≤50 users) / from **$34/mo** (100k LOC) / Enterprise (custom) | per-user + LOC tier | sonarsource.com/plans-and-pricing — SSR. Legacy LOC model coexists with per-user. |
| **Cursor** | AI coding (IDE / agent) | **$20/mo** (Pro) / **$40/user/mo** (Teams) / Enterprise | per-seat; usage-based options | cursor.com/pricing — SSR (Next.js; strip script tags before regex). |
| **Sourcery** | AI refactoring / review | **$12/seat/mo** (Pro) / **$24/seat/mo** (Team) / Enterprise | per-seat | sourcery.ai/pricing — SSR. Closest comp to a "refactor enforcement" tool. |
| **Qodo (CodiumAI)** | AI code review / testing | ~**$15–19/seat/mo** (Pro) | per-seat | qodo.ai — JS-rendered; verify via browser_console DOM query. |

## Extraction recipe (Tier 2 — curl + regex on SSR pages)

CodeRabbit / SonarQube / Cursor / Sourcery all server-render pricing in the
HTML. Cursor and CodeRabbit are Next.js, so raw `$\d` regex produces
false-positive matches inside `self.__next_f.push([1,...])` hydration JSON —
**strip `<script>` tags first** (the standard Next.js pitfall), then extract.
Qodo is fully JS-rendered and needs the browser (Tier 3) path.

```python
import re
html = open('page.html', encoding='utf-8', errors='ignore').read()
text = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.S|re.I)  # strip hydration blobs
text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.S|re.I)
text = re.sub(r'<[^>]+>', ' ', text)
text = re.sub(r'&[a-z]+;', ' ', text)
text = re.sub(r'\s+', ' ', text)
# dollar amounts with per-unit context
for m in re.finditer(r'[^.]{0,60}(?:per\s(?:seat|developer|user|month|PR|LOC)|\$[0-9]+)[^.]{0,90}', text, re.I):
    s = m.group(0).strip()
    if any(w in s.lower() for w in ['per ', '/mo', '/yr', '$', 'plan', 'billed', 'team', 'enterprise', 'free']):
        print(s[:160])
```

## Pricing-model patterns

1. **Per-seat dominates.** Every commercial dev-quality tool charges per
   developer/seat/month. LOC-based pricing (SonarQube) is a legacy pattern;
   per-seat is the modern default for new ventures.
2. **Free tier gated by repo type or rate limit**, not just a time-limited
   trial. CodeRabbit and Sourcery both gate a permanent free surface (OSS repos,
   limited rate). This is table-stakes for PLG distribution in devtools.
3. **Rate-limiting differentiates tiers**, not just features. CodeRabbit limits
   "PR reviews per developer per hour" (5 → 10 → 12 → custom) — a usage-aware
   way to tier without pure metering. Reusable pattern for any review/gate tool.
4. **Enterprise is always "talk to us."** SSO, on-prem, custom rules,
   unlimited repos — custom pricing. Don't try to price enterprise publicly.

## Pricing heuristic for a new devtools venture

- Default to **per-seat/month, annual billing** with a ~20% annual discount.
- Put the tool in the **$15–$30/seat/mo** (Pro) / **$30–$50** (Team/Ent) band
  unless there's a strong reason to deviate.
- Offer a **free tier gated by repo type (OSS) or rate limit**, not a trial
  alone — PLG adoption in devtools needs a permanent free surface.
- Anchor against the closest comp in the table above and justify any premium.
