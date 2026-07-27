# GitHub App Installation Tokens & Shallow Clone Auth

Condensed, citable facts on GitHub App installation token lifecycle, `@octokit/auth-app` caching internals, and using an installation token as a git credential for a shallow clone. Jump-starts any GitHub-App-integration research (token caching strategy, git auth scheme, rate-limit budgeting, clone depth). **Re-verify live before citing numbers;** the URLs and quoted phrases below were confirmed 2026-07-25.

## The token chain at a glance

| Step | Credential | TTL | Signed/issued how | Primary source |
|---|---|---|---|---|
| 1. App JWT | `Authorization: bearer ***` | ≤10 min (`exp` claim) | RS256 with app's private key; claims `iat`/`exp`/`iss` | [Generating a JWT](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-json-web-token-jwt-for-a-github-app) |
| 2. Installation token | `Authorization: token ghs_…` | **1 hour** | `POST /app/installations/{id}/access_tokens` authenticated with the JWT | [Generating an installation token](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app) |
| 3. Git ops | `x-access-token:***` as HTTP basic-auth user | (same token, 1h) | Pass the installation token as the HTTP password | [Auth as installation](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-as-a-github-app-installation) |

## Verbatim anchors

**Installation token expires after 1 hour (the foundational fact):**
> "The installation access token will expire after 1 hour."
> — [Generating an installation access token](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app)

**JWT claims and lifetime:**
> "iat Issued At — The time that the JWT was created. To protect against clock drift, we recommend that you set this 60 seconds in the past…"
> "exp Expires At — The expiration time of the JWT, after which it can't be used to request an installation token. The time must be no more than 10 minutes into the future."
> "iss Issuer — The client ID or application ID of your GitHub App… Use of the client ID is recommended."
> — [Generating a JWT for a GitHub App](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-json-web-token-jwt-for-a-github-app)

