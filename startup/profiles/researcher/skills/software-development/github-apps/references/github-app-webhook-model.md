# GitHub App webhook model — condensed reference

Condensed, citable facts on how a GitHub App receives and verifies webhooks, with the recurring design finding that **the canonical "push to PR branch" signal is `pull_request` action `synchronize`, NOT the `push` event.** Jump-starts ADR / architecture fact-checking when a claim asserts "the app listens for push events on PR branches" or asks which webhook events/permissions an app needs. Re-verify live before citing exact field names (GitHub periodically adds payload fields).

Primary source for all quotes below: `https://docs.github.com/en/webhooks/webhook-events-and-payloads` unless noted.

---

## Q1. "Push to PR branch" — use `pull_request.synchronize`, NOT `push`

This is the #1 recurring misconception in GitHub-App-for-PR-analysis designs. The `push` event and the `pull_request` event are **different event types** that both fire for the same underlying git operation (commits pushed to a branch that has an open PR), but they carry different context:

| | `push` event | `pull_request` event, action `synchronize` |
|---|---|---|
| Carries PR number? | **No** — only the branch `ref` | **Yes** — top-level `number` |
| Carries head SHA? | `after` (post-push SHA) | `pull_request.head.sha` |
| Carries head ref / base ref? | `ref` only | `pull_request.head.ref`, `pull_request.base.ref` |
| Knows it's a PR (vs main)? | **No** — must call `GET /pulls?head=<owner>:<branch>&state=open` to find out | **Yes** — it IS the PR event |
| Permission needed | Contents: read | Pull requests: read (write to comment) |

**Verdict:** Subscribe to **`pull_request` events only**. Route on `action ∈ {opened, synchronize, reopened, closed}`. Do **not** subscribe to `push`. This is the GitHub-documented standard pattern: the official "Building a GitHub App that responds to webhook events" tutorial registers an app subscribed to the "Pull request" webhook event, reads `action`, and posts a comment — it never touches `push`.

> When commits are pushed to a branch with an open PR, GitHub fires BOTH `push` and `pull_request{action:synchronize}` *if subscribed to both*. The `synchronize` event carries the PR context; `push` carries only the branch ref. For a PR-analysis app, `pull_request` strictly dominates.

Cite: `https://docs.github.com/en/apps/creating-github-apps/writing-code-for-a-github-app/building-a-github-app-that-responds-to-webhook-events`; best-practices "subscribe to the minimum number of events" at `https://docs.github.com/en/webhooks/using-webhooks/best-practices-for-using-webhooks`.

---

## Q2. Payload fields the analysis needs

### `pull_request` payload (the one you want)
- `action` (string, Required) — `opened` / `synchronize` / `reopened` / `closed` / `edited` / `labeled` / …
- `number` (integer, Required) — **the PR number.**
- `pull_request` (object, Required) — full PR object (same shape as REST `GET /pulls/{number}`):
  - `pull_request.head.sha` — head commit SHA (analysis target).
  - `pull_request.head.ref` — head branch name.
  - `pull_request.head.repo.full_name` — `owner/repo` of the head (differs from base for forks).
  - `pull_request.base.ref`, `pull_request.base.sha` — base branch + SHA.
  - `pull_request.state` (`open`/`closed`), `pull_request.title`, etc.
- `repository` (object, Required) — `repository.full_name` (the repo the event occurred in).
- `installation` (object) — present "when the event is configured for and sent to a GitHub App"; carries **`installation.id`** (needed to mint installation tokens).
- `sender` (object, Required), `organization`, `enterprise` (optional).

### `push` payload (for completeness — usually don't subscribe)
- `ref` (string, Required) — "The full git ref that was pushed. Example: `refs/heads/main` or `refs/tags/v3.14.1`."
- `after` (string, Required) — "The SHA of the most recent commit on ref after the push." (Prefer over `head_commit.id` for the post-push SHA.)
- `before` (string, Required), `head_commit` (object|null), `commits` (array, max 2048), `repository.full_name`, `installation.id`, `created`, `deleted`, `forced`.

> Cite: `https://docs.github.com/en/webhooks/webhook-events-and-payloads#pull_request` and `…/#push`. For the same schema rendered as plain tables (no collapsed disclosures), use the REST-API reference mirror at `https://docs.github.com/en/rest/using-the-rest-api/github-event-types` (the `PullRequestEvent` / `PushEvent` sections). Note: that mirror's `PullRequestEvent.action` list is occasionally a *subset* (e.g. it may omit newer actions like `synchronize`/`ready_for_review`) — cross-check any action you rely on against `@octokit/webhooks` type definitions or a real delivery payload.

---

## Q3. Delivery guarantees & HMAC verification

**At-least-once, with manual redelivery.** GitHub retries on non-2xx (or >10s timeout) and supports manual redelivery via the UI or the `deliveries` REST API.

