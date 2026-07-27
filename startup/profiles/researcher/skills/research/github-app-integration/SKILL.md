---
name: github-app-integration
description: "Verify and cite GitHub App authentication, token lifecycle, git clone auth, webhook, permission, and rate-limit behaviors from primary sources (docs.github.com, octokit source, git-scm.com). Use when building or auditing a GitHub App integration — Probot/Octokit apps or custom webhook services — and the questions are 'how do installation tokens work', 'how do I clone with an installation token', 'what permissions/events does this app need', or 'will I hit the rate limit'. Carries a distilled knowledge bank (token TTL, @octokit/auth-app cache internals, x-access-token clone scheme, depth=1 semantics) so you don't re-derive it each session. Sibling to docs-verification and source-code-verification; load THOSE for the general method, load THIS for the GitHub-App-specific facts and extraction paths."
---

# GitHub App integration verification

Verify and cite GitHub App integration facts against primary sources. The authority is `docs.github.com` (token/webhook/permission/rate-limit guarantees) + `octokit/*.js` source (how the auth library actually caches/mints) + `git-scm.com` (clone semantics). This skill carries the distilled knowledge bank so a design-doc or ADR question ("do installation tokens expire?", "how do I clone with one?", "what permission for editing a PR comment?") is answered in seconds, then re-verified live.

## When to load

- "How do GitHub App installation tokens work / expire / refresh?"
- "How do I do a shallow git clone using an installation token?"
- "What permissions/events does my GitHub App need for [clone + post PR comment]?"
- "Will my app hit the REST API rate limit at [scale]?" / "Does the git clone count against the API rate limit?"
- "How does @octokit/auth-app cache tokens — do I need a DB-backed cache?"
- "How do I verify a GitHub webhook delivery (the HMAC secret)?" / "what's the X-Hub-Signature-256 algorithm?"
- "What permission does endpoint X need?" / "do I need Issues: Write to edit a PR comment?"
- "Should I subscribe to `push` or `pull_request` for a PR-triggered bot?"
- Any ADR/architecture question about a GitHub-App-based service (webhook receiver, PR bot, CI server).

If the question is about a *non-GitHub* vendor's docs, load `docs-verification` instead. If it's about a *non-Octokit* library's source, load `source-code-verification`. This skill is GitHub-App-domain-specific.

## The knowledge bank (read first, re-verify before citing)

The distilled facts — token chain, TTLs, auth-app cache internals, clone scheme, rate limits — live in **`references/github-app-tokens-and-clone.md`**. Read it before touching the web; it answers ~80% of design questions immediately. The facts below are the one-screen summary; the reference has the verbatim quotes + URLs.

### Token chain
| Step | Credential | TTL |
|---|---|---|
| App JWT | `bearer ***` | ≤10 min (`exp` claim; `iat` 60s in past, `iss`=client_id) |
| Installation token | `token ghs_…` | **1 hour** |
| Git ops | `x-access-token:***` HTTP basic user | (same token) |

### @octokit/auth-app caching (source-verified)
- Default: in-memory LRU (`toad-cache`), **max 15 000 tokens, 59-min TTL**, keyed by `installationId|repoIds|repoNames|permissions`.
- **No proactive refresh** — serves cached token until TTL evicts, then re-mints on next call. `refresh:true` forces bypass.
- Concurrent same-key requests are de-duped via a `pendingPromises` map (one mint in flight).
- 401-on-fresh-token retried up to 5s (token replication delay).
- Cache injectable via `options.cache.{get,set}`.

### Clone auth
- `git clone https://x-access-token:TOKEN@github.com/owner/repo.git` — token as HTTP password, user `x-access-token`, needs `Contents: read`. (GitHub-documented + octokit/auth-token confirms the prefix.)
- `--depth 1` implies `--single-branch`, gives the **full HEAD working tree** (all files). Sufficient for "entire repo at HEAD" without sparse-checkout.
- **Leakage caveat:** token-in-URL exposes via `/proc/cmdline` & logs. Prefer `GIT_ASKPASS`/`core.askPass` or a `git credential` helper in production; URL-embedding only for controlled local use.
- Cloning a raw SHA: `--branch <sha>` is invalid; use `--depth 1 --no-checkout` then `git fetch origin <sha> --depth 1 && git checkout <sha>`.

