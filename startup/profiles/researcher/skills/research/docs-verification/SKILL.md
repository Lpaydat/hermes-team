---
name: docs-verification
description: "Verify technical claims against official documentation — Cloudflare/AWS/nginx/other vendor docs — by extracting verbatim quotes from the source, not paraphrasing. Use when the ask is 'confirm from the docs that X', 'what do the official docs say about Y', or fact-checking an ADR/spec against primary documentation. The source of truth here is the documentation site itself. Sibling to source-code-verification (which covers source code); load THAT one when the claim is about how code is implemented, load THIS one when the claim is about what the docs guarantee."
---

# Documentation verification

Verify claims against the official documentation, quoting verbatim. Every claim you report must trace to a named doc page and an exact quoted phrase — not a paraphrase. The docs are the authority for this class of task; if you can't find it in the docs, say so.

## When to load

- "Confirm from the Cloudflare docs that X is per-data-center."
- "What does the ADR claim, and is it actually what AWS/nginx/Cloudflare docs say?"
- "Find the typical [latency / cost / behavior] from official sources."
- "What does RFC NNNN / the OAuth 2.0 Security BCP say about X?" / "Quote the relevant section of the spec."
- "Fact-check these N claims; report URLs; do NOT fabricate."
- Any request ending in "per the docs" / "from primary sources" / "cite the source" / "quote the spec."

If the question is about **how code is implemented** (cloning a repo, reading source), load `source-code-verification` instead. This skill is for **documentation** as the source of truth.

## The method (in order)

### 1. Read the ADR / spec / claim list first

If you're validating a prior decision doc, read it in full before touching the web. You need to know the *exact wording* of each claim so you can confirm-or-refute verbatim, not re-derive the question. Note the claim's specifics (numbers, plan tiers, code names) — those are the falsifiable parts.

### 2. Extract clean text — try the markdown endpoint before the browser

Modern docs sites (Cloudflare, AWS, many Docusaurus/Starlight sites) render from markdown and often expose it directly. This bypasses bot-detection walls AND browser-snapshot truncation on long pages:

- **Cloudflare**: `https://developers.cloudflare.com/<path>/index.md` → returns YAML frontmatter + clean markdown. Fallback: `/<path>/markdown/index.md`. This was the single highest-leverage move in practice — full untruncated text, no JS, no bot wall.
- **AWS docs**: pages carry a **"Download Markdown"** link near the title. Grab that file; it's the authoritative source-text artifact.
- **JS-rendered docs sites (Auth0/Mintlify, some Docusaurus):** `curl` returns a multi-MB JS shell with no content, and `browser_snapshot` truncates before reaching the article. Use `browser_console` with a DOM `.innerText` extraction (`document.querySelector('article')?.innerText ?? document.querySelector('main')?.innerText ?? document.body.innerText`) — it returns the full hydrated text in one call, untruncated. See `references/doc-extraction-recipes.md` § "JS-rendered docs sites."
- **Static-HTML sites (nginx.org)**: `curl -sL -o /tmp/<name>.html` then strip locally.

**Do NOT pipe `curl` output into a script interpreter** (`curl … | python3`). The shell safety guard blocks this as untrusted-code execution. The correct pattern is **download-to-file-then-process**:
```
curl -sL "https://…/page" -o /tmp/page.md   # or .html
```
then `read_file` (for markdown) or a local extraction script that reads `/tmp/page.html` from disk. Download-then-process is guard-friendly AND leaves the artifact on disk for re-reading.

See `references/doc-extraction-recipes.md` for concrete per-site patterns (Cloudflare Availability-table parsing, AWS CloudWatch metric-definition parsing, nginx `proxy_cache_valid` quoting) — load it on your first docs-scraping task.

### 3. Quote verbatim, never paraphrase for the verdict

When confirming or refuting a claim, the evidence is a **direct quote** in quotes, with the page URL. Paraphrasing is how verification drifts into fabrication. If the docs say "Counters are not shared across data centers, with the exception of data centers associated with the same geographical location," quote that — don't summarize as "per-DC."

### 4. Distinguish "documented" from "empirically observed"

A claim like "API Gateway adds 20-50ms" may be a real, widely-reported observation that **no doc ever states as a number**. AWS *defines* overhead as `Latency − IntegrationLatency` (a documented metric) but publishes no ms figure. Report this distinction explicitly:
- **CONFIRMED** = the docs say it, verbatim, cite the URL.
- **EMPIRICAL / community-reported** = real and probably accurate, but the source is a benchmark/blog, not the official docs. Name the gap; point to the closest official construct (e.g. the metric definition) as the citable anchor.
- **NOT FOUND** = you searched and couldn't locate it. Say so. Do not invent a URL.

### 5. Check the right sub-page, not just the overview

