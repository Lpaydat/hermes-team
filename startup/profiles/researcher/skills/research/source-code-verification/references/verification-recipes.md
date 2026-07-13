# Source-code verification recipes

Concrete patterns that recur across verification tasks. Read the section relevant to your framework or task type.

## The grep batch (copy-and-adapt)

When you land in an unfamiliar codebase, run these three search_files passes in ONE turn before reading anything:

```
# Pass 1 — find the factory / dependency registration
pattern: "@upstash/ratelimit"          # or "rate-limiter-flexible", "slowapi", etc.

# Pass 2 — find the algorithm / API surface
pattern: "slidingWindow|tokenBucket|fixedWindow|leakyBucket"

# Pass 3 — find the route/handler (broad)
pattern: "Ratelimit|ratelimit|rateLimiter|rate-limit"
```

The overlap between pass-1 hits (where it's defined) and pass-3 hits (where it's called) narrows you to the 2–4 files that matter.

## Framework dispatch locations (where the handler actually lives)

These are the surprise locations — the places a "redirect" or "endpoint" handler hides that aren't the obvious route file:

| Framework | Hot-path handler location | Notes |
|---|---|---|
| **Next.js (App Router)** | `middleware.ts` (root or `app/`) | Redirects for dynamic paths (`/:code`) live in middleware via `NextResponse.redirect()`, NOT in `app/[param]/route.ts`. The app-router `route.ts` is for `/api/*`. This bit me — I searched `app/api` first and found nothing. |
| **Next.js (App Router) API** | `app/api/<path>/route.ts` | Standard REST endpoints. Export `GET`/`POST` etc. |
| **Express** | `routes/*.js` + `server.js` wiring | Route definitions live in route files; the app wires them in `server.js`. Middleware (rate-limit) is attached per-route via `router.use()` or passed to the handler. |
| **PHP / Mezzio (e.g. shlink)** | `config/autoload/routes.config.php` | All routes declared in a config array. Middleware pipeline in `config/autoload/middleware-pipeline.global.php`. |
| **FastAPI / Starlette** | `@app.get("/:code")` decorators or `APIRouter` | Rate-limit middleware is often a decorator (`@limiter.limit(...)`) or a Depends(). |

**Lesson:** before grepping for the behavior, find the framework's dispatch point. Otherwise you grep the wrong subtree and conclude (wrongly) that something doesn't exist.

## Worked example: dub.co rate-limit audit

**Task:** Does dub.co (1) rate-limit GET /:code redirects? (2) rate-limit POST /api/links? What algorithm/key? (3) Rely on CDN caching for the redirect path?

**Commit:** `803e789bf35c148cbef7ffc642e3919192540d31` (dubinc/dub, 2026-07-10).

### Step-by-step with the evidence that mattered

1. **Clone + pin commit** — `git clone --depth 1`; recorded `803e789b`.

2. **Parallel greps** found: the ratelimit factory at `lib/upstash/ratelimit.ts`, `@upstash/ratelimit` in `package.json`, and ~15 call sites across `app/api/**/route.ts`. Notably, ZERO hits in `lib/middleware/`.

3. **Read the redirect handler in full.** The redirect was NOT in `app/api/` — it was `apps/web/lib/middleware/link.ts` (`LinkMiddleware`, 607 lines), dispatched from root `middleware.ts:89`. Read all 607 lines across two reads.

4. **Proved absence of rate-limiting on redirects:**
   ```
   grep -n "ratelimit|ratelimitOrThrow|Ratelimit" lib/middleware/link.ts  →  (none found)
   ```
   Shown empty output → legitimately reported "NOT rate-limited."

5. **Confirmed POST /api/links limit with the guard.** `app/api/links/route.ts:65-76`:
   ```ts
   if (!session) {                                    // ← THE GUARD (unauth only)
     const ip = req.headers.get("x-forwarded-for") || LOCALHOST_IP;
     const { success } = await ratelimit(10, "1 d").limit(ip);   // slidingWindow, IP-keyed
   ```
   Reported: algorithm=slidingWindow, key=IP, but **only for unauthenticated requests** — the guard is half the finding.

6. **Caught the "defined vs applied" trap (CDN claim).** The `STATIC_PAGES_CACHE_HEADERS` constant (`Vercel-CDN-Cache-Control: s-maxage=86400`) is defined at `link.ts:66`, but grepping its usage sites showed it spread onto ONLY the static error-page responses (lines 103/217/228/247/303 — all `NextResponse.rewrite` to notfound/banned/expired). The actual 302 redirect branches (596–606) set no CDN header. So "relies on CDN caching for the redirect path" was **REFUTED** — the code caches error pages, not redirects. This distinction only surfaced because I counted the usage sites rather than trusting the definition.

### Verdicts produced
- Redirects rate-limited? → **NO** (proven by empty grep).
- POST /api/links rate-limited? → **YES, slidingWindow 10/day, IP-keyed, unauth-only** (route.ts:65-76 + ratelimit.ts factory).
- CDN caching on redirects? → **NO** (defined-but-not-applied; only static error pages carry the header).

## Reporting into a kanban council

If the verification feeds a decision body (ADR review, design council), post a blackboard comment with a **verdict table** (claim → CONFIRMED/REFUTED/PARTIAL → one-line evidence pointer), not the full transcript. Park the full detail in a workspace findings file and name it in the comment. Council members read the table; the curious follow the file.

## Absence-claim checklist (before you say "X does not do Y")

- [ ] Ran a grep for Y's identifiers in the relevant handler file — output shown, empty.
- [ ] Checked the framework's actual dispatch point (not just the obvious route folder).
- [ ] Confirmed Y isn't conditionally guarded-out behind a feature flag or env var.
- [ ] Checked that Y isn't applied as outer middleware (e.g. a global `app.use(limiter)`) that you'd miss by reading only the handler.

If any box is unchecked, the honest report is "I could not confirm Y" — not "Y is absent."

## At-rest storage verification (auth servers / token systems)

When the question is "does framework X store secret Y in plaintext or hashed at rest?" or "does it cache responses for idempotency?" — read **`references/at-rest-storage-verification.md`**. It covers the migration-history pitfall (current `main` can hold two eras of storage simultaneously — Supabase GoTrue's v1-plaintext / v2-HMAC split is the canonical example), the schema-before-struct reading order (SQL DDL is ground truth, not the ORM model), and an auth-server grep batch plus a verified at-a-glance table for Hydra / Keycloak / Supabase / Authentik / Spring Authorization Server / Django allauth.