### Rate limits (installation tokens)
- **5 000 req/hour minimum** (15 000/hour on Enterprise Cloud); scales up with repos/users for non-Enterprise, cap 12 500/hr. **Git clone does NOT consume this budget** (only REST calls do; git ops are Smart-HTTP, not REST). Only Git LFS has a separate API bucket.
- **Secondary limits are the real binding constraints** for a write-heavy bot: 100 concurrent; 900 points/min REST (GET=1pt, POST/PATCH=5pt); **80 content-generating req/min and 500/hour** (comment create is content-generating); 90s CPU/60s real; 2 000 OAuth-token-creations/hour.

### Webhook secret verification
- **Algorithm:** HMAC-SHA256(key = webhook secret, msg = **raw body bytes**) → hex → prefix `sha256=` → compare to `X-Hub-Signature-256` header. **MUST use timing-safe compare** (Python `hmac.compare_digest`; Ruby `secure_compare`; TS `@octokit/webhooks.verify`).
- **Test vector:** secret=`It's a Secret to Everybody`, payload=`Hello, World!` → `sha256=757107ea0eb2509fc211221cce984b8a37570b6d7586c22c46f4379c8b043e17`.
- **Delivery:** at-least-once, no ordering guarantee. `X-GitHub-Delivery` = event GUID (dedupe redeliveries on it). Legacy `X-Hub-Signature` (SHA1) is deprecated — use `-256`.

### Permissions & events (for a clone + PR-comment bot)
- **Contents: Read** (clone), **Pull requests: Write** (list/create/edit comments), **Metadata: Read** (effectively mandatory — UI-locked to read-only). No `Issues: Write` needed: PR comments use shared `/issues/comments` endpoints that accept "at least one of" Issues OR Pull requests permission.
- **PR issue comments ≠ PR review comments:** living-summary comment = `/issues/comments/{id}` PATCH; inline diff annotations = `/pulls/comments/{id}` PATCH. Different endpoints.
- **Subscribe to `pull_request`** (needs Pull requests: Read; route on `opened`/`synchronize`/`reopened`/`closed`). `synchronize` is the canonical "new commits on PR branch" signal and carries PR number + head SHA inline. Avoid `push` for a PR bot — its payload has no PR number and forces an API lookup.

The verbatim quotes, test vectors, and extraction recipes for permissions/webhooks/rate-limits live in **`references/github-app-permissions-webhooks-ratelimits.md`**; the token-chain + clone-auth quotes live in **`references/github-app-tokens-and-clone.md`**.

## The method (when you must re-verify or find a new fact)

1. **GitHub docs (`docs.github.com`) render server-side HTML** — `curl -sL` returns full HTML (no JS shell, unlike AWS/Stripe/Cloudflare). Download to file, strip tags locally; pages are large (60–700 KB), so don't grep the stream:
   ```
   curl -sL "https://docs.github.com/en/…/page" -o /tmp/gh.html
   python3 -c "import re; t=re.sub(r'<[^>]+>',' ',open('/tmp/gh.html').read()); t=re.sub(r'\s+',' ',t); …"
   ```
2. **Octokit source lives on `raw.githubusercontent.com`** — fetch files by path, no clone needed for a read-only snapshot. The three files that answer cache-lifecycle questions: `src/cache.ts` (TTL/key), `src/get-installation-authentication.ts` (mint + concurrent-de-dup), `src/hook.ts` (request hook + 401-retry). Pin to `main` (or a tag) and note the date.
3. **REST reference page (`/rest/apps/apps`) is a 700 KB index** — grep for the endpoint verb (`Create an installation access token`); the response-schema block (`{token, expires_at, permissions, …}`) is the citable artifact.
4. **Quote verbatim with the URL.** Same standard as `docs-verification` — paraphrasing is how verification drifts into fabrication. Re-verify live before citing any number; these pages move.

## Pitfalls

