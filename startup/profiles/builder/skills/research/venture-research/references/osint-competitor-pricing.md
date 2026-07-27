# OSINT Competitor Pricing & Landscape

Captured 2026-07-23 via direct curl of pricing pages. All prices verified
live unless noted otherwise. **Re-verified and corrected 2026-07-23** (second
pass during the OSINT Desk dossier build).

## Enterprise OSINT Platforms (sales-gated pricing)

| Competitor | Pricing Model | Notes |
|---|---|---|
| **Maltego** | Community €0/yr, **Entry €3,000/yr** (10,000 credits), **Professional €7,500/yr** (20,000–40,000 credits, Standard/Advanced variants), Enterprise = contact sales | Source: maltego.com/pricing (live, 2026-07-23, server-rendered HTML — extractable via curl+regex, no browser needed). Credit-bundled tier structure confirmed from HTML. Page itself states Entry/Professional are "great for individual investigators." |
| **SocialLinks** | Contact sales / book demo | sociallinks.io — "book a demo" only, no public pricing (verified 2026-07-23) |
| **Echosec** | Contact sales / book demo | echosec.net — "Get a Demo" only |
| **Flashpoint** | Contact sales / book demo | flashpoint.io — claims "$500M fraud loss avoided/year," "482% ROI in 6 months," "saves $80M in fraud losses per year" (per customer testimonials) |
| **Intel 471 (acquired SpiderFoot)** | "Let's Talk" only — **no public pricing; former pricing page is a confirmed 404** | intel471.com. IMPORTANT CORRECTION: spiderfoot.net/pricing does NOT redirect — it now returns Intel 471's **404 page** (verified 2026-07-23 via headless browser). The affordable/free SpiderFoot path has been removed entirely. "Verity471" SaaS platform, cyber threat intelligence focus. |
| **Overwatch (YC S22)** | Contact sales | OSINT platform for cyber and fraud risk. HN Launch: news.ycombinator.com/item?id=40659236 (164 pts, 89 comments, 2024-06-12). Founders describe incumbent tools as "very expensive, noisy, keyword-based." Commenter explicitly asked: "Would this be a service you would ever offer to regular researchers?" — confirming prosumer demand the enterprise tier ignores. |

## Individual / Prosumer OSINT Tools

| Competitor | Pricing | Notes |
|---|---|---|
| **IntelTechniques** | Certification training + free search tools | inteltechniques.com by Michael Bazzell. OSIP (Open Source Intelligence Professional) certification. Individual-focused, privacy-remediation angle. Live 2026-07-23: site confirms "OSIP" + "certif" + "training" present; no product SaaS pricing. |
| **Hunchly** | Could not verify — **SSL failures from curl AND headless browser** | ~$129-179/yr per user (web capture for investigations) per industry reporting. Acquired/bundled by Maltego as of 2024. IMPORTANT: hunchly.com fails with `net::ERR_SSL_PROTOCOL_ERROR` from both curl AND browser_navigate (confirmed twice, 2026-07-23) — do not spend cycles retrying; cite as unverifiable-live. |

## Free / Open Source OSINT Tools

| Tool | What it does | HN Signal |
|---|---|---|
| **SpiderFoot** | OSINT collection/recon (open source) | 272 pts (2020), but "currently not in working condition" per 2024 HN comment. Maintained version now under Intel 471 (pricing page 404 — see above). |
| **GHunt** | Extract info about Google accounts | 247 pts, 39 comments (2020-10-03). Note: many features broken by Google API changes. HN comment: "Doesn't really work for Google accounts that have reasonable privacy configuration." |
| **Web-check** | All-in-one website OSINT analysis | 80 pts (2024-07-27). GitHub: Lissy93/web-check. Criticized as "surface level" (verbatim HN quote). |
| **theHarvester** | Emails, subdomains, names harvester | 90 pts (2021). |
| **Osgint** | Find info about GitHub users | 116 pts, 26 comments (2025-03-24). Criticized: "Who does this benefit besides spammers?" / "Just as recruiters were stopping to spam me via GitHub." |

## Key Market Signals (from HN) — verified thread IDs

All IDs verified live 2026-07-23 via HN Algolia API. Reusable across OSINT dossiers.

1. **Shadowbroker — real-time OSINT dashboard** — 312 pts, 123 comments, 2026-03-08. `47300102`. GitHub: BigBodyCobain/Shadowbroker. Founder: "I got tired of bouncing between Flightradar, MarineTraffic, and Twitter every time something kicked off globally." Top comment (laborcontract): "I've seen so many of these in the last week alone. I need a realtime OSINT dashboard for OSINT dashboards." — market is forming.

2. **"Slow collapse of critical thinking in OSINT due to AI"** — 446 pts, 231 comments, 2025-04-03. `43573465`. Signals that AI-powered OSINT tools are entering the market but quality/verification is a concern. Gold quote (jruohonen): "Instead of forming hypotheses, users asked the AI for ideas. Instead of validating sources, they assumed the AI had already done so." Adjacent 20-yr-analyst comment `43582930`: "OSINT is much more accessible... there are a lot of people who CAN be OSINT analysts or call themselves that and are not professionally trained... especially if they are using expensive tools."

3. **OSINT tools directories are a recurring side project** — 3+ Show HN posts in 2024-2026. OsintRadar `47646504` (83pts, 2026-04-05); R00M 101 `44178780` (53pts, 2025-06-04). Comment pattern (verbatim): "generally useless," "biased towards US," "wrappers/aggregators on other services." R00M 101 founder: "most open-source intelligence tools are scattered across GitHub, outdated blog posts, or random Discords."

4. **Optery (YC W22)** — 223 pts, 2022-03-08. `34245102`. Data removal service (the inverse of OSINT). Validates the personal data ecosystem. "I would definitely pay for the removal of arrest record listings."

5. **Enterprise vs prosumer gap**: All 6 funded platforms gate pricing behind "contact sales" / "Let's Talk." Cheapest usable (Maltego Entry) is €3,000/yr. The free/open-source tools are fragmented, US-centric, and criticized as "surface level." This is the whitespace — the thesis behind the OSINT Desk dossier (20/25).

## Adjacent Industries for TAM Estimation

- **Private investigators** (BLS data): Could not fetch from bls.gov this session.
- **Data broker / people search**: Sites like Radaris, WhitePages, PeekYou — validated as massive by Optery's YC launch.
- **Cyber threat intelligence**: Flashpoint, Intel 471, Recorded Future — enterprise market, multi-billion dollar.
