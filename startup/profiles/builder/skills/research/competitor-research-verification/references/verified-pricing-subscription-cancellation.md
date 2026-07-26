# Verified Pricing & Signals — Subscription Cancellation / SaaS Rescue

**Verified:** 2026-07-25
**Reusable for:** any consumer-fintech, subscription-management, bill-negotiation, SMB SaaS-spend, or "cancel for you" dossier. Re-verify if citing months later — several players here are acquired/dead and status keeps shifting.
**Extraction methods used:** curl + HTTP/body-size checks; iTunes Lookup API (mobile apps); browser_navigate + browser_console (JS-rendered pricing).

## Live-verified pricing & status

| Competitor | Category | Pricing (live-verified 2026-07-25) | Status / Evidence |
|---|---|---|---|
| **Rocket Money** (rocketmoney.com) | Consumer — cancel + bill negotiation | **Free** + **Premium** (commission ~40% of savings; exact $/mo NOT published). Homepage HTTP 200, 643 KB. | Category leader. Self-reported: 10M+ users, $880M+ canceled, $2.5B+ saved (/about). Owned by Rocket Companies. |
| **Truebill** | Consumer (original pioneer) | — | **DEFUNCT.** Acquired by Rocket Companies for **$1.275B cash, Dec 2021** (HN 29626570, HousingWire/MarketWatch). |
| **Cushion** (cushion.ai) | Consumer — fee/bill negotiation | — | **DEFUNCT.** Acquired by LendingClub, April 2025. Tribute homepage: "2016–2025, AI-Powered Consumer Finance, Acquired by LendingClub." |
| **Trim** (trim.is / asktrim.com) | Consumer — bill negotiation | — | **APPEARS DEAD.** `trim.is` → HTTP 000 (DNS fail); `asktrim.com` → HTTP 403. Could not verify any live status. |
| **Bobby** (iOS, Yummygum) | Consumer — manual tracker | **Free** (iTunes lookup `id1059152023`). Pro IAP price not verified. | Tracking only; does not cancel. Own site was 401; verified via iTunes API. |
| **Subby** (iOS) | Consumer — manual tracker | **Free** (iTunes lookup `id6739703718`). | Tracking only. Category fragmented (multiple "Subby" apps). |
| **Capital One Eno** | Bank-native tracker | **Free** (cardholder). HTTP 200, 522 KB. | Tracking/alerting only — does not cancel. Locked to Capital One customers. |
| **Chase** (bank subscription insights) | Bank-native tracker | **Free** (bundled). HTTP 200, 339 KB. | In-app visibility only; no cancellation action. |
| **Vendr** (vendr.com) | SMB SaaS procurement | **No public price** — demo/quote only. | **Acquired → now Vertice.** `vendr.com/pricing` redirects to `vertice.one/pricing` (HTTP 200, 164 KB). Vertice markets "20%+ savings, 7x ROI." |
| **Tropic** (tropicapp.io) | SMB SaaS procurement | **No public price** — demo only. | **WATCH domain:** `tropic.com` is a UK skincare brand, NOT this tool. Markets "$425M savings, 21% avg, $23B+ spend data." Customers: Zapier, Notion, Strava. |
| **Cledara** (cledara.com) | SMB SaaS spend + cards | **LIVE (GBP):** Basic £75/mo, Premium £200/mo, Pro from £500/mo. Add-ons £150/mo each. Annual: Basic £750/yr, Premium £2,000/yr, Pro from £5,000/yr. | Spend management/cards, NOT cancellation. USD pricing requires in-app currency switch (not public). UK/EU-centric. |
| **Spendesk** (spendesk.com) | SMB spend management | **No public $ price** — "Request a free quote." Modular: Foundations + paid add-ons. | Cards/AP/procurement, not cancellation. |
| **Tally** (meettally.com) | Debt payoff (NOT subscriptions) | **Could not verify** — HTTP 403 bot-block. | OUT OF CATEGORY (credit-card debt, not subscriptions). |
| **Papercups** (papercups.io) | — | — | HTTP 404 — defunct/repurposed. Not in-category (was customer-messaging). |

## Key signals (for dossier evidence / "why now" sections)

- **FTC Click-to-Cancel rule finalized Oct 2024** (HN 41858665, 1747pts; passed 3-2 party-line) — then **struck down by US court July 2025** (HN 44505675, 227pts; The Guardian, 2025-07-08). Retention friction is legally protected to persist → a "cancel for you" agent is MORE valuable, not less.
- **Standalone consumer fee/bill-negotiation fintechs don't survive independently.** Truebill ($1.275B → Rocket), Cushion (→ LendingClub 2025), Trim (dead). They get absorbed by lenders/banks or die. Durable insight: negotiation-alone is a thin wedge; own the cancellation *action* end-to-end (incl. the retention-call gauntlet) instead.
- **Category leader (Rocket Money) is conflicted.** Owned by a mortgage/lending conglomerate; ~40%-of-savings commission is opaque; consumer-only; does NOT automate the hard retention cases (call/chat-bot required).
- **SMB SaaS-spend vendors (Vendr/Vertice, Tropic, Cledara, Spendesk) are all demo-gated procurement for Series B+ finance teams.** None cancels individual zombie seats; none serves sub-50-person SMBs; none fights the retention gauntlet. Pure whitespace for a self-serve SMB rescue tool.

## Cross-domain analog (strongest predictor)

**GDPR/CCPA data-deletion services** (DeleteMe ~$129/yr, Incogni ~$99/yr, Mine): a legal right + persistent merchant friction + an affordable done-for-you agent = a real subscription category. Same playbook, applied to cancellation instead of data deletion. Avoid the bill-negotiation-only failure mode (Trim/Cushion fate).

## Source references (all verified live 2026-07-25 unless noted)

| Source | URL / ID | Notes |
|---|---|---|
| Rocket Money homepage + about | rocketmoney.com, /about | HTTP 200; 10M users / $880M canceled / $2.5B saved |
| Truebill → Rocket acquisition ($1.275B) | HN 29626570, 29627281 | Dec 2021, cash |
| Cushion → LendingClub | cushion.ai | Tribute page, "Acquired April 2025" |
| FTC Click-to-Cancel finalized | HN 41858665 | Oct 2024, 1747pts |
| FTC Click-to-Cancel struck down | HN 44505675 | July 2025, The Guardian |
| FTC ban precursor | HN 35274519 | 2023, 919pts |
