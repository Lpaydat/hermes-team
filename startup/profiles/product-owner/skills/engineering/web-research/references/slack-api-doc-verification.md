# Slack API Documentation Verification

Reference for verifying Slack platform claims (OAuth scopes, event
payloads, method parameters, rate limits) against official docs.
Capture of patterns confirmed across two verification sessions
(t_2e42c12f runs, 2026-07).

## Canonical URL structure (docs.slack.dev)

Slack's developer docs migrated from `api.slack.com` to `docs.slack.dev`
(Docusaurus, client-side rendered). The legacy `api.slack.com/*` URLs
301-redirect to the canonical `docs.slack.dev/reference/*` paths. Construct
URLs directly to skip the redirect:

| Resource | URL pattern | Example |
|---|---|---|
| Event reference | `https://docs.slack.dev/reference/events/<event_type>/` | `…/reference/events/reaction_added/` |
| Message.* events | **dotted name, no slash**: `…/reference/events/message.<sub>/` | `…/reference/events/message.channels/` |
| Web API method | `https://docs.slack.dev/reference/methods/<method>/` | `…/reference/methods/dnd.setSnooze` |
| Events API guide | `https://docs.slack.dev/apis/events-api/` | — |
| Rate limits | `https://docs.slack.dev/apis/web-api/rate-limits` | — |

**Pitfall — event-name URL format.** Message sub-events use a DOT in both
the event type and the URL path segment: `message.channels`, NOT
`message_channels` or `message/channels`. The underscore / slash variants
return a Slack 404 page ("You stand in an open field") that still renders
HTTP 200 — easy to mistake for a real (thin) page. The correct form mirrors
the sidebar link text exactly.

## Extraction technique

docs.slack.dev is CSR (Docusaurus) — **jina.ai silently fails** (returns the
nav sidebar only). Use `browser_navigate` + `browser_console` JS extraction:

```js
(() => {
  const m = document.querySelector('article') || document.querySelector('main');
  return m ? m.innerText.substring(0, 6000) : 'NOT FOUND';
})()
```

Wrap in an IIFE — see the browser_console identifier-collision pitfall in
the parent SKILL.md.

## The scope-vs-subscription-type distinction (load-bearing)

A common confusion in Slack integration design: **event-type names are NOT
OAuth scopes.** They are two separate things you must configure together:

1. **Event subscription** — the event type string (e.g. `message.channels`,
   `reaction_added`) you enter in App Config's Event Subscriptions or the
   app manifest's `event_subscriptions.request` list.
2. **OAuth scope** — the permission (e.g. `channels:history`, `reactions:read`)
   the app must be granted to actually RECEIVE that event's payloads.