**Dedup key — `X-GitHub-Delivery` is a GUID, stable across redeliveries.** A redelivery reuses the same GUID as the original ("If you request a redelivery, the `X-GitHub-Delivery` header will be the same as in the original delivery"). → The app MUST be idempotent and dedupe on this GUID. The `deliveries` API response also carries a `redelivery` boolean.

**Signature verification — `X-Hub-Signature-256` (HMAC-SHA-256 over the raw body):**
- Compute `expected = "sha256=" + hex(HMAC-SHA256(key=WEBHOOK_SECRET, msg=<raw request body bytes>))`.
- Compare against the header value with **constant-time comparison** (`hmac.compare_digest` / `Rack::Utils.secure_compare`).
- The HMAC key is the **webhook secret**; the message is the **raw bytes received** (do NOT re-serialize JSON — read the exact body).
- Legacy `X-Hub-Signature` uses SHA-1; GitHub recommends `X-Hub-Signature-256`.
- Use `@octokit/webhooks`' `verify(body, signature)` (the SDK handles this; shown in the docs' TS example).

**Delivery headers (all):**
- `X-GitHub-Event` — event name (e.g. `pull_request`). Read this to route.
- `X-GitHub-Delivery` — event GUID (dedup key).
- `X-GitHub-Hook-ID` — webhook identifier.
- `X-Hub-Signature-256` — HMAC-SHA-256 signature (verify this).
- `User-Agent` — always prefixed `GitHub-Hookshot/`.
- `X-GitHub-Hook-Installation-Target-Type` / `-ID`.

**10-second response deadline.** "Your server should respond with a 2XX response within 10 seconds of receiving a webhook delivery. If your server takes longer than that to respond, then GitHub terminates the connection and considers the delivery a failure." → **Enqueue and ack fast; process async via a queue.** Do not run analysis inline in the webhook handler.

Cite: `https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries`; `https://docs.github.com/en/webhooks/using-webhooks/best-practices-for-using-webhooks`; `https://docs.github.com/en/webhooks/using-webhooks/handling-webhook-deliveries`.

---

## Q4. Ordering — there is NONE

GitHub does **not** guarantee in-order webhook delivery. The docs state no per-event ordering contract; deliveries are individual HTTP POSTs that can be retried, redelivered, and arrive out of order (B delivered before A; a redelivery of A resurrected after B).

**Handling pattern (deduce from the delivery model — no ordering contract is promised):**
1. **Idempotency:** dedupe on `X-GitHub-Delivery` GUID.
2. **Staleness guard:** tag each analysis with `pull_request.head.sha`. Before writing the living comment, compare the in-flight SHA to the **current** PR HEAD (re-fetch the PR, or track last-seen head SHA per PR). If stale, **discard** (last-write-wins on head SHA).
3. **Comment-edit race:** editing one living comment in place (`PATCH /repos/.../issues/comments/{id}`) can race under concurrent deliveries; include the head SHA in the body and let the freshest SHA win.

> Treat webhooks as an at-least-once, unordered stream. Never assume `synchronize` for push-A arrives before `synchronize` for push-B.

---

## Q5. Quick: events & permissions for a PR-analysis app

- **Subscribe:** `Pull request` (only). Do NOT subscribe to `push`.
- **Route on action:** `opened` (first analysis + first comment), `synchronize` (re-analyze, edit comment), `reopened` (refresh), `closed` (stop tracking).
- **Permissions:** `Pull requests: write` (read + post/edit comments). Clone via installation token additionally needs `Contents: read`. `Metadata: read` is required-by-default.
- **Comments use the issues-comments API** (`PATCH /repos/{owner}/{repo}/issues/comments/{id}`), because PRs are issues in GitHub's data model — confirmed at `https://docs.github.com/en/rest/pulls/pulls` ("Pull requests are a type of issue… handled by the REST API to manage issues").

---

## TL;DR scorecard for an architect

| Claim / question | Verdict | Anchor |
|---|---|---|
| "Subscribe to push to detect PR-branch pushes" | **REFUTED (use pull_request.synchronize)** | GitHub App tutorial subscribes to "Pull request" only |
| Does push carry the PR number? | **No** | push payload table — only `ref` |
| Does pull_request carry PR # + head SHA + head ref? | **Yes** | pull_request payload: `number`, `pull_request.head.sha/ref` |
| Webhook verification | HMAC-SHA-256, `X-Hub-Signature-256`, constant-time, over raw body | validating-webhook-deliveries |
| Is delivery exactly-once? | **No — at-least-once; redeliveries reuse the GUID** | best-practices; deliveries API `redelivery` bool |
| Ordering guaranteed? | **No** | no ordering clause in docs; model is retry/redeliver HTTP POSTs |
| Response deadline | **10 seconds** — ack then process async | handling-webhook-deliveries |
