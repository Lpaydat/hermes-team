# WhatsApp BSP / Shared Inbox — Competitor Pricing & Landscape

Captured 2026-07-23 via direct curl/browser of pricing pages. All prices
verified live unless noted otherwise. Reusable for any WhatsApp-messaging,
shared-inbox, or DTC-support venture dossier.

## WhatsApp Business API economics (the underlying layer)

Source: wexio.io/blog/free-whatsapp-business-api + HN thread
news.ycombinator.com/item?id=48504753 (28 pts, 2026-06-12).

- **Per-message billing since July 2025** (replaced per-24h-conversation model).
- **4 message categories:** Marketing, Utility, Authentication, Service.
  Rate varies by country AND category.
- **Service conversations are FREE** — your replies inside a customer-initiated
  24-hour window cost nothing.
- **First 1,000 customer-initiated service conversations each month are FREE.**
- **Country variance is huge:** India ~$0.0094/msg vs Germany ~$0.124/msg
  (HN comment by /u/Puvvl).
- **BSP (Business Solution Provider) markup** is the hidden cost layer: vendors
  charge a platform fee + mark up Meta's per-message rate. Wati ~2x Meta rate;
  360dialog ~$0.005/conversation over Meta; Meta-direct = no markup but no UI.
- **Meta Business Manager onboarding is a major friction cliff** — HN consensus
  ("clusterfuck," "maze of config pages," painful verification). Any product
  targeting non-technical SMBs must absorb this step (concierge onboarding).

## Real all-in cost comparison (2,000 WA conversations/mo, 3 agents, AI on 30%)

Source: wexio.io/blog/wati-alternatives (2026-07-23).

| Provider | Platform fee | Conversation cost | AI cost | Total/mo |
|---|---|---|---|---|
| Wexio (Standard) | $16 | Meta rate (~$18 India mix) | OpenAI direct (BYOK) ~$5 | ~$39 |
| AiSensy (Pro) | $19 | Bundled low markup | Included | ~$45 |
| 360dialog | $0 | $18 Meta + $10 360 fee | Own | ~$30 |
| Interakt (Standard) | $12 | Bundled | Included basic | ~$35 |
| Wati (Growth) | $49 | Bundled ~2x Meta | Wati AI add-on $30 | ~$130 |
| respond.io (Team) | $79 + seats | Bundled | Bundled | ~$220 |
| Twilio | $0 | $18 Meta + $10 Twilio | Own | ~$30 |
| Meta Direct | $0 | $18 Meta | Own | ~$18 |

## Named competitors — verified pricing

| Competitor | What it does | Pricing (verified live 2026-07-23) | Positioning |
|---|---|---|---|
| **Wati** | WA-first shared inbox + chatbots + broadcast + Shopify. Asia-focused. | Growth **$39/mo** (1 channel, 3 users, NO add'l users), Pro **$79/mo** (5 users, +$24/user), Business **$199/mo** (5 users, +$59/user) — billed annually. Shopify add-on $4.99/mo. Extra WA number $29/mo. **Source: wati.io/pricing (browser-verified — JS-rendered, curl gets `$ -`).** | Agency / broadcast-marketing. Real all-in ~$130-400/mo. |
| **respond.io** | Omnichannel inbox (WA, IG, Messenger, web, email, Telegram) + AI agents. Malaysia-based. Raised **$62.5M** June 2026 (TechCrunch). | Starter **$79/mo**, Growth **$159/mo**, Advanced **$279/mo**, Enterprise custom — billed yearly. Add'l users $12-24/mo. MAC-metered (Growth starts 1,000 contacts, +$15/100 overage). **Source: respond.io/pricing (curl-verified).** | Up-market omnichannel. Expanding NA/Europe with fresh capital. |
| **Trengo** | Omnichannel team inbox + helpdesk. Dutch, EU focus. | Boost **€299/mo** (10 users, annual; €349 m-t-m), Pro **€499/mo** (20 users; €599 m-t-m), Enterprise custom. **Source: trengo.com/pricing (curl-verified — note: /en/pricing 404s, use /pricing).** | Mid-market / enterprise. Inaccessible to SMB. |
| **Wassenger** | WA-only shared inbox + automation. | Could not verify pricing page this session. Reddit user /u/flavia (r/smallbusiness `1uti90c`) confirmed it as their switch-from-shared-phone solution. | WA-only niche player. |
| **Interakt** | India WA shared inbox + Shopify. | Standard ~$12/mo (per wexio comparison). | India-focused, low end. |
| **AiSensy** | India WA shared inbox. | Pro ~$19/mo (per wexio comparison). | India-focused, low end. |
| **DelightChat** | India WA shared inbox + Shopify. | Typically $40-60/mo (industry-known; could not re-verify live this session). | India-focused. |
| **WhatsApp Business app (free)** | Meta's free SMB app: 1 number, quick replies, catalog, labels. | Free | The incumbent everyone flees FROM. No shared inbox. WA Business ~200M monthly users (2023, Wikipedia). |
| **Meta Cloud API / 360dialog / Twilio** | Raw WA API access, no inbox UI. | $0-10 platform + Meta per-message rate. | Infrastructure, not product. Enable builders. |

## Market size signals

- **WhatsApp: 3 billion MAU** (May 2025, Wikipedia).
- **WhatsApp Business: ~200 million monthly users** (2023, Wikipedia).
- **respond.io $62.5M raise** (June 2026, TechCrunch) validates the category
  is large and well-funded.
- WA-dominant markets (where the DTC-on-WhatsApp pain concentrates): India,
  Brazil, Indonesia, MENA, LatAm, parts of Europe. NOT the US (SMS/iMessage
  dominate there).

## Key HN threads (reusable signal library)

| Topic | HN ID | Points | Date | Use |
|---|---|---|---|---|
| WA Business API pricing 2026 (free vs markup) | 48504753 | 28 | 2026-06-12 | WA cost structure, Meta Business Manager pain |
| Why is WhatsApp API so bad? (24h window, webhooks) | 40181170 | 3 | 2024-04-27 | WA API constraints / hard parts |
| respond.io $62.5M raise | 48565275 | 2 | 2026-06-17 | Market validation |
| Wati alternatives real all-in cost | 48220557 | 2 | 2026-05-21 | Competitor cost analysis (→ wexio.io) |
| Fiwano unified messaging API (inbox price floor) | 48673261 | 1 | 2026-06-25 | "$60-200/mo" inbox floor quote |
| WhatsApp Personal Shopper for Shopify | 44129774 | 2 | 2025-05-29 | WA+Shopify validation |