Plan tiers, availability matrices, and parameter tables often live on a *sub-page*, not the page a claim cites. Cloudflare's per-DC statement is on the "Request rate calculation" page; the plan-tier availability table is on the *overview* page's `#availability` anchor; the characteristic list is on the "parameters" page. If a claim is about "what plan tier supports X," you must find the **Availability** table specifically — guessing from the parameters page alone gives the wrong answer.

### 6. Report a scorecard

A verdict table (claim → CONFIRMED / REFUTED / WRONG-REASON / EMPIRICAL / NOT-FOUND, each with URL) is the output shape the asker can act on fastest. Flag "WRONG-REASON" explicitly: a claim whose *conclusion* holds but whose *stated justification* is incorrect (e.g. ADR says "Business plan" when the real bar is Enterprise). The conclusion still works; the reasoning needs fixing, and only a human knows if that matters downstream.

## Pitfalls

- **Citing the overview when the detail is on a sub-page.** The Availability table, the exact counter-language, and the parameter definitions are usually split across 3-4 sibling pages. A claim sourced only to the overview URL is often imprecise.
- **Paraphrasing the verdict.** "The docs confirm per-DC counting" is weaker than quoting the sentence. Verbatim-or-nothing for the evidence; paraphrase only in the scorecard summary.
- **Asserting a number the docs never published.** "20-50ms" style claims are usually community benchmarks. Trace to the closest official anchor (a metric definition, a spec line) and label the number empirical.
- **Wrong plan tier from the wrong table.** Free/Pro/Business/Enterprise columns differ sharply on which *characteristics* (IP-only vs Headers vs Custom) are available. Read the exact row + column. ADRs commonly cite the wrong tier here.
- **Forgetting the override caveats.** A doc that says "302 is cached by default" will also say (often nearby) the exceptions: `Set-Cookie` responses aren't cached; `Cache-Control`/`Expires` headers override the directive. Confirm the happy path AND read for the exceptions — both are in the same doc paragraph.
- **Truncation masquerading as absence.** Browser snapshots truncate long pages. If a page "doesn't mention" something, verify via the markdown/HTML artifact (full text) before claiming absence. Absence claims need the full source, same as in source-code-verification. On **JS-rendered sites** (where curl gives you a shell, not content), the equivalent move is `browser_console` DOM extraction (`document.querySelector('article').innerText`) — it returns full untruncated text where `browser_snapshot` cuts off. See `references/doc-extraction-recipes.md` § "JS-rendered docs sites."
- **AWS pricing numbers are trapped in images.** The rendered tables on `aws.amazon.com/<service>/pricing/` are `<img>` tags — `document.querySelectorAll('table')` returns `0`, and grepping the HTML for `$X.XX` finds only the surrounding prose. The numbers themselves are unreachable as text. **Use the AWS Price List API instead** (`https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/<ServiceCode>/current/index.json`) — same data, machine-readable, dated, with verbatim tier-description strings you can quote. Run `scripts/parse-aws-price-list.py` on the downloaded JSON rather than hand-rolling a parser. See `references/doc-extraction-recipes.md` § "AWS pricing pages — the image-table trap".
- **AWS deep links now silently redirect to the guide root.** Direct `browser_navigate` or `curl` to an old/deep AWS docs URL (e.g. `…/cognito/…/token-handling.html`) returns a ~1KB meta-refresh+JS stub that bounces you to `what-is-<service>.html` — no error, just the wrong page. Both `browser_navigate`'s final `url` and `curl -sL` hide this. **Navigate the expanding sidebar tree** (root → expand top section → expand nested section → click leaf) to reach current URLs, then extract via `browser_console`. The "Download Markdown" link still works once you're on the right page. See `references/doc-extraction-recipes.md` § "Deep-link redirect wall".
- **Restructured docs portals 404 on old deep URLs (Okta, GitLab, Atlassian).** Unlike the AWS meta-refresh wall (silent redirect to root), these portals return a real HTTP **404 "Page not found"**. Old deep URLs you recall or find in ADRs/old tickets are unreliable, and guessing the new slug by extrapolation mostly 404s too — slugs are *renamed*, not just relocated. Don't burn turns guessing. Instead: `browser_navigate` to a known-stable index/hub page, `browser_click` the nav link for the topic, then read `location.href` for the canonical current URL. See `references/doc-extraction-recipes.md` § "Restructured docs portals."
- **General search engines are blocked from automated IPs — don't open a research session with a search query.** Google returns a `google.com/sorry` CAPTCHA page; DuckDuckGo returns a 202 JS challenge with no organic links; Bing renders but geo-redirects non-local IPs to unrelated localized results. `site:` operators make it worse. For "find which primary source says X" tasks, go **direct to the known source domain's index** (e.g. `stripe.com/blog/engineering`, `linear.app/blog`, `shopify.engineering/`), render it in the browser, and extract article links via `browser_console` DOM query (curl returns empty JS shells on these indexes). For dead/moved URLs, use the **Web Archive** (`archive.org/wayback/available?url=` for existence, `web.archive.org/web/<YEAR>/<url>` for the snapshot) rather than guessing renamed slugs. See `references/web-source-discovery.md` for the full discovery ladder and per-engine failure modes.