**Installation token creation endpoint + response shape:**
> `POST /app/installations/{installation_id}/access_tokens` → `201`
> `{ "token": "ghs_16…8B4a", "expires_at": "2016-07-11T22:14:10Z", "permissions": {"issues":"write","contents":"read"}, "repository_selection": "selected", "repositories": [...] }`
> — [REST endpoints for GitHub Apps](https://docs.github.com/en/rest/apps/apps)

**Git clone with installation token (the auth scheme):**
> "You can also use an installation access token to authenticate for HTTP-based Git access. Your app must have the 'Contents' repository permission. You can then use the installation access token as the HTTP password. Replace TOKEN with the installation access token: `git clone https://x-access-token:TOKEN@....git`."
> — [Authenticating as a GitHub App installation](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-as-a-github-app-installation)

**Installation-token rate limit:**
> "GitHub Apps authenticating with an installation access token use the installation's minimum rate limit of 5,000 requests per hour. If the installation is on a GitHub Enterprise Cloud organization, the installation has a rate limit of 15,000 requests per hour."
> "For installations that are not on a GitHub Enterprise Cloud organization, the rate limit for the installation will scale with the number of users and repositories."
> — [Rate limits for the REST API](https://docs.github.com/en/rest/overview/rate-limits-for-the-rest-api)

## @octokit/auth-app caching internals (source-verified)

Read directly from `octokit/auth-app.js` source (commit on `main`, 2026-07-25). These resolve the recurring "how do I cache installation tokens correctly" architecture question:

**Default cache — in-memory LRU, 59-min TTL, per-installation key** (`src/cache.ts`):
> `getCache()` returns `new Lru<string>(15000, 1000 * 60 * 59)` — max **15 000 tokens**, TTL **59 minutes** (1 minute under GitHub's 1-hour ceiling). Source comments: *"cache max. 15000 tokens, that will use less than 10mb memory"* / *"Cache for 1 minute less than GitHub expiry."*

**Cache key** (`optionsToCacheKey` in `src/cache.ts`): `installationId | repositoryIds | repositoryNames | permissions(sorted)`. Tokens for different permission-scope or repo-subset requests are cached separately.

**No proactive refresh — lazy re-mint on TTL eviction.** `getInstallationAuthenticationImpl` (`src/get-installation-authentication.ts`) checks the cache first; if a hit exists it returns it, otherwise it mints a new token via the REST endpoint and caches it. **There is no timer that refreshes before expiry** — the token is served until the 59-min TTL evicts it, then the next call re-mints. Pass `refresh: true` to force a bypass.

**Concurrent-request de-duplication.** A module-level `pendingPromises` map (`Map<string, Promise<…>>`) ensures that if N requests ask for the same installation's token while a mint is in flight, they all await the same promise rather than firing N mints. Keyed by the same cache key; promise deleted in a `.finally()`.

**401-on-freshly-created-token retry.** `sendRequestWithRetries` (`src/hook.ts`) retries a 401 up to 5 seconds after token creation (1s, 2s… backoff), because "newly created tokens might not be accessible immediately." After 5s it throws with a message pointing to `githubstatus.com`.

**Cache is injectable.** Pass `options.cache = { async get(key), async set(key, value) }` to `createAppAuth()` to back the cache with Redis, a DB, etc. The default is in-memory (`toad-cache`).

### Architecture verdicts this settles

- **Q: In-memory cache vs DB-backed?** In-memory (the default) is correct and sufficient for a single-instance server. Installation tokens are **ephemeral 1-hour credentials, not durable state** — caching them in memory does not violate a "stateless / state-in-DB" design rule, because nothing of record is lost when the process restarts (a fresh token is minted on next request). DB-backed caching only earns its complexity when scaling horizontally across instances to share mints and avoid redundant token-creation API calls.
- **Q: Do I need to handle expiry myself?** No, if you use `@octokit/auth-app` as the `authStrategy` on an Octokit instance — the hook transparently re-mints after the 59-min TTL. You only handle expiry yourself if you're using the raw token for **non-Octokit operations** (e.g. a `git clone` subprocess — see below).
- **Q: Mid-clone expiry?** A `git clone` started with a token that expires mid-clone fails with a fatal auth error. Fix: **worker-level retry** — catch the clone failure, call `auth({type:"installation", refresh:true})` to force a fresh token, retry the clone once. For a shallow `--depth 1` clone of a <1000-file repo this almost never triggers, but the retry must exist.

## Shallow clone with the installation token

**The scheme (GitHub-documented):** `git clone https://x-access-token:TOKEN@github.com/owner/repo.git`. Token is the HTTP password; username is literally the string `x-access-token`. Needs `Contents: read` permission. Confirmed independently by `octokit/auth-token.js` README:
> "when using with an installation, the token must be prefixed with `x-access-token`"

**depth=1 sufficiency:** `--depth 1` implies `--single-branch` and produces the **full HEAD working tree** — all files at the current commit, no history. For "analyze the entire repo at current HEAD" this is exactly right. No sparse-checkout needed unless the repo is huge and you only need a subtree.

**Security caveat — token-in-URL leakage.** Embedding the token in the URL exposes it via `/proc/<pid>/cmdline`, shell history, process listings, and any tool that logs the git command. Mitigations, in order of preference:
1. **GIT_ASKPASS / `core.askPass`** — point git at a script that echoes the token on demand; the token never appears in argv. Best for production.
2. **`git credential` helper** — supply `protocol=https\nhost=github.com\nusername=x-access-token\npassword=***` via a helper; same benefit.
3. **URL-embedded token** — acceptable for quick local experiments and when you control logging (e.g. `execa` with the prefixed URL, as octokit/auth-token's example shows). Avoid in multi-tenant servers.

**Cloning a specific PR head SHA:** `--branch <sha>` is invalid for arbitrary SHAs in git. Robust server-side pattern: shallow-clone the ref (`--depth 1 --branch <branch>`), or `--depth 1 --no-checkout` then `git -C <dir> fetch origin <sha> --depth 1 && git -C <dir> checkout <sha>` (fetching a raw SHA may require `uploadpack.allowReachableSHA1InWant` on some server configs). For a PR-sync webhook you usually have the branch ref, so clone the branch.

## Extraction notes for the next verifier

- **GitHub docs (`docs.github.com`) render server-side HTML** — `curl -sL` returns the full HTML (no JS shell, unlike AWS/Stripe/Cloudflare). Download to a file, then strip tags locally. Pages are large (60–700 KB), so don't grep the curl stream:
  ```
  curl -sL "https://docs.github.com/en/…/page" -o /tmp/gh_page.html
  python3 -c "import re; t=re.sub(r'<[^>]+>',' ',open('/tmp/gh_page.html').read()); t=re.sub(r'\s+',' ',t); …"
  ```
  Rate-limit / token statements appear both as rendered HTML *and* as `\u003c…\u003e`-escaped JSON in the same page — both carry the same text; grep for the keyword either way.
- **Octokit source is on `raw.githubusercontent.com`.** Fetch individual files by path — no clone needed for a read-only snapshot:
  ```
  curl -sL "https://raw.githubusercontent.com/octokit/auth-app.js/main/src/cache.ts"
  curl -sL "https://raw.githubusercontent.com/octokit/auth-app.js/main/src/get-installation-authentication.ts"
  curl -sL "https://raw.githubusercontent.com/octokit/auth-app.js/main/src/hook.ts"
  ```
  The three files that answer cache-lifecycle questions: `cache.ts` (TTL/key), `get-installation-authentication.ts` (mint + concurrent-de-dup), `hook.ts` (request hook + 401-retry). README.md has the public API contract.
- **The REST API reference page (`/rest/apps/apps`) is a 700 KB index** — grep for the specific endpoint verb (`Create an installation access token`) rather than reading top-to-bottom. The response-schema block (`{token, expires_at, permissions, …}`) is the citable artifact for the token shape.
