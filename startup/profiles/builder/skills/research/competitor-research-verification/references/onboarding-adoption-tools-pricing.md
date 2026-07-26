# Verified Pricing: Customer Onboarding / Digital Adoption Tools
# Captured 2026-07-24 — re-verify if citing months later.
# Reusable for any onboarding, in-app-guidance, DAP, or adoption dossier.

## Extraction methods used (see SKILL.md Step 3 for the technique)
- **JSON-LD** (schema.org Offer blocks in raw HTML): Intercom, Userflow
- **curl + regex** on rendered HTML: Userpilot, HelpHero, Chameleon, Candu, Loom, Notion, Zapier, Scribe
- **browser_console** (JS-rendered, no server-side prices): Appcues, Stonly, Usertour, WalkMe
- **GitHub API**: intro.js, Usertour repo, Shepherd

## ENTERPRISE (dedicated onboarding / DAP)
| Tool | Pricing | Method | Source |
|------|---------|--------|--------|
| Intercom | Essential $39/seat/mo, Advanced $99/seat/mo, Expert $139/seat/mo; Fin AI $0.99/resolution | JSON-LD | intercom.com/pricing |
| Pendo | SALES-GATED (no public price; demo-only, MAU-based) | curl+browser | pendo.io/pricing |
| Userflow | Adoption Studio $500/mo ($400/mo annual); Adoption Agent $100/mo ($80/mo annual); 1K MAU base; 14-day free trial | JSON-LD | userflow.com/pricing |
| Appcues | SALES-GATED ("Book a call"). Tiers: Start (≤3K MAU), Grow (≥3K MAU), Enterprise, Spark (small teams — link 404s) | browser_console | appcues.com/pricing |
| ChurnZero | NO PRICING PAGE (/pricing/ returns 404). Demo-gated. | browser | churnzero.net/pricing |
| Whatfix | SALES-GATED. Page contains a $950,000 example contract figure. | curl | whatfix.com/pricing |
| WalkMe | SALES-GATED ("Request a quote"). Post-SAP-acquisition. | browser | walkme.com/pricing |

## MID-MARKET
| Tool | Pricing | Method | Source |
|------|---------|--------|--------|
| Userpilot | $299/mo, $849/mo | curl+regex | userpilot.com/pricing |
| HelpHero | $55/mo (1K MAU) → $115 (2.5K) → $179 (5K) → $249 (10K) → $299 (20K); Startup/Enterprise = contact | curl+regex | helphero.co/pricing |
| Stonly | SALES-GATED. Small Business tier defined (4K guide views, 5 members, <100 employees) but no $ | browser_console | stonly.com/pricing |
| Chameleon | $300/mo (Starter), $750/mo, $1,250/mo | curl+regex | trychameleon.com/pricing |
| Candu | $199/mo, $799/mo | curl+regex | candu.ai/pricing |
| Shepherd.js | Free (MIT-licensed JS library) | curl | shepherdjs.dev |
| Joyride | DEFUNCT — domain joyride.io does not resolve (ERR_NAME_NOT_RESOLVED); only HN trace is a 2016 post | browser | joyride.io |

## INDIE / OPEN-SOURCE
| Tool | Pricing | Method | Source |
|------|---------|--------|--------|
| Usertour.io | Hobby $0/mo (hobbyists), Starter $59/mo, Growth $119/mo, Business $249/mo. Open-source (2,106★). Cloud + self-managed. | browser_console | usertour.io/pricing |
| Scribe | Free; Pro $13/seat/mo; Team $25/seat/mo (annual). (Docs/SOPs, not in-app flows) | curl+regex | scribehow.com/pricing |
| Usetiful | ACQUIRED by Fullstory (Nov 3 2025); folded into enterprise platform. No longer indie. Pricing page redirects to fullstory.com. | browser | usetiful.com/pricing |
| intro.js | Free (MIT), 23,480★. Code library, not a product. | GitHub API | github.com/usablica/intro.js |

## FOUNDER WORKAROUND STACK (the de facto "indie onboarding market")
| Tool | Pricing | Method | Source |
|------|---------|--------|--------|
| Loom | Free (25 vids); Business $18/user/mo; Enterprise $24/user/mo | curl+regex | loom.com/pricing |
| Notion | Free; Plus $10/seat/mo; Business $20/seat/mo | curl+regex | notion.so/pricing |
| Zapier | Free (100 tasks); Starter $19.99/mo; Pro $33.33/mo; up to ~$103/mo | curl+regex | zapier.com/pricing |

## Price-ladder / gap note
Dedicated onboarding tools floor at $55/mo (HelpHero, tours-only) → $59 (Usertour, dev-focused) → $199–300 (Candu/Chameleon/Userpilot) → $500 (Userflow) → sales-gated (Pendo/Appcues/Stonly/Whatfix/WalkMe). The cobbled founder stack (Loom+Notion+Zapier) costs $30–70/mo in aggregate but is components, not one automated onboarding system. A clear unoccupied gap sits at $20–50/mo for a self-serve, multi-channel onboarding automator. The indie tier is contracting (Usetiful acquired upmarket, Joyride dead), widening rather than filling the gap.
