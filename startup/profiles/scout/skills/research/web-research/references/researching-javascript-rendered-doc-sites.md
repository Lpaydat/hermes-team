# Researching JS-Rendered Documentation Sites

When investigating API/platform documentation that is a client-side rendered
SPA (React/Vue/subapp frameworks like Walmart I/O's xarc V2), the static
snapshot will be **empty** even though the page "works" in a normal browser.

## Diagnosis signals

- `browser_snapshot` returns `(empty page)` or near-zero element count
- `browser_console` expression shows `document.body.innerText.length === 0`
  but `document.body.innerHTML.length > 0`
- Console shows many empty `"source": "exception"` JS errors (40+)
- HTML contains markers like `SSR disabled for subapp` or a root
  `<div id="...">` with no children

## Workarounds when the SPA won't render in headless mode

1. **Harvest hrefs from the static shell.** Even when content doesn't render,
   the page's `<a>` tags and nav links are often in the initial HTML:
   ```js
   Array.from(document.querySelectorAll('a')).map(a => ({href: a.href, text: a.textContent.trim()})).filter(a => a.text || a.href)
   ```
   This recovered the real docs URLs (`walmart.io/docs/affiliate/`,
   `walmart.io/docs/opd/`) from the Walmart I/O homepage even though the
   docs pages themselves wouldn't render.

2. **Try the `www.` prefix.** Bare domains (`walmart.io`) returned Forbidden
   /empty; `www.walmart.io` served the full site. Always try both when one
   variant fails.

3. **Read sibling static pages.** Docs pages may be SPAs, but marketing home,
   FAQ, benefits, and onboarding pages are often server-rendered. They
   frequently contain the same links and summarize the same capabilities.
   Read them for the overview, then cite the docs URL even if you couldn't
   render it.

4. **Expand accordion FAQs.** FAQ pages use clickable `<button>` accordions
   (`aria-expanded=false`). The collapsed snapshot only shows question text —
   click each button to reveal the answer before snapshotting.

5. **Use `browser_console` to dump page text.** When the snapshot is thin but
   the page has rendered, `document.body.innerText` often returns the full
   readable content even if the accessibility tree missed it:
   ```js
   document.body.innerText
   ```

6. **Fall back to a non-headless browser.** If a JS-rendered page is the only
   source and it won't render headless, note this limitation explicitly in
   the research output and recommend the user (or a computer-use skill) open
   it in a real browser. Do NOT fabricate the content.

## What NOT to do

- Do not conclude "the API does not exist" or "the docs are broken" from a
  headless-render failure. The page works for real users; the failure is
  environment-specific and transient.
- Do not invent endpoint specs, rate limits, or response schemas you could
  not actually read. State "could not confirm from primary docs in this
  session" and cite where the answer should live.
