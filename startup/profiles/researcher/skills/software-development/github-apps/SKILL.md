---
name: github-apps
description: "Research and design the GitHub App integration layer — webhook event selection, payload shapes, HMAC verification, delivery guarantees, installation-token auth, and clone permissions — against GitHub's primary docs. Use when the ask is 'which webhook events should our GitHub App subscribe to', 'how does the app authenticate a git clone', 'verify this ADR's webhook/token/permission claims against the docs', or designing any bot that reacts to PR/push activity. The source of truth is docs.github.com; quote it verbatim."
---

# GitHub App integration research & verification

Design or fact-check the GitHub-App integration layer for a service that receives webhooks and acts on repositories (clone, analyze, comment). Every claim must trace to a named `docs.github.com` page with a verbatim quote. The docs are the authority; if you can't find it there, say so.

## When to load

- "Our app receives push-to-PR-branch webhooks — what's the payload shape?" / "Does it need `pull_request` events too?"
- "Which webhook events and repository permissions does our GitHub App need?"
- "How is the webhook secret verified (HMAC)? What are the delivery guarantees (at-least-once, redelivery, ordering)?"
- "How does the app authenticate a server-side `git clone` (installation token as credential)?"
- Fact-checking an ADR/spec claim about webhooks, tokens, permissions, or rate limits against primary docs.
- "Post findings to the blackboard" / "cite everything" / "don't design the deployment — just give evidence."

Load the sibling `docs-verification` skill for the *general* docs-extraction methodology (markdown endpoints, `browser_console` DOM extraction, the `curl`-pipe guard). THIS skill specializes it for GitHub's docs site and the GitHub-App domain.

## The recurring misconception — settle it first

**The canonical "push to PR branch" signal is `pull_request` action `synchronize`, NOT the `push` event.** They are *different event types* that both fire for the same git operation (commits pushed to a branch with an open PR), but they carry different context:

| | `push` | `pull_request` action `synchronize` |
|---|---|---|
| PR number in payload? | **No** — only branch `ref` | **Yes** — top-level `number` |
| head SHA? | `after` | `pull_request.head.sha` |
| head/base ref? | `ref` only | `pull_request.head.ref`, `pull_request.base.ref` |
| Knows it's a PR? | **No** — must call `GET /pulls?head=…&state=open` | **Yes** — it IS the PR event |

**Default recommendation (cite the official tutorial + best-practices):** subscribe to **`Pull request`** events only; route on `action ∈ {opened, synchronize, reopened, closed}`; do **not** subscribe to `push`. GitHub's own "Building a GitHub App that responds to webhook events" tutorial registers an app subscribed to the "Pull request" webhook event, reads `action`, and posts a comment — it never touches `push`. The best-practices doc says "only subscribe to the webhook events that you need."

For the full payload field tables, the HMAC algorithm, delivery/ordering guarantees, and a claim-by-claim scorecard, read `references/github-app-webhook-model.md` on your first GitHub-App task.

## Method

### 1. Read the ADR / spec / question list first
Know the *exact wording* of each claim so you can confirm-or-refute verbatim, not re-derive. Note falsifiable specifics (event names, action values, permission names, SHA field names).

### 2. Extract GitHub docs — use the REST-API reference mirror, NOT the collapsible webhooks page
**⚠️ The webhooks "events & payloads" page (`/en/webhooks/webhook-events-and-payloads`) renders each event's actions in a collapsed `<details>` disclosure that shows only the DEFAULT action.** For `pull_request` the default-rendered action is `assigned` — both the accessibility snapshot AND a direct `browser_console` `document.querySelectorAll('button')` returned only `["assigned"]`. The `synchronize` action (the one a PR-analysis app needs) is hidden behind the disclosure and is not extractable without forcing each one open.