## Verification (self-check before reporting)

- [ ] Is every CONFIRMED backed by a verbatim quote + URL?
- [ ] Is every number labeled as either documented or empirical, with the closest official anchor cited for empirical ones?
- [ ] Did I find the specific sub-page (Availability table, metric definitions), not just the overview?
- [ ] Did I read the surrounding paragraph for exceptions/overrides, not just the matching sentence?
- [ ] Is every "not found" genuinely searched (via the full markdown/HTML artifact, not a truncated snapshot)?
- [ ] Did I distinguish WRONG-REASON (conclusion holds, justification wrong) from REFUTED (conclusion itself wrong)?

## Output shape

A findings file (Markdown) with: a scorecard table (claim → verdict → URL), then per-claim detail with verbatim quotes and the distinction between documented/empirical, then a "URLs cited" list. If part of a kanban council, post a condensed `[swarm:evidence]` version of the scorecard to the shared blackboard as a comment so downstream workers inherit the verdicts.

## Related skills

- `source-code-verification` — the sibling. Load it when the claim is about **how code is implemented** (clone the repo, grep the source). Load THIS skill when the claim is about **what the docs say**.
- `research` (mattpocock) — the general research umbrella; this skill specializes its "primary sources" step for the docs-as-source-of-truth case.

## Reference

- `references/doc-extraction-recipes.md` — per-site extraction patterns: Cloudflare `index.md` markdown endpoints, AWS "Download Markdown" link + CloudWatch metric-definition parsing, nginx HTML strip-and-grep, the `curl`-to-file guard workaround, and the Cloudflare Availability-table parsing that catches wrong-plan-tier ADR errors. **Now also covers IETF RFCs and Internet-Drafts** (`rfc-editor.org/rfc/rfcNNNN.txt` — clean plain text, no stripping), the **draft→RFC verification pattern** (check the datatracker canonical URL before citing a draft — it may have become an RFC), and **absence-as-evidence** (grep the full `.txt` to prove a negative, e.g. "RFC 9700 doesn't cite RFC 7009"). Read this on your first docs-scraping task, and the IETF section on any protocol/security-spec verification.
- `references/web-source-discovery.md` — the discovery ladder when you need to *find* the source URL and search engines are blocked (Google CAPTCHA, DDG 202 challenge, Bing geo-garbage): go direct to the source domain index, render + `browser_console`-extract links from JS-rendered blog indexes, fall back to Web Archive for dead/moved URLs. Read this when discovery — not extraction — is the bottleneck.
- `references/rate-limiting-algorithms.md` — condensed, citable facts on what rate-limiting algorithm each major gateway uses (AWS = token bucket; Cloudflare = fixed-window counter; Stripe = per-second rate + concurrency; GitHub = windowed counter), with verbatim anchors and the **proof that token-bucket burst is tunable away** (`capacity` governs burst independently of `rate`; `capacity = rate` converges to a 1-second sliding-window counter). Jump-starts design-doc / ADR fact-checking when a claim asserts "gateway X uses algorithm Y" or "token-bucket burst is unavoidable." Re-verify live before citing numbers.
- `references/oauth-refresh-token-rotation.md` — the foundational OAuth 2.0 Security BCP (RFC 9700) authority **first** (Q0: what the spec mandates on rotation/reuse-detection/sender-constraining, with a normative-force cheat sheet and the key finding that RFC 9700 does NOT cite RFC 7009), then condensed provider data models (**Auth0/Okta/Cognito/Keycloak/Firebase**: what's stored per refresh token, keyed by what) + verdicts on recurring auth-architecture tensions: Q2 (stateless rotation — no), Q4 (signature-only vs admin revocation — incompatible), Q5 (replay race — grace window mandatory; Auth0 ships it OFF by default), Q6 (JWT vs opaque format for refresh tokens — opaque wins; self-contained benefit doesn't apply since refresh tokens never reach resource servers), **Q7 (crash-recovery vs theft disambiguation — the false-positive reuse-alarm problem: RFCs treat it as unsolvable by the server; no vendor does two-tier detection; idempotency keys are standardized generically but unused by auth frameworks; Keycloak issue #49213 documents a 99.1% false-positive rate in production)**. Jump-starts OAuth2/OIDC rotation + token-format + crash-recovery research; re-verify live before citing numbers.
- `scripts/parse-aws-price-list.py` — parses a downloaded AWS Price List API `index.json` into per-SKU tier descriptions + per-unit USD. Use it whenever a pricing claim needs exact numbers (the rendered pricing pages carry tables as images, so this is the only reliable path). Run: `python3 scripts/parse-aws-price-list.py /tmp/<svc>_pricing.json --region us-east-1 --keyword Request`.
