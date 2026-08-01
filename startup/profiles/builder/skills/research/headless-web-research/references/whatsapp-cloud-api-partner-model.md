# WhatsApp Cloud API — Partner Model & Access Architecture

Captured 2026-08-01 via Meta official documentation (developers.facebook.com +
business.whatsapp.com). Reusable for any WhatsApp-messaging, shared-inbox,
DTC-support, or WA-CPaaS venture dossier. Complements the
`whatsapp-bsp-competitor-pricing.md` reference under the `venture-research`
skill (which covers competitor pricing + per-message economics — the two
references together cover the full WA integration picture).

## The core fact: BSP is NOT required for the Cloud API

The "BSP required" model is a **legacy of the deprecated On-Premise API**,
which required hosting your own client and provisioning through a BSP. The
On-Premise API is end-of-life.

The **Cloud API** (Meta-hosted, launched 2022) is directly accessible to any
developer. Businesses self-register via Meta Business Manager / App Dashboard.
This is the single most common point of confusion in the WhatsApp integration
space — much older advice and many vendor docs still say "you need a BSP."

### Self-registration path (confirmed live 2026-08-01)

Meta's "Cloud API Get Started" documents a fully self-service flow:
1. Facebook account + developer registration
2. Create a Meta app with the "Connect with customers through WhatsApp" use case
3. Create or select a WhatsApp Business Account (WABA)
4. Generate a system user access token

No BSP involvement at any step.

## The modern partner tier model (Tech Provider / Tech Partner / Solution Partner)

Source: https://business.whatsapp.com/partners/become-a-partner (feature matrix,
verified live 2026-08-01). The successor concepts to "BSP":

| Capability | Tech Provider | Tech Partner | Solution Partner |
|---|---|---|---|
| Direct API access | Yes | Yes | Yes |
| Manage business's account / act on behalf (send messages, manage templates) | Yes | Yes | Yes |
| Onboard businesses via Embedded Signup | Yes | Yes | Yes |
| Partner program incentives | No | Yes | Yes |
| **Manage billing via line-of-credit sharing** | No | No | **Yes** |

**Key takeaway:** The ONLY capability exclusive to a Solution Partner (the
modern BSP — 360dialog, Twilio, MessageBird, etc.) is line-of-credit billing
(consolidate messaging costs, resell at markup). Everything else is available
to a Tech Provider directly. Any developer becomes a Tech Provider by default.

### Progression
Third Party Developer -> Tech Provider -> Tech Partner (must onboard as Tech
Provider first, then self-initiate upgrade). Solution Partner is a separate
track requiring Meta application.

## Recommended architecture for a multi-tenant WhatsApp SaaS (shared inbox)

You do NOT need to partner with a BSP. The correct path:

1. **Become a Tech Provider** (default for any developer).
2. **Use Embedded Signup** — Meta's official onboarding flow. Each customer
   connects their own WABA to your app from within your UI. It returns the
   customer's WABA ID, phone number ID, and an exchangeable token. The customer
   retains ownership of their WhatsApp assets (and keeps full WhatsApp Manager
   access — you cannot restrict it).
3. **Billing:** As a Tech Provider, each customer adds their own payment method
   directly to their WABA via Meta. You don't handle Meta's billing.

### Onboarding limits (Embedded Signup)
- Default: 10 new business customers in a rolling 7-day window.
- After Business Verification + App Review + Access Verification: 200/week.
- Beyond 200/week: apply to become a Meta Business Partner.

### Direct vs BSP trade-off (decision guide)
- **Direct (Tech Provider + Embedded Signup):** Each customer owns their WABA,
  adds their own card to Meta, no billing risk/margin on message costs. Best
  for early-stage. Onboarding limits scale with verification.
- **Via BSP/Solution Partner (360dialog etc.):** They handle line-of-credit
  billing (you can mark up messaging), higher throughput/limits faster, support
  included — but you pay their markup and add an intermediary. They also
  abstract some Meta app review/verification complexity.

## Meta docs URL restructure (navigation fact)

Meta restructured developer docs in 2026. Old paths under
`developers.facebook.com/docs/whatsapp/...` now frequently 404. The canonical
live path is `developers.facebook.com/documentation/business-messaging/whatsapp/...`.
Redirects are unreliable — if a `/docs/whatsapp/...` URL 404s, try the
`/documentation/business-messaging/whatsapp/...` equivalent. Confirmed
2026-08-01 (partners/ and onboarding-for-tech-providers/ old paths both 404).

## Verified source URLs (live 2026-08-01)

1. **Cloud API Get Started** (confirms self-service registration)
   https://developers.facebook.com/docs/whatsapp/cloud-api/get-started
2. **About the WhatsApp Business Platform** (Cloud API vs Business Management API)
   https://developers.facebook.com/docs/whatsapp/cloud-api/overview
3. **Embedded Signup** (customer-onboarding flow; Tech Provider vs Solution
   Partner billing requirements)
   https://developers.facebook.com/docs/whatsapp/embedded-signup
4. **Become a Partner** (feature-matrix table)
   https://business.whatsapp.com/partners/become-a-partner
