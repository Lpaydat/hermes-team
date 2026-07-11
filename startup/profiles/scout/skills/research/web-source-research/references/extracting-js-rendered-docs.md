# Extracting Content from JS-Rendered Documentation Sites

Modern developer docs (developer.kroger.com, developer.stripe.com, and similar)
are JavaScript-rendered SPAs. The browser tools' accessibility-tree snapshot
**truncates at ~8000 chars** and often omits content hidden behind accordions,
tabs, or lazy-loaded panels. Use `browser_console` to pull the real DOM text.

## Technique 1 — Read the article body in full

After navigating to a doc page, the snapshot may be truncated or missing the
prose. Extract the full article text via a DOM expression:

```js
document.querySelector('article')
  ? document.querySelector('article').innerText.substring(0, 8000)
  : 'no article found'
```

- Pass this as the `expression` argument to `browser_console`.
- If there's no `<article>`, fall back to `document.querySelector('main')`.
- For long pages, paginate with `.substring(8000, 16000)`, etc.

This reliably returns the rendered prose even when the snapshot shows only the
nav sidebar and headings.

## Technique 2 — Expand accordions / FAQ widgets, then read

FAQ and "details" widgets render collapsed — the answers are not in the DOM
text until expanded. Two-step pattern:

1. **Expand via the snapshot's ref IDs.** `browser_snapshot` lists each
   accordion item as a button with `expanded=false` and a `[ref=@eN]`.
   `browser_click(ref='@eN')` to expand it. Batch the clicks you need.

2. **Read all expanded answers at once.** Instead of re-snapshotting (which
   re-truncates), pull the text of every open panel:

```js
(() => {
  let out = [];
  document.querySelectorAll('button[aria-expanded="true"]').forEach(b => {
    let panel = b.nextElementSibling;
    if (panel) out.push({
      question: b.innerText.trim(),
      answer:   panel.innerText.trim().substring(0, 2000)
    });
  });
  return JSON.stringify(out, null, 2);
})();
```

The selector `button[aria-expanded="true"]` + `nextElementSibling` is the most
common accordion pattern. If the widget uses `<details>`/`<summary>`, read
`document.querySelectorAll('details[open]')` instead.

## Technique 3 — Finding hidden interactive elements

When the snapshot doesn't expose a ref for an element you can see, locate it
by text and tag via the console first, then decide whether to click it
programmatically or via `browser_click`:

```js
// Enumerate candidate clickable elements matching text
document.querySelectorAll('a, button, [role="button"]').forEach(el => {
  const t = el.innerText.trim();
  if (t.includes('target phrase')) console.log(el.tagName, el.className, t);
});
```

## When to prefer this over the snapshot

- Snapshot is truncated (`[... N more lines truncated]`).
- Target content is inside an accordion/tab/modal that hasn't been opened.
- You need the full prose body of a long article page.
- The page lazy-loads content on scroll — `browser_scroll` first, then extract.

## Pitfall: SPA client-side routing

On SPAs, the URL bar may change but `browser_navigate` to a deep doc URL often
**redirects to the home/index page** (the router hasn't hydrated that route for
a cold load). When `browser_navigate` drops you at the index instead of the
target page, navigate to the index, then click through the sidebar nav links
(`browser_click` on the sidebar `<a>` refs) to reach the target page with the
router fully hydrated. The sidebar refs are stable across pages.

## Pitfall: variable name collisions in console expressions

`browser_console` evaluates expressions in the page context, which persists
across calls. If you declare a variable with `let`/`const` (e.g. `let results = ...`)
in one expression and then reuse the same name in a later expression, you get
`SyntaxError: Identifier 'X' has already been declared`. Wrap multi-statement
expressions in an IIFE: `(() => { ... })();` to avoid polluting the scope.