- **Citing an old deep URL.** GitHub restructured the docs tree ("developers/apps" → "apps/creating-github-apps"). Old ADRs/tickets carry dead slugs. Navigate from a known-stable index page or check the current path before citing.
- **Assuming auth-app proactively refreshes.** It does not — it's lazy (TTL-eviction-then-re-mint). If you have a long-running operation holding a token (e.g. a 20-min clone), it can expire mid-op; the *worker*, not auth-app, must catch and retry with `refresh:true`.
- **Token-in-URL in a multi-tenant server.** Embedding the token in the clone URL leaks it to process listings. This is a real production security issue, not a theoretical one — use `GIT_ASKPASS` or a credential helper.
- **`--branch <sha>` is invalid.** A common wrong guess for cloning a PR head by SHA. Use fetch-then-checkout.
- **Confusing App-JWT limits with installation-token limits.** The JWT lives ≤10 min; the installation token lives 1 hour. Different ceilings, different purposes — don't cite one when you mean the other.
- **Asserting auth-app behavior from the README alone.** The README documents the public contract; the cache TTL (59 min), the 15 000 cap, and the concurrent-de-dup live in source. Cite source for internals, README for API.
- **Assuming `Issues: Write` is needed to edit a PR comment.** It isn't. PR comments use the shared `/issues/comments` endpoints that accept "at least one of" Issues OR Pull requests permission — `Pull requests: Write` alone suffices. Adding `Issues: Write` is an over-broad permission request that makes installers suspicious.
- **Confusing PR issue comments with PR review comments.** The "living summary" comment a bot edits in place is a PR *issue* comment (`PATCH /issues/comments/{id}`). PR *review* comments are inline diff annotations (`PATCH /pulls/comments/{id}`) — a different endpoint family for a different feature. Pick the right one.
- **Subscribing to `push` for a PR-triggered bot.** The `push` payload has `ref` + `after` SHA but **no PR number** — the app must call the PRs API to even know a PR exists for that branch. Subscribe to `pull_request` instead; `action: synchronize` is the documented "commits pushed to PR branch" signal and carries the PR number + head SHA inline.
- **Using `==` to compare webhook signatures.** GitHub's docs explicitly forbid plain equality ("Never use a plain == operator") — timing attack. Use `hmac.compare_digest` / `secure_compare` / `crypto.subtle.verify`.
- **Thinking the 5 000/hr primary limit is the binding constraint for a comment bot.** The secondary **content-creation limit (500/hr)** is tighter for write-heavy bots. At ~1 create + 1 edit per analysis, ~250 analyses/hr hits the content ceiling before the 5 000/hr REST ceiling. Still ample for a single-installation PR bot, but cite the right number.
- **Counting the git clone against the REST rate limit.** It doesn't. Only REST API calls consume the 5 000/hr budget; `git clone --depth=1` over HTTPS is a Smart-HTTP git operation, not a REST call. Only Git LFS has a separate API bucket.

## Verification (self-check before reporting)

- [ ] Did I re-verify the quoted fact against the live page (not just the reference bank)?
- [ ] For auth-app internal-behavior claims, did I cite the source file (`cache.ts`/`hook.ts`/…), not just the README?
- [ ] For clone-auth recommendations, did I flag the token-leakage caveat if recommending URL-embedding?
- [ ] Did I distinguish GitHub's documented guarantees from octokit's implementation choices?
- [ ] For permission claims, did I cite the permissions reference (`/rest/authentication/permissions-required-for-github-apps`) for the endpoint→scope mapping, and note the "at least one of" rule for shared endpoints?
- [ ] For webhook-secret claims, did I quote the algorithm + note timing-safe comparison + give the test vector?
- [ ] For rate-limit claims, did I distinguish the primary (5 000/hr) from the secondary content-creation (500/hr) limit, and note that git clone doesn't consume the budget?

## Output shape

A findings file (Markdown) or inline text (per task instruction): a per-question verdict with the verbatim quote + URL, then a recommendation. For a kanban council, post a condensed `[swarm:evidence]` scorecard to the blackboard. **If the task says "do not write files," return the findings as text — do not create a file.**

## Related skills

- `docs-verification` — the parent method for verifying claims against official docs (any vendor). This skill is the GitHub-App-domain specialization with a knowledge bank.
- `source-code-verification` — verifying claims against source code generally. The auth-app-internals section of this skill applies its method to the octokit repo.
- `research` (mattpocock) — the general research umbrella.

## Reference

- `references/github-app-tokens-and-clone.md` — the knowledge bank: token chain, verbatim anchors (1-hour expiry, JWT claims, clone scheme, rate-limit numbers), @octokit/auth-app cache internals (59-min TTL, 15 000 cap, concurrent de-dup, 401-retry), shallow-clone auth options with the security caveat, and per-source extraction recipes. Read this first on any GitHub-App task; re-verify live before citing numbers.
