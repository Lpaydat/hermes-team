# GitHub App Permissions, Webhook Secret & Rate Limits

Condensed, citable facts on which repository permissions a GitHub App needs, how webhook deliveries are verified, and how REST rate limits apply to installation tokens. Sibling to `github-app-tokens-and-clone.md` (which covers the token chain + shallow-clone auth). Jump-starts the "what permissions/events does my app need", "how do I verify the webhook", and "will I hit the limit" questions. **Re-verify live before citing numbers;** the URLs and quoted phrases below were confirmed 2026-07-25.

---

## Repository permissions — the reference page

**Authoritative page:** [Permissions required for GitHub Apps](https://docs.github.com/en/rest/authentication/permissions-required-for-github-apps) — a ~1.9 MB server-rendered HTML table mapping every REST endpoint to its required permission scope. This is the page to grep when you need "what permission does endpoint X need."

**Permission-selection guidance:** [Choosing permissions for a GitHub App](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app) — explains the permission model and the git-access rule.

### Operation → permission mapping (for a typical PR-analysis bot)

| Operation | Endpoint | Required permission |
|---|---|---|
| Shallow git clone via installation token (HTTPS) | `git clone https://x-access-token:***` | **Contents: Read** |
| List existing comments on a PR | `GET /repos/{o}/{r}/issues/{n}/comments` | Pull requests: Read (or Issues: Read) |
| Create a new PR comment | `POST /repos/{o}/{r}/issues/{n}/comments` | **Pull requests: Write** (or Issues: Write) |
| Edit a PR comment in place | `PATCH /repos/{o}/{r}/issues/comments/{id}` | **Pull requests: Write** |
| Get PR details | `GET /repos/{o}/{r}/pulls/{n}` | Pull requests: Read (or Contents: Read) |

### Verbatim anchors

**Git access needs Contents (the clone-permission rule):**
> "If you want your app to use an installation or user access token to authenticate for HTTP-based Git access, you should request the 'Contents' repository permission. If your app specifically needs to access or edit Actions files in the .github/workflows directory, request the 'Workflows' repository permission."
> — [Choosing permissions for a GitHub App](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app)

**PR comments are shared endpoints (Issues OR Pull requests satisfies):**
> "The fine-grained token must have at least one of the following permission sets: 'Issues' repository permissions (write) OR 'Pull requests' repository permissions (write)."
> — [REST API endpoints for issue comments](https://docs.github.com/en/rest/issues/comments) (Create an issue comment section)

**Every PR is an issue (the endpoint-routing rationale):**
> "You can use the REST API to create and manage comments on issues and pull requests. Every pull request is an issue, but not every issue is a pull request. For this reason, 'shared' actions for both features, like managing assignees, labels, and milestones, are provided within the Issues endpoints. To manage pull request review comments, see REST API endpoints for pull request review comments."
> — [REST API endpoints for issue comments](https://docs.github.com/en/rest/issues/comments)

### Critical distinction — PR issue comments vs PR review comments

Two **different** endpoint families; don't confuse them:

- **PR issue comments** (top-level "conversation" tab comments — what a living-summary bot wants): `/repos/{o}/{r}/issues/{n}/comments` (list/create) and `/repos/{o}/{r}/issues/comments/{id}` (get/update/delete). Permission: Pull requests (or Issues).
- **PR review comments** (inline annotations on specific diff lines): `/repos/{o}/{r}/pulls/{n}/comments` and `/repos/{o}/{r}/pulls/comments/{id}`. Permission: Pull requests. Endpoint verb is `PATCH /repos/{o}/{r}/pulls/comments/{id}`.

A "single living comment edited in place" uses the **issue-comments** `PATCH` endpoint. It needs `Pull requests: Write` and **no additional** `Issues: Write` — the "at least one of" rule covers it.

### Metadata: Read — effectively mandatory

The scraped docs do not carry an explicit prose sentence "Metadata is required for all apps." In practice the **Metadata permission in the GitHub App settings UI is locked to Read-only and cannot be set to "No access"** (observed in the registration UI). Treat `Metadata: Read` as effectively mandatory; it grants `GET /repos/{owner}/{repo}` and basic repo metadata endpoints. (If the architect demands a doc citation for "mandatory," this is UI-enforced, not text-documented on the scraped pages — confirm against the live UI or flag the gap honestly.)

---

## Webhook events — which to subscribe

**Authoritative pages:** [Using webhooks with GitHub Apps](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/using-webhooks-with-github-apps) · [Webhook events and payloads](https://docs.github.com/en/webhooks/webhook-events-and-payloads) · [Registering a GitHub App](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/registering-a-github-app)

### Subscription requirements per event (verbatim)

- **`pull_request` event:** "To subscribe to this event, a GitHub App must have at least read-level access for the 'Pull requests' repository permission."
- **`push` event:** "To subscribe to this event, a GitHub App must have at least read-level access for the 'Contents' repository permission."

### Permissions gate event availability

> "If you selected Active in the earlier step to indicate that your app should receive webhook events, under 'Subscribe to events', select the webhook events that you want your app to receive. **The permissions that you selected in the previous step determine what webhook events are available.**"
> — [Registering a GitHub App](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/registering-a-github-app)

### `pull_request` payload carries everything a PR-analysis bot needs

Fields present when GitHub delivers a `pull_request` webhook to a GitHub App:
- `action` (string) — `opened` / `synchronize` / `reopened` / `closed` / `edited` / …
- `number` (integer) — **the PR number**
- `pull_request` (object) — full PR object incl. `head.sha`, `head.ref`, `base.ref`, `state`, `title`
- `repository` (object) — incl. `full_name`
- `installation` (object) — incl. `installation.id`
- `sender`, `organization`, `enterprise` (as applicable)

### `push` payload does NOT carry a PR number

The `push` event fires on any branch push (main, feature, tag). Payload has `ref`, `after` (head SHA), `before`, `commits`, `repository`, `installation` — but **no PR number and no PR metadata**. To detect "is this pushed branch a PR branch?" the app must query `GET /repos/{o}/{r}/pulls?head={owner}:{branch}&state=open`. **For a PR-triggered bot, subscribe to `pull_request` and route on `action ∈ {opened, synchronize, reopened, closed}` — you do not need `push`.** (`synchronize` is the canonical "new commits pushed to the PR head branch" signal.)

---

## Webhook secret verification — HMAC-SHA256

**Authoritative page:** [Validating webhook deliveries](https://docs.github.com/en/webhooks-and-events/webhooks/securing-your-webhooks)

### Algorithm (verbatim)

> "GitHub uses an HMAC hex digest to compute the hash."
> "The hash signature always starts with `sha256=`."
> "The hash signature is generated using your webhook's secret token and the payload contents."
> "The hash signature will appear in each delivery as the value of the **X-Hub-Signature-256** header."

**Procedure:** HMAC-SHA256(key = webhook secret, msg = **raw request body bytes**) → hex digest → prefix `sha256=` → compare to the `X-Hub-Signature-256` header value (`sha256=<hex>`).

### Test vector (use to validate your implementation)

| Input | Value |
|---|---|
| secret | `It's a Secret to Everybody` |
| payload | `Hello, World!` |
| expected signature | `757107ea0eb2509fc211221cce984b8a37570b6d7586c22c46f4379c8b043e17` |
| expected X-Hub-Signature-256 | `sha256=757107ea0eb2509fc211221cce984b8a37570b6d7586c22c46f4379c8b043e17` |

### Timing-safe comparison — REQUIRED

> "Never use a plain == operator. Instead consider using a method like `secure_compare` or `crypto.timingSafeEqual`, which performs a 'constant time' string comparison to help mitigate certain timing attacks against regular equality operators, or regular loops in JIT-optimized languages."

Per-language constants: Ruby → `Rack::Utils.secure_compare`; **Python → `hmac.compare_digest`** (stdlib, no dep); JS → `crypto.subtle.verify`; TS → `@octokit/webhooks` `.verify()`.

### Other constraints

- **Legacy header:** `X-Hub-Signature` (HMAC-SHA1) is "only included for legacy purposes" — use `X-Hub-Signature-256` (HMAC-SHA256).
- **Encoding:** "If your language and server implementation specifies a character encoding, ensure that you handle the payload as UTF-8." Operate on raw bytes, not a re-encoded string.
- **Delivery headers:** `X-GitHub-Event` (event name), `X-GitHub-Delivery` (globally-unique event GUID — reuse it to dedupe redeliveries), `X-GitHub-Hook-ID`, `User-Agent: GitHub-Hookshot/…`.
- **No ordering guarantee + at-least-once delivery:** GitHub retries on non-2xx and supports manual redelivery (same `X-GitHub-Delivery` GUID). Treat the webhook stream as unordered + at-least-once: dedupe by GUID, gate writes by comparing the in-flight analysis's head SHA to the current PR HEAD, discard stale work.

---

## Rate limits — installation tokens

**Authoritative page:** [Rate limits for the REST API](https://docs.github.com/en/rest/overview/rate-limits-for-the-rest-api)

### Primary limit (per installation)

> "GitHub Apps authenticating with an installation access token use the installation's minimum rate limit of **5,000 requests per hour**. If the installation is on a GitHub Enterprise Cloud organization, the installation has a rate limit of **15,000 requests per hour**."

**Scaling (non-Enterprise):** +50 req/hr per repository over 20 repos; +50 req/hr per user over 20 users; **cap 12,500 req/hr.**

### Secondary limits (these are the real binding constraints for a write-heavy bot)

> "In addition to primary rate limits, GitHub enforces secondary rate limits in order to prevent abuse and keep the API available for all users."

| Secondary limit | Value |
|---|---|
| Concurrent requests (REST + GraphQL combined) | **100** |
| REST endpoint points | **900 points/min** (GET/HEAD/OPTIONS = 1 pt; POST/PATCH/PUT/DELETE = 5 pts) |
| Content-generating requests | **80/min** and **500/hour** |
| CPU time | 90s CPU / 60s real |
| OAuth token creation (GitHub/OAuth apps) | 2,000/hour |

> "Creating content too quickly using this endpoint may result in secondary rate limiting." (stated on the create-comment endpoint)

**For a PR-comment bot:** comment create (`POST`) is content-generating, so the **500 content-creating req/hour** secondary limit is tighter than the 5,000/hr primary limit. At ~1 create + 1 edit per analysis that's ~250 analyses/hour before the content limit bites — still far above any realistic single-installation load, but it's the constraint to watch, not the headline 5,000.

### Response headers (how to check status)

`x-ratelimit-limit` · `x-ratelimit-remaining` · `x-ratelimit-used` · `x-ratelimit-reset` (UTC epoch seconds) · `x-ratelimit-resource`. Prefer reading these headers over calling `GET /rate_limit` (which itself consumes secondary-limit budget). On a 403/429, honor `retry-after` and `x-ratelimit-reset`; **"Continuing to make requests while you are rate limited may result in the banning of your integration."**

### Git clone does NOT count against the REST rate limit

The rate-limit doc scopes limits to "the number of REST API requests" and calls out a separate limit **only for Git LFS** ("API requests are required when you upload or download Git LFS content. These count towards a separate rate limiting bucket…"). Plain `git clone --depth=1` over HTTPS via `x-access-token:<installation-token>` is a git-protocol operation on the Smart HTTP transport — **not a REST API call, does not consume the 5,000/hr budget.** Only the ~2-3 REST calls per analysis (list/create/edit comment) consume the budget. Token-minting (`POST /app/installations/{id}/access_tokens`) counts against the separate 2,000/hr OAuth-token bucket.

---

## Extraction notes for the next verifier

- **`docs.github.com` reference pages are server-rendered HTML — curl works.** The permissions reference (`/rest/authentication/permissions-required-for-github-apps`, ~1.9 MB), rate-limits (`/rest/overview/rate-limits-for-the-rest-api`, ~340 KB), webhook events (`/webhooks/webhook-events-and-payloads`, ~890 KB), and issue-comments (`/rest/issues/comments`, ~470 KB) all return full HTML to `curl -sL`. Download to file, strip tags locally, grep the artifact.
- **Tutorial / registration pages ARE JS-rendered.** `/apps/creating-github-apps/.../registering-a-github-app` and `.../using-webhooks-with-github-apps` return a JS shell via curl (~190 KB, ~40 stripped lines of chrome). For these, use `browser_navigate` then `browser_console` with `document.querySelector('article')?.innerText ?? document.querySelector('main')?.innerText` to get the full hydrated text in one call.
- **Slug discovery — the permission-scope page moved.** The old `/apps/using-github-apps/permission-scopes-for-github-apps` 404s; the canonical permissions reference is now `/rest/authentication/permissions-required-for-github-apps`. The "modifying a GitHub App" page moved from `creating-github-apps/` to `maintaining-github-apps/`. Don't trust recalled deep URLs — a stable index page + `location.href` after a sidebar click is reliable; see `docs-verification`'s `references/doc-extraction-recipes.md` § "Restructured docs portals."
- **`browser_console` link-discovery for moved pages:** `JSON.stringify(Array.from(document.querySelectorAll('a')).filter(a => /keyword/i.test(a.textContent)).map(a => ({text:a.textContent.trim(), href:a.href})))` lists candidate canonical URLs from any stable index page — faster than guessing slugs.
- **Endpoint→permission table parsing:** the permissions reference HTML nests `<tr>` rows with endpoint, access level, and token types as `<td>` cells. After stripping, convert `</td>` → ` | ` and `<tr>` → `\n` to get greppable rows like `POST /repos/{o}/{r}/issues/{n}/comments | write | UAT`. Search for the endpoint verb to land on the row.
