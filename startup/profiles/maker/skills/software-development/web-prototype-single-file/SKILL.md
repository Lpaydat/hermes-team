---
name: web-prototype-single-file
description: >-
  Build a zero-dependency, single-HTML-file interactive web prototype that calls
  a public API. Use when the user asks for a web page, widget, calculator, or
  tool that fetches data and renders it. Covers the single-file architecture,
  the input-fetch-render skeleton, inline CSS/JS conventions, and the
  browser-based verification loop. This is the fastest path from idea to
  working prototype — no build step, no npm install, no framework.
---

# Single-File Web Prototype

## When to use
- User asks for a web page, tool, calculator, dashboard, or widget
- The prototype needs to call a public API (REST) and render the result
- Speed matters more than scalability — this is a prototype, not production
- No backend, auth, or database required (or those are deferred)

## When NOT to use
- User needs a multi-file React/Vue/Next app (use that framework instead)
- Secrets/API keys must stay hidden (client-side = everything is visible)
- Production app with routing, SSR, or complex state management

## Architecture: one file, zero dependencies

Everything goes in a single `.html` file:
- `<style>` block in `<head>` — all CSS inline, no external stylesheets
- `<script>` block before `</body>` — all JS inline, no external scripts
- No build step, no bundler, no `npm install`, no framework
- Can be opened directly via `file://` or served with `python3 -m http.server`

**Why single-file:** the user can open it instantly, share it in one file, deploy
by dropping it on any static host. No toolchain friction for a prototype.

## The skeleton: input → fetch → render

Every interactive prototype follows the same shape:

```
[ input field ] → [ button ] → fetch(API_URL) → render result card
```

1. **Input** — text field + button (or just Enter key). Validate non-empty.
2. **Fetch** — `async function` using `fetch()`. Handle 404, rate-limit (403/429),
   and network errors with user-facing messages. Use `Promise.all` for parallel
   API calls.
3. **Render** — build HTML from the response data. Use template literals. Toggle
   a `.active` class on a card container to show/hide with a fade animation.

Key patterns from working prototypes:
- Disable the button during fetch, re-enable in `finally`
- Show a loading indicator with animated dots
- Clear previous results/errors on new submission
- Listen for Enter key on the input, not just button click

## Inline conventions

- CSS: use CSS custom properties or a dark gradient background for instant polish
- Add subtle animation (fade-in cards, hover transforms) — cheap, big impact
- Google Fonts via `<link>` is the ONE acceptable external dependency
- Responsive: `max-width` container + `flex-wrap` on input rows

## Public API checklist

- Does it support CORS? (most public GET APIs do — GitHub, weather, etc.)
- What's the rate limit? (GitHub unauthenticated = 60/hr per IP)
- Does it need a key? If yes, the key is visible client-side — acceptable for
  a prototype, NOT for production. Note this in the footer.
- Test the endpoint with `curl` before writing the fetch logic:
  `curl -s "https://api.example.com/endpoint" | python3 -m json.tool`

## Verification loop (REQUIRED — do not ship untested)

Every prototype must be loaded in a browser and exercised end-to-end:

1. **Serve locally:** `cd <dir> && python3 -m http.server <port> --bind 127.0.0.1`
   (run in background — it's a long-lived server)
2. **Navigate:** `browser_navigate` to `http://127.0.0.1:<port>/index.html`
3. **Happy path:** type a real input value, click the button, verify the card
   renders via `browser_snapshot` (full=true to see all text content)
4. **Error path:** type an invalid input (e.g. nonexistent API ID), verify
   graceful error message with no console exceptions
5. **Kill the server** when done

**Vision model note:** `browser_vision` may fail (429 / plan doesn't include it).
Use `browser_snapshot` with `full=true` instead — it returns the full accessibility
tree as text, which is sufficient for verifying rendered content.

## Common patterns & pitfalls

### Clipboard API falls silent on http://
`navigator.clipboard.writeText()` rejects silently on `http://` origins
(including `127.0.0.1` when testing locally). Always add a fallback:

```js
navigator.clipboard.writeText(text).then(/* show Copied UI */)
  .catch(() => {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); } catch(e) {}
    document.body.removeChild(ta);
    // show Copied UI here too
  });
```

The fallback's UI must mirror the success path — a failure on the success path
but not on fallback leaves the button stuck mid-state during local testing.

### Daily-deterministic content via seed hash

For prototypes that should show **the same content to the same viewer on the
same day but change daily** (horoscopes, daily quotes, word-of-the-day), use a
simple hash-based seed that avoids server-side state:

```js
function todayUTC() {
  const d = new Date();
  return d.getUTCFullYear() + '-' +
    String(d.getUTCMonth()+1).padStart(2,'0') + '-' +
    String(d.getUTCDate()).padStart(2,'0');
}

// djb2 string hash
function hash(str) {
  let h = 5381;
  for (let i = 0; i < str.length; i++) {
    h = ((h << 5) + h) + str.charCodeAt(i);
    h = h & h;
  }
  return Math.abs(h);
}

const seed = user.login + todayUTC();
const templateIdx = Math.floor(hash(seed) % TEMPLATES.length);
```

The key insight: combine an identity key (username, session id) + the date to
produce unique daily content per user without backend, storage, or cookies.

### Multi-variable template interpolation

When a data-driven reading has multiple slot variables ({n}, {stars}, {years},
{percent}, etc.), chain `.replace()` calls cleanly instead of building strings
with individual variables:

```js
let text = template
  .replace(/\{n\}/g, String(count))
  .replace(/\{stars\}/g, String(totalStars))
  .replace(/\{years\}/g, String(age))
  .replace(/\{percent\}/g, String(pct))
  .replace(/\{langs\}/g, String(distinct));
```

Use `g` flag on every `replace()` so a variable can appear more than once in
one template. Keep slot names grep-friendly — the same name in all templates.

## Verification loop pitfall: re-navigate after patching

When iterating — patch the HTML on disk while the server still runs — the
browser cache serves the old version. A hard re-navigate (`browser_navigate`
to the same URL, which the Hermes browser treats as a fresh load) is required
between edits. A soft `browser_snapshot` after a patch catches the stale
version and wastes a round-trip debugging something already fixed.

## Template

See `templates/single-file-api-prototype.html` — a working skeleton with input,
fetch, error handling, loading state, and a result card. Copy it and modify for
the specific API and rendering logic.
