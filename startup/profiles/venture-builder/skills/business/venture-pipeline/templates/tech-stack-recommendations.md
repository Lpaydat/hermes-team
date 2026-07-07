# Tech Stack Recommendations (Prototype / MVP)

> Goal: fastest path to a testable hypothesis. NOT production architecture. Optimize for iteration speed, low setup cost, and the team's ability to change direction fast. Scale later — only after market validation.

---

## Selection Principles

1. **Speed over scalability.** A prototype that takes 2 days beats one that takes 2 weeks, even if the architecture is uglier.
2. **Boring is beautiful.** Use stacks you and the team already know. Novelty in tooling is a tax, not an advantage, during validation.
3. **Minimize moving parts.** Every service, API, and integration is a failure surface and setup cost. Fewer = faster to experiment.
4. **Managed over self-hosted.** Use managed services (Vercel, Supabase, Railway, etc.) during validation. Self-host only when a managed equivalent doesn't exist for your needs.
5. **Payments early.** If willingness-to-pay is the riskiest assumption, integrate a payment provider from day one. Stripe Payment Links = zero code.

---

## Default Stacks by Experiment Type

### Smoke Test (Landing Page + Email Capture / Pre-order)
**Fastest possible:**
| Layer | Default | Alternatives |
|-------|---------|--------------|
| Landing page | Carrd, Framer, or Next.js + Vercel | Webflow, plain HTML/CSS |
| Email capture | ConvertKit Mail, Resend, Buttondown | Mailchimp, Tally |
| Pre-order / WTP test | Stripe Payment Links | Gumroad, Lemon Squeezy |
| Analytics | Plausible, Vercel Analytics | GA4, PostHog |
| **Total build time** | **Hours** | |

### Concierge MVP (Manual Service)
**No "stack" — you are the software.**
| Layer | Default |
|-------|---------|
| Landing page | Carrd / Framer (to recruit participants) |
| Service delivery | Manual — email, spreadsheets, Slack |
| Scheduling | Cal.com, Calendly |
| Feedback collection | Tally forms, Typeform |
| **Total build time** | **Hours** | |

### Single-Feature MVP (Web App)
**Balanced default — fast but real product:**
| Layer | Default | Why |
|-------|---------|-----|
| Frontend | Next.js (App Router) + Tailwind CSS | Industry-standard, fast, huge ecosystem |
| Backend | Next.js API routes (or FastAPI if data-heavy) | Single deployment, no separate backend to manage |
| Database | Supabase (Postgres + Auth + Realtime) | Managed, generous free tier, instant setup |
| Auth | Supabase Auth or Clerk | Zero-config auth |
| Hosting | Vercel | Zero-config deploys, preview branches |
| Payments | Stripe (Checkout or Payment Links) | Industry standard, easy setup |
| Analytics | PostHog or Plausible | Actionable metrics built in |
| **Total build time** | **3–7 days** | |

### Single-Feature MVP (API / Backend-Only)
**For developer tools or data services:**
| Layer | Default |
|-------|---------|
| API | FastAPI (Python) or Hono (TypeScript) |
| Database | Supabase / Neon (Postgres) |
| Hosting | Railway, Fly.io, or Vercel |
| Auth | API keys (simple) or Clerk |
| Docs | Mintlify or GitHub README |
| **Total build time** | **2–5 days** | |

### Mobile Prototype
| Layer | Default |
|-------|---------|
| Cross-platform | Expo (React Native) |
| Backend | Supabase |
| Distribution | Expo Go (no app store needed for prototype) |
| **Total build time** | **5–10 days** | |

---

## Decision Heuristics

**"Do we need a backend at all?"**
If the experiment is testing demand (smoke test) or solution fit (concierge), the answer is usually **no**. Landing page + manual delivery is enough. Build a backend only when the riskiest assumption requires users to interact with actual software.

**"Database?"**
Start with Supabase free tier. It's Postgres + Auth + Realtime + Storage in one, and the free tier is generous enough for any prototype. Switch later only if there's a compelling reason.

**"Custom auth?"**
Never during validation. Use Clerk or Supabase Auth. Building auth is a distraction from testing the core hypothesis.

**"Which payments provider?"**
- **Stripe** — default for SaaS/web. Most mature, best docs.
- **Lemon Squeezy / Paddle** — if you need them to handle VAT/tax globally (Merchant of Record).
- **RevenueCat** — for mobile subscriptions.

**"Self-host or managed?"**
Managed, always, during validation. The cost difference is negligible at prototype scale, and the setup/maintenance time saved is massive. Self-hosting is a tax on iteration speed.

---

## Anti-Patterns (Don't Do This During Validation)

- **Microservices.** You don't have enough scale or team complexity to justify the overhead. Monolith.
- **Custom auth.** Use a service.
- **Kubernetes.** For a prototype. Seriously. Vercel/Railway/Fly.io.
- **Self-hosted databases.** Managed Postgres (Supabase/Neon/Railway).
- **Building a design system.** Use Tailwind + a component library (shadcn/ui, Radix).
- **Optimizing for scale.** You have 0 users. Optimize for the 1→100 user range, not 100k.
- **Multiple programming languages.** Pick one stack and stay in it. Context switching between languages slows the team.
