# Slack App Distribution & Approval — Verified Facts

Verified 2026-07-17 against official `docs.slack.dev` pages.
Use when verifying claims about: external app install without
Marketplace listing, direct OAuth-URL distribution, review timelines,
workspace caps, "Add to Slack" button mechanics, or MVP launch timing.

## Authoritative sources

| Tag | Page | URL |
|-----|------|-----|
| DIST | App lifecycle & distribution | https://docs.slack.dev/app-management/distribution/ |
| REVIEW | Slack Marketplace review guide | https://docs.slack.dev/slack-marketplace/slack-marketplace-review-guide |
| SUBMIT | Distributing your app in the Slack Marketplace | https://docs.slack.dev/slack-marketplace/distributing-your-app-in-the-slack-marketplace |

## Naming: "App Directory" → "Slack Marketplace"

The old "App Directory" was renamed to the **Slack Marketplace**. Older
URLs (e.g. `api.slack.com/apps/managing-apps`) redirect or 404; the
canonical home is now `docs.slack.dev/slack-marketplace/`. Note also
that `api.slack.com` documentation has migrated wholesale to
`docs.slack.dev` — prefer the latter for any Slack platform fact.

## The 3 distribution states (DIST)

1. **Undistributed** — single workspace only. "Undistributed apps exist
   on a single workspace ... but they can't be distributed to other
   workspaces."
2. **Unlisted distributed** — installable to ANY workspace via an OAuth
   2.0 flow. **No review required.** Activated from the app dashboard:
   Manage Distribution → "Share Your App with Other Workspaces" →
   checklist → **Activate Public Distribution**. Yields:
   - an embeddable **Add to Slack button**
   - a **shareable URL** (= `https://slack.com/oauth/v2/authorize?
     client_id=XXX&scope=YYY&...`) that kicks off install on click
   - an HTML `<meta name="slack-app-id">` tag for app suggestions
   Slack's own framing (DIST): *"Distributing your unlisted app is
   perfect for when you want to test out your app by running a pilot
   for early customers."*
3. **Listed (Slack Marketplace)** — reviewed/approved; discoverable in
   the Marketplace; supports direct in-client install.

## Key verified facts

### External install WITHOUT Marketplace approval — YES (DIST)
Unlisted distribution works the instant "Activate Public Distribution"
is clicked. No submission, no review, no approval. The OAuth URL alone
suffices for users in other workspaces to install.

### Workspace/user cap for unlisted apps — NONE (DIST)
No numeric cap. DIST explicitly anticipates growth to "potentially
hundreds" of workspaces. (The "5 active workspaces" figure that appears
in the docs is a **prerequisite to SUBMIT** to the Marketplace, not a
ceiling on unlisted installs — see REVIEW/SUBMIT.)

### Marketplace review timeline — ~10 weeks new submissions (REVIEW, SUBMIT)
| Phase | Duration |
|-------|----------|
| Preliminary review (listing info + OAuth sanity) | up to **10 business days** to feedback |
| Functional review (reviewer installs + tests) | up to **10 weeks** (new) / **6 weeks** (updates to published apps) |
| Queue position | **Resets** on every preliminary-round resubmission |

Slack guidance (REVIEW): *"we strongly recommend that the timeline for
an app's launch includes your app's submission and review as a milestone
with at least a few weeks to spare"* and *"we will not be able to skip
or accelerate the review process."*

### Marketplace is OPTIONAL, not a gate (DIST, SUBMIT)
Marketplace adds discoverability + trust signal + in-client direct
install + App Suggestions. It is NOT a prerequisite for external OAuth
installs. Unlisted and Marketplace-listed are independent parallel paths.

### Prerequisites to SUBMIT to Marketplace (REVIEW, SUBMIT)
- App fully functional, publicly available, installs correctly.
- Tested end-to-end (install, onboard, use, uninstall) on a workspace
  that is NOT the dev workspace.
- **Installed on ≥5 active workspaces** (active = used in past 28 days,
  not sandboxes). Apps not meeting this are blocked from submission.
  (Exception: Discovery API security/compliance partners.)
- App must not be in private beta / still being built.
- Must not fall into an excluded category (message export/backup,
  destructive behavior, financial/crypto/NFT transactions, LLM training
  on Slack data, standalone sentiment analysis, etc. — see SUBMIT).

### Caveat: admin-managed workspaces can block unlisted apps (DIST)
*"Some workspaces will restrict app installation so that only workspace
administrators can provide authorization. Other workspaces may only
allow the installation of apps officially listed in the Slack Marketplace."*
So while the unlisted/OAuth path is officially uncapped, some target
workspaces (enterprise/admin-managed, or Marketplace-only) will reject
unlisted installs or require admin approval. Mitigation: target
free/standard workspaces; expect admin-approval friction on enterprise.

## Pattern: verifying a Slack platform claim

1. Go to the section landing page you know (e.g.
   `docs.slack.dev/slack-marketplace/`).
2. If you need a sub-page whose URL you're unsure of, dump the sidebar
   `href`s via `browser_console` (see the "Guessed docs URLs that 404"
   pitfall in the parent SKILL.md) — don't guess slugs.
3. Extract full page text with
   `document.querySelector('article').innerText` (the snapshot truncates
   long pages).
4. Quote verbatim with the source URL; note whether the claim is
   load-bearing for the plan's timeline/scope assumptions.
5. Distinguish what the docs SAY from what they ALLOW — Slack's
   recommendations ("intended for commercial distribution") are
   guidance, not hard gates.

## Cross-reference

For Slack API scope/event/method verification (e.g. `reactions:read`
vs `reaction_added`, `channels:history` vs `message.channels`), see the
companion reference `slack-api-doc-verification.md` — that covers the
API surface; this file covers distribution/approval/timeline.