Every event reference page lists its required scope(s) under a "Facts" panel
(`Required Scopes: <scope>`). The Events API guide is explicit
(https://docs.slack.dev/apis/events-api/, "Activating subscriptions"):

> "you'll need to request the specific OAuth scopes corresponding to the
> event types you're subscribing to ... Consult the event reference docs for
> all of the available event types and corresponding OAuth scopes."

## Verified scope mappings (2026-07)

Confirmed directly from each event's reference page:

| Event type | Required scope | URL |
|---|---|---|
| `reaction_added` | `reactions:read` | …/reference/events/reaction_added/ |
| `message.channels` | `channels:history` | …/reference/events/message.channels/ |
| `message.im` | `im:history` | …/reference/events/message.im/ |
| `message.groups` | `groups:history` | …/reference/events/message.groups/ |
| `message.mpim` | `mpim:history` | …/reference/events/message.mpim/ |

Other verified facts (from prior t_2e42c12f run):
- `dnd.setSnooze`: `num_minutes` is a **required** parameter.
- `app_uninstalled` and `tokens_revoked` events exist and fire on
  uninstall / token revocation respectively.
- No "link clicked" event exists. `link_shared` fires on link POST/unfurl,
  NOT on click — do not design click-detection on top of Slack events.
- `reaction_added` payload: the reacting user is in field `user` (NOT
  `user_id`); `item_user` (the original item's author) may be ABSENT for
  webhook-authored messages.
- **Bot-authored DM reactions are received by the sender.** A bot that
  posted a DM via `chat.postMessage` DOES get `reaction_added` for emoji
  reactions to it — via the perspectival distribution model (bot is a
  channel member). The "apps don't get events for own posts" filter applies
  to bot-authored `message.*` events, NOT to user-initiated reactions on
  the bot's message. Confirmed via reaction_added + message.im + Events API
  pages. See the dedicated section above.

## Bot-authored message reactions — does the sender receive the event?

**Yes.** This is the load-bearing question for any efficacy-measurement
mechanism that relies on emoji reactions to bot-sent DMs (e.g. 👍/👀/👎
on a digest message). Confirmed by cross-referencing the `reaction_added`
event page, the `message.im` event page, and the Events API guide
(t_93be245a run, 2026-07).

**Three facts combine to guarantee it:**

1. **Distribution rule** (`reaction_added` page): *"the reaction_added event
   is sent to all connected clients for users who can see the content that
   was reacted to."*
2. **Bot perspectivity** (Events API guide): *"Bot Events: subscribe to
   events on behalf of your application's bot user ... you'll only receive
   events perspectival to your bot user."*
3. **Membership by authorship**: a bot that posted a DM via `chat.postMessage`
   is a *member* of that DM channel and therefore "can see" the message.
   A reaction to it is visible to the bot → the bot receives the event.

**The "apps don't receive events for own posts" filter does NOT apply here.**
That filter suppresses `message.*` events for messages the bot itself
authored. But a user's emoji *reaction* is user-initiated activity ON the
bot's message, not a message the bot authored — so it is delivered normally.
This is a subtle but design-critical distinction.

**`item_user` confirms authorship.** The event payload's `item_user` field
holds the user/bot ID that created the reacted-to item. For Web-API-authored
messages (`chat.postMessage`), `item_user` == the bot's user ID. The docs
note it is omitted *only* for messages "not authored by users, like those
created by incoming webhooks." Filter on `item_user == <bot_id>` to confirm
the reaction is on your own message, and match `event.item.ts` against the
`ts` you captured from the `chat.postMessage` response to identify the
specific digest.

**Reliability / latency caveats for an efficacy pipeline:**

| Caveat | Detail |
|---|---|
| Delivery is "near real-time" | No hard latency SLA per event (Events API overview). |
| 3-second HTTP 200 requirement | Respond 200 immediately; process business logic async (queue). Timeouts trigger retries. |
| Duplicate delivery possible | De-duplicate by `event_id`; also possible across Enterprise orgs. |
| 30,000 events / workspace / app / 60 min | Above this, Slack sends `app_rate_limited` (throttled, not dropped). Not a concern for low-volume reaction pipelines. |
| No events after uninstall / token revoke | If a user uninstalls or an admin removes the app, no further events arrive for that user. |
| Socket Mode is a valid alternative | Same events + scope requirements, delivered over WebSocket — no public HTTP endpoint needed. |

## Bot Events vs Workspace Events (Events API nuance)

The Events API subscription manager (App Config) has two surfaces
(https://docs.slack.dev/apis/events-api/, "Choosing event subscriptions"):

- **Workspace Events** — require the corresponding OAuth scope, perspectival
  to the installing member.
- **Bot Events** — subscribed on behalf of the bot user; docs say
  "no additional scopes beyond bot required." BUT some event types are NOT
  available as bot events (consult the event page).

**Practical effect:** when you check a bot-event subscription in App Config,
the UI **auto-adds** that event's Required Scope to the bot's scope list.
So `reaction_added` subscribed as a bot event silently grants `reactions:read`
— the app works even if a design doc omits the scope, but the scope IS
granted and WILL appear on the installer consent screen. Design manifests
should list it explicitly to stay honest and avoid surprise on the consent
screen.

## Verification checklist (for Slack claim-checking)

1. Construct the canonical `docs.slack.dev/reference/{events,methods}/<name>/`
   URL. For message sub-events, use the dotted form.
2. `browser_navigate` to it; confirm you are NOT on the "open field" 404
   page.
3. Extract `article`/`main` innerText via `browser_console` (IIFE-wrapped).
4. Read the **Facts** panel for Required Scopes + Compatible APIs, and the
   payload example for exact field names.
5. Cross-check scope-vs-subscription claims against the Events API guide's
   "Permission model" and "Activating subscriptions" sections — do not infer
   from a single event page.
6. **For "does app/bot X receive event Y?" questions**, cross-reference
   three sources: (a) the event page's distribution/delivery rule (the
   "Usage info" paragraph — e.g. "sent to all clients who can see the
   content"), (b) the Events API guide's perspectivity model ("Bot Events
   ... events perspectival to your bot user"), and (c) the channel-type
   event page (`message.im` etc.) to confirm the channel class is in play.
   No single page states "the bot receives reactions to its own DMs" — the
   answer is derived by combining the three. This is how the bot-authored-DM
   reaction question above was resolved.
