# Walmart API Landscape (as of 2026-07)

Walmart operates **three distinct API surfaces** that are easy to conflate.
Each has different auth, different access requirements, and different
capabilities. This map was verified by browsing the live sites.

## 1. Walmart Marketplace Developer Portal — `developer.walmart.com`

- **Purpose:** APIs for sellers to manage their own Walmart.com listings.
- **Audience:** Marketplace sellers, solution providers, 1P suppliers,
  transportation carriers, advertising partners.
- **API categories (verified from API Reference):** Authentication &
  Authorization, Advertising (SEM: campaigns/catalog/diagnostics/reporting),
  Assortment Recommendations, Claims, Disputes, Feed Management, Fulfillment,
  Insights, Inventory Management, Item Management, Lag Time, Notifications,
  On Request Reports, Order Management, Payments, Payment Reports,
  Price Management, Promotion Management, Returns, Recommendations,
  Reviews Acceleration, Settings, Ship With Walmart, Walmart+, Simulations.
- **Price Management:** Write-only (PUT/POST to *set* prices on own SKUs).
  Does NOT browse competitor or catalog prices.
- **Access:** Requires a Walmart Marketplace Seller account.
- **NOT suitable for:** Grocery price comparison / catalog browsing.

## 2. Walmart I/O — `www.walmart.io` (developer/affiliate platform)

- **Purpose:** Developer portal hosting affiliate and commerce APIs.
- **APIs listed (from homepage):** Affiliate API, Buy Now SDK, Partner API,
  OPD API (Online Grocery Pickup & Delivery — likely), I2P Mapping API.
- **Affiliate API docs:** `https://www.walmart.io/docs/affiliate/`
  (SPA — did not render headless; could not extract endpoint specs).
- **OPD API docs:** `https://www.walmart.io/docs/opd/`
  (SPA — did not render; may be the closest thing to a "grocery API").
- **API reference index:** `https://www.walmart.io/apirefservices`
  (returned Forbidden when accessed without auth).
- **Onboarding:** `https://www.walmart.io/onboarding` — free; uses a
  Walmart.com account; choose "Affiliate path" or "Developer path";
  requires uploading a public/private key pair.
- **Auth:** Public key upload linked to an application; API key issued.
- **Note:** Bare `walmart.io` returned Forbidden; `www.walmart.io` worked.

## 3. Walmart Affiliate Program — `affiliates.walmart.com`

- **Purpose:** Earn commissions by linking to Walmart.com products.
- **Management:** Via **Impact Radius** (affiliate service provider).
- **Cost:** Free to join; approval "within a day."
- **Commission:** 1–4% on qualifying sales; 3 return days (cookie window).
- **Deliverables:** Weekly newsletter, banner ads, text links, **data feeds**
  with product info, Affiliate Member Center access.
- **API:** The `/api` path on affiliates.walmart.com errored. API access
  routes through Walmart I/O (platform #2 above), not the affiliate site.
- **FAQ:** `https://affiliates.walmart.com/faqs`
- **Benefits:** `https://affiliates.walmart.com/page/benefits`

## Grocery-specific findings

- **No public, documented "Walmart Grocery API" was found.**
- Walmart merged its standalone Grocery app/site into the main Walmart.com
  experience in 2020.
- The **OPD API** on Walmart I/O may relate to grocery pickup/delivery but
  its docs did not render (SPA).
- The Affiliate API covers the **Walmart.com online catalog**, which includes
  online groceries, but no documentation confirms **store-level pricing**
  (Neighborhood Market vs. Supercenter). Online prices likely differ from
  in-store prices.
- **Unconfirmed:** exact rate limits, response schema fields, grocery
  coverage breadth. These live behind the SPA docs that didn't render.

## Source URLs (all verified loadable except SPA docs)

| Surface | URL | Status |
|---|---|---|
| Marketplace Developer Portal | `https://developer.walmart.com/` | Loaded, server-rendered |
| Marketplace API Reference | `https://developer.walmart.com/` → API Reference | Loaded |
| Walmart I/O (developer) | `https://www.walmart.io/` | Loaded (use www. prefix) |
| Affiliate API docs | `https://www.walmart.io/docs/affiliate/` | SPA, did not render |
| OPD API docs | `https://www.walmart.io/docs/opd/` | SPA, did not render |
| API reference index | `https://www.walmart.io/apirefservices` | Forbidden without auth |
| Onboarding | `https://www.walmart.io/onboarding` | Loaded, server-rendered |
| Affiliate Program home | `https://affiliates.walmart.com/` | Loaded |
| Affiliate FAQ | `https://affiliates.walmart.com/faqs` | Loaded |
| Affiliate benefits | `https://affiliates.walmart.com/page/benefits` | Loaded |
