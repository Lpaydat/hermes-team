# Rate-Limiting Algorithms — Major API Gateways

Condensed, citable facts on what algorithm each major gateway uses, extracted verbatim from primary-source docs. Jump-starts design-doc / ADR fact-checking when a claim asserts "gateway X uses algorithm Y" or "token bucket's burst is unavoidable." **Re-verify live before citing numbers;** the URLs and quoted phrases below were confirmed 2026-07-13.

## The four gateways at a glance

| Gateway | Algorithm | Burst handling | Primary source |
|---|---|---|---|
| AWS API Gateway | **Token bucket** (explicitly named) | `rate` (refill) + `burst` (capacity) as **independent** knobs | [AWS: Throttling](https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-request-throttling.html) |
| Cloudflare WAF Rate Limiting | **Fixed-window counter** | requests-per-period + mitigation timeout; Enterprise "throttle" action = opt-in smoothing | [CF: Request rate calculation](https://developers.cloudflare.com/waf/rate-limiting-rules/request-rate/) |
| Stripe | **Per-second rate limit** + separate **concurrency** limit (algorithm unnamed server-side) | Recommends **client-side token bucket** | [Stripe: Rate limits](https://docs.stripe.com/rate-limits) |
| GitHub | **Windowed counter** (fixed-window; reset-epoch semantics) | per-hour primary + per-minute / CPU-time / content-creation secondary tiers | [GitHub: REST API rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api) |

Only **AWS** names its algorithm. Cloudflare uses a strict counter. Stripe and GitHub use windowed counters and do not name a bucketing algorithm server-side.

## Verbatim anchors

**AWS API Gateway — token bucket:**
> "API Gateway throttles requests to your API using the token bucket algorithm, where a token counts for a request. Specifically, API Gateway examines the rate and a burst of request submissions..."
> "You can specify a throttling rate, which is the rate, in requests per second, that tokens are added to the token bucket. You can also specify a throttling burst, which is the capacity of the token bucket."

**Cloudflare — fixed-window counter (NOT a token bucket):**
> Parameters: Characteristics (counting key), Period (seconds), Requests per period, Duration (mitigation timeout).
> "Cloudflare tracks request rates by maintaining separate counters for each unique combination of values in a rule's characteristics."
> Default action behavior blocks for the full Duration regardless of rate; Enterprise can configure the rule to "throttle requests" (allow when rate drops below limit) — that opt-in mode is the token-bucket-style smoothing.

**Stripe — rate + concurrency; recommends client-side token bucket:**
> "rate limits are measured in API requests per second, per Stripe account" ... "rate limits, which in general reset after one second"
> "Concurrency limits restrict the number of simultaneously active requests, separate from rate limits."
> "A common technique for controlling API usage is to implement a client-side token bucket rate-limiting algorithm."

**GitHub — windowed counter with reset epoch (fixed-window, not sliding):**
> Headers: `x-ratelimit-limit` (max/hour), `x-ratelimit-remaining`, `x-ratelimit-used`, `x-ratelimit-reset` (UTC epoch seconds when window resets).
> Secondary tiers: 100 concurrent; 900 points/min REST; 90s CPU / 60s real; 80 content-creating req/min.

## The tuning question (resolves the recurring "burst is unavoidable" ADR claim)

**Claim to refute:** "Token bucket's burst capacity inherently creates an abuse vector that can't be removed without switching to a sliding-window counter."

**Verdict: REFUTED (the conclusion is wrong).** Token bucket has two *independent* parameters, and the burst ceiling is governed **entirely by `capacity`**, not by `rate`:
- `rate` = steady-state refill (tokens/sec)
- `capacity` = max accumulated tokens = **max instantaneous burst**

| Config | Worst-case burst | Equivalent to |
|---|---|---|
| `capacity = 1` | 1 request, then strictly `rate` spacing | Leaky bucket (zero burst) |
| `capacity = rate` (e.g. 100/s, cap=100) | 1 second of traffic instantly, then 100/s | ≈ 1-second sliding-window counter |
| `capacity = rate × N` | N seconds of traffic instantly | N-second bursts |

**Decisive proof:** AWS API Gateway exposes exactly these two knobs independently and lets operators set `burst` as low as desired. The burst vector is a **misconfiguration** (`capacity >> rate`), not an algorithmic defect. As `capacity` drops, token bucket and sliding-window counter **converge**; at `capacity = 1` they are functionally identical to a leaky bucket.

**Recommendation to embed when a design-doc raises this concern:** keep token bucket; set `capacity = rate` (worst-case burst = one second of traffic, same ceiling as a 1-second sliding-window counter) at lower memory cost than a sliding log; add a separate concurrency cap (Stripe's pattern) as defense-in-depth. Use `capacity = 1` only when true zero-burst is required (penalizes legitimate clients).

## Extraction notes for the next verifier

- Stripe / GitHub / AWS docs pages are **JS-rendered** — `curl` returns a shell; `browser_snapshot` truncates. Use `browser_console` with `document.querySelector('main')?.innerText` (full untruncated text in one call). Already covered in `references/doc-extraction-recipes.md`.
- Cloudflare rate-limiting docs live under `/waf/rate-limiting-rules/` (the old `/rate-limiting-rules/` root **404s** — product was folded into the WAF). Classic "restructured docs portal" pattern; navigate the WAF sidebar to find current slugs. The "Request rate calculation" sub-page is where the counter semantics live, not the overview.