**✅ Use the REST-API reference mirror instead:** `/en/rest/using-the-rest-api/github-event-types` renders the SAME schema as plain HTML tables with no disclosures — the `PullRequestEvent` and `PushEvent` sections list every action value and every payload field in one page. Download or `browser_console`-extract it. (Note: that mirror's `PullRequestEvent.action` list is occasionally a *subset* — e.g. it may omit newer actions like `synchronize`/`ready_for_review` — so cross-check any action you rely on against the `@octokit/webhooks` type definitions or the actual payload of a real delivery.)

For the webhook *event-overview* prose ("This event occurs when…", availability, permission-required-to-subscribe), the webhooks page IS fine — only the per-action payload tables are collapsed.

### 3. Quote verbatim, label documented vs empirical
Every verdict backs to a direct quote + URL. Distinguish **CONFIRMED** (docs say it, verbatim) from **EMPIRICAL** (real, but sourced from a benchmark/blog, not the docs) from **NOT FOUND**. GitHub publishes no ms-figure for webhook delivery latency, for example — label such numbers empirical.

### 4. Verify the delivery/verification model as a set
The webhook layer is a bundle; verify them together so the architect gets the complete picture:
- **At-least-once** delivery; **redelivery reuses the same `X-GitHub-Delivery` GUID** → app must be idempotent + dedupe on GUID.
- **HMAC-SHA-256** verification via `X-Hub-Signature-256` = `"sha256=" + hex(HMAC-SHA256(secret, raw_body))`, constant-time compared. Use `@octokit/webhooks`' `verify(body, signature)`.
- **10-second response deadline** → enqueue + ack fast, process async. Do NOT run analysis inline.
- **No ordering guarantee** → dedupe by GUID; gate writes on head SHA vs current PR HEAD; discard stale.

### 5. Report a scorecard
A verdict table (claim → CONFIRMED/REFUTED/WRONG-REASON/EMPIRICAL/NOT-FOUND + URL) is the fastest shape for an architect to act on. Flag WRONG-REASON (conclusion holds, justification wrong) explicitly.

## Pitfalls

- **Assuming `push` is the "push to PR branch" signal.** It is not. `push` carries no PR number and no PR context; detecting "is this branch a PR?" forces a `GET /pulls?head=…` API round-trip. Use `pull_request` action `synchronize`. See the table above.
- **Reading only the collapsed action from the webhooks page.** The `<details>` disclosure shows the default action (`assigned` for `pull_request`). You will wrongly conclude "pull_request only has an `assigned` action." Pivot to `/en/rest/using-the-rest-api/github-event-types`.
- **Re-serializing JSON before HMAC verification.** The signature is over the **raw request body bytes**, exactly as received. Re-`JSON.parse`→`JSON.stringify` changes byte ordering and the check fails silently. Read the raw body.
- **Trusting webhook ordering.** GitHub guarantees none. Two `synchronize` events for the same PR (push A then push B) can arrive B-before-A, and a redelivery can resurrect A after B. Last-write-wins on head SHA.
- **Running analysis in the webhook handler.** The 10s timeout will mark deliveries failed and trigger retries. Acknowledge (2XX) within 10s and process via a queue.
- **Citing the overview URL when the detail is on a sub-page.** Webhook delivery headers, the HMAC algorithm, the redelivery behavior, and the best-practices are on FOUR sibling pages (`webhook-events-and-payloads`, `validating-webhook-deliveries`, `best-practices-for-using-webhooks`, `handling-webhook-deliveries`). Source each claim to the specific page.
- **Confusing "PR comment" endpoints.** PRs are issues in GitHub's data model. The single-living-comment pattern edits via the *issues-comments* endpoint `PATCH /repos/{owner}/{repo}/issues/comments/{id}`, not a pull-request-specific endpoint. Confirmed at `/en/rest/pulls/pulls` ("Pull requests are a type of issue").

## Verification (self-check before reporting)

- [ ] Did I settle the push-vs-synchronize question explicitly (the most common ADR error)?
- [ ] Is every CONFIRMED backed by a verbatim quote + URL?
- [ ] Did I read actions/fields from the REST-API reference table, not the collapsed webhooks disclosure?
- [ ] Did I verify the full delivery bundle (at-least-once, GUID dedup, HMAC, 10s timeout, no ordering)?
- [ ] Did I distinguish WRONG-REASON from REFUTED?
- [ ] Did I avoid designing the deployment when asked only for evidence?

## Output shape

If part of a kanban council, post findings + a scorecard as a **task comment** (the blackboard), so downstream workers inherit the verdicts via `kanban_show`. The deliverable is the evidence the architect needs — not a deployment design. (See the `research` skill for the general "write findings to a Markdown file" default; in a headless/kanban context the comment-thread handoff is usually what's wanted.)

## Related skills

- `docs-verification` — the parent methodology: markdown-endpoint extraction, `browser_console` DOM extraction, the `curl`-pipe guard, verbatim-quoting discipline. Load it for the general docs-scraping technique; THIS skill specializes it for GitHub.
- `research` (mattpocock) — general research umbrella.

## Reference

- `references/github-app-webhook-model.md` — condensed, citable facts on the GitHub App webhook model: the push-vs-synchronize scorecard, full `pull_request`/`push` payload field tables, the HMAC-SHA-256 verification algorithm, the delivery guarantees (at-least-once, GUID-stable redelivery, no ordering, 10s deadline), and a TL;DR architect scorecard. Jump-starts ADR fact-checking for any GitHub-App webhook/token/permission claim. Re-verify live before citing exact field names.
