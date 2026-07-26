# Verified Competitor Pricing — iPaaS / SMB Automation / CRM Tools

> Captured 2026-07-24 for the "SMB Cross-Platform Data Sync" dossier.
> Reusable for any data-sync, integration-platform, SMB-automation, CRM, or
> "zero-config automation" dossier. Re-verify if citing months later.

## iPaaS (integration platforms) — the "too complex for SMBs" cluster

| Tool | Tiers (live-verified unless noted) | Source / access method | Caveat |
|------|------------------------------------|------------------------|--------|
| **Zapier** | Free $0/mo (100 tasks), Professional $19.99/mo, Team $69/mo, Company custom. Add-ons: Agents Pro $33.33/mo ($400/yr), Chatbots from $13.33/mo. | zapier.com/pricing — curl + desktop UA, prices in raw HTML (strip `<script>` first) | Server-rendered; curl works. |
| **n8n** | Starter €20/mo (~2.5k executions), Pro €50/mo (10k executions), Business €667/mo (40k executions), Enterprise contact sales. Start-up Plan: 50% off Business (<20 employees). Community Edition: free, self-hosted. | n8n.io/pricing — **JS-rendered; curl returned NO € amounts.** Extracted via browser snapshot. | Always use browser for n8n pricing, not curl. Own tagline: "for technical teams." |
| **Make.com** (formerly Integromat) | **COULD NOT VERIFY LIVE.** Cloudflare-blocked for curl ("Just a moment...") AND headless browser. G2/GetApp also 403. Publicly documented: Free (1,000 ops), Core ~$10.59/mo (10k ops), Pro ~$18.82/mo, Teams ~$34/mo. | make.com/en/pricing — BLOCKED | Cite as "publicly documented, could not verify live." Re-verify later. |
| **Workato** | No public pricing — "Contact Sales" / "Book a demo" only. Enterprise iPaaS. | workato.com/pricing — curl, page loads, no prices | Enterprise-only; not SMB-accessible. |
| **Tray.io** | No public pricing — "Contact sales" / "Enterprise" only. JSON-LD: `"price":"Contact sales"`. | tray.io/pricing — curl | Enterprise-only; pivoted from SMB no-code to enterprise embedded integrations. |

## SMB CRM tools (the lock-in / overpayment cluster)

| Tool | Tiers (live-verified unless noted) | Source / access method | Caveat |
|------|------------------------------------|------------------------|--------|
| **Keap** (formerly Infusionsoft) | **Starts at $249/mo ($2,988/yr).** Plus messaging add-ons ($24–$279/mo tiered by SMS/text volume) and $299 early-termination fee. | keap.com/pricing — curl + desktop UA; prices in HTML + `<meta name="description">` | The $24–$279 are *messaging add-ons*; the main CRM plan is $249/mo. Don't conflate. Confirms the r/smallbusiness "$3,000–4,000/yr overpayment" complaint. |
| **HubSpot** | Free $0/mo (up to 2 users, all hubs' free tools), Starter $7–$20/mo/seat (discounted promo; 1,000 marketing contacts), Pro/Enterprise $800–$3,600+/mo. HubSpot Credits: $9/1,000 credits for AI agents. | hubspot.com/pricing/crm — browser snapshot | Free tier is a lead-gen funnel to expensive hubs. |
| **Pipedrive** | **COULD NOT VERIFY LIVE.** Cloudflare-blocked for curl AND browser ("Sorry, you have been blocked"). Publicly documented: Essential ~$14/mo, Advanced ~$29/mo, Professional ~$49/mo, Power ~$64/mo, Enterprise ~$79/mo/seat. | pipedrive.com/en/pricing — BLOCKED | Cite as "publicly documented, could not verify live." |

## AI-native automation tools (the emerging cluster)

| Tool | Tiers (live-verified unless noted) | Source / access method | Caveat |
|------|------------------------------------|------------------------|--------|
| **Bardeen** | Basic $10/mo (100 credits/mo), Premium (annual, custom credits), Enterprise contact sales. | bardeen.ai/pricing — browser snapshot | GTM/sales-focused (lead sourcing, prospecting), NOT general SMB sync. |
| **Magical** | **Enterprise — no self-serve pricing ("Book a demo").** | getmagical.com — browser snapshot | **[PIVOT DETECTED — see `references/magical-healthcare-pivot-example.md`]** Magical pivoted entirely from SMB autofill/data-entry to "AI Agents for Healthcare Operations." The SMB product is gone. A named AI-native competitor vacated the SMB segment. |
| **Multiway** | Could not verify — site timed out. | multiway.ai — timeout | Flag for follow-up. |

## Key positioning insights for SMB data-sync / automation dossiers

- **Whitespace price band:** $15–$39/mo for a standalone SMB sync tool. Below Keap ($249/mo, which owners complain is too expensive) and above the "free CRM" expectation (HubSpot free) that kills monetization. Zapier's $19.99/mo is the reference "automation tool an individual pays for."
- **The "too complex" gap is structural, not feature-level.** Zapier/Make/n8n ALL require building workflows — integration engineering non-technical SMB owners won't do. n8n's own tagline is "for technical teams." Simplifying to zero-config would undercut their power-user base, so they're structurally slow to serve this segment.
- **CRMs solve sync via lock-in, not openness.** Keap ($249/mo, termination fee) and HubSpot bundle CRM+invoicing but only if you adopt their whole stack. The gap is a neutral sync layer across the tools the owner already has.
- **Enterprise iPaaS (Workato, Tray) is irrelevant to SMB.** No self-serve, opaque pricing, sales-led. Include for landscape completeness, not as a real SMB competitor.
