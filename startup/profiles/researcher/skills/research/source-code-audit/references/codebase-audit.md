# Codebase Audit — Worked Example: URL-shortener redirect rate-limiting

Session-specific reference for the `source-code-audit` skill. Four open-source
shorteners audited to answer: **do they rate-limit the public `GET /:code` redirect
route (the 301/302)?**

The answer turned out to be "no" for all four — and the interesting findings are
(1) kutt.it has the rate-limit infrastructure but *deliberately* exempts the redirect,
(2) polr implements write-limiting with a *custom* DB-count helper rather than the
framework's built-in `throttle` middleware, and (3) yourls uses a per-IP cooldown gap
limiter (not a counter). Those distinctions (code exists vs. code is wired in;
framework keyword vs. custom implementation; counter vs. gap limiter) are the core
lessons.

## The question

For each shortener: does it rate-limit the redirect route? If so, what algorithm and
key? Or does it rely on web-server caching / CDN / no limit at all?

## Repos

- **shlink** — `https://github.com/shlinkio/shlink` (PHP, Mezzio/PSR-15)
- **kutt.it** — `https://github.com/thedevs-network/kutt` (Node, Express)
- **polr** — `https://github.com/cydrobolt/polr` (PHP, Lumen/Laravel micro-framework)
- **yourls** — `https://github.com/YOURLS/YOURLS` (vanilla PHP, no framework)

## shlink — verdict: NO rate-limiting anywhere

### Route wiring — `config/autoload/routes.config.php:98-108`
```php
[
    'name' => CoreAction\RedirectAction::class,
    'path' => sprintf('/{shortCode}%s', $shortUrlRouteSuffix),
    'middleware' => [
        IpAddress::class,
        IpGeolocationMiddleware::class,
        TrimTrailingSlashMiddleware::class,
        CoreAction\RedirectAction::class,
    ],
    'allowed_methods' => [RequestMethodInterface::METHOD_GET],
],
```
Redirect route middleware: IP extraction → GeoIP → trailing-slash trim → action.
**No rate-limit middleware.**

### Global pipeline — `config/autoload/middleware-pipeline.global.php`
Read in full. App-wide middleware: AccessLog, ContentLength, RequestId, ErrorHandler,
CrossDomain (CORS), ProblemDetails, routing, auth, not-found handlers. **None is a
rate limiter.**

### Dependencies — `composer.json`
```
grep -iE "rate|limit|throttle|cache" composer.json
```
Matches: `memory_limit` (PHP ini in coverage scripts) only. **No rate-limit package.**

### Handler — `module/Core/src/Action/RedirectAction.php` + `AbstractTrackingAction.php`
Resolves short URL, builds 302, tracks the visit via `trackIfApplicable()` (writes a
visit row). No counter, no cache lookup, no 429 path.

### Repo sweep
```
find . -iname "*ratelimit*" -o -iname "*throttle*"   # → zero results
grep -ri "rate.?limit|throttle" docs/                 # → zero relevant hits
```

**Conclusion: shlink ships zero application-layer rate-limiting.** Self-hosted model
defers protection to the operator's web server (RoadRunner / FrankenPHP / nginx).

## kutt.it — verdict: NO on redirect; YES on auth (deliberate split)

### Redirect route — `server/server.js:82`
```js
// finally, redirect the short link to the target
app.get("/:id", asyncHandler(links.redirect));
```
Bare route. Just the handler. No `helpers.rateLimit(...)`.

### Global middleware — `server/server.js:39-60`
helmet, cookieParser, express.json, express.urlencoded, static, passport.initialize,
locals.isHTML, locals.config. **No global rate limiter.**

### The rate-limit infra DOES exist — `server/handlers/helpers.handler.js:88-124`
```js
function rateLimit(params) {
  if (!env.ENABLE_RATE_LIMIT) {
    return function(req, res, next) { return next(); }   // opt-in, default OFF
  }
  let store = undefined;
  if (env.REDIS_ENABLED) {
    store = new RateLimitRedisStore({                    // Redis when available
      sendCommand: (...args) => redis.client.call(...args),
    })
  }
  return expressRateLimit({
    windowMs: params.window * 1000,
    validate: { trustProxy: false },
    skipSuccessfulRequests: !!params.skipSuccess,
    skipFailedRequests: !!params.skipFailed,
    ...(store && { store }),
    limit: function (req, res) { ... },
    keyGenerator: function(req, res) {
      return "rl:" + req.method + req.baseUrl + req.path + ":" + req.ip;  // key
    },
    ...
  });
}
```
- **Algorithm:** fixed-window (express-rate-limit default).
- **Key:** `rl:<METHOD><baseUrl><path>:<IP>`.
- **Store:** Redis (`rate-limit-redis`) when `REDIS_ENABLED`, else in-memory.
- **Gated behind `ENABLE_RATE_LIMIT` env var (default `false`).**

### Where it's actually called
Only `server/routes/auth.routes.js` calls `helpers.rateLimit` — 8 times, all on
auth endpoints (login, signup, password reset, etc.), e.g.:
```js
helpers.rateLimit({ window: 60, limit: 5 }),
```
`server/routes/link.routes.js` (the `/api/v2/links` CRUD) has **zero** `rateLimit` calls.
And the public `GET /:id` redirect in `server.js` has none.

### Docs — `README.md:130`
```
| `ENABLE_RATE_LIMIT` | Enable rate limiting for some API routes. If Redis is enabled
                        uses Redis, otherwise, uses memory. | `false` | `true` |
```
Explicitly scoped to *"some API routes"* — not redirects. Default off.

**Conclusion: kutt.it made a deliberate choice.** Rate-limit the mutation/auth surface
(where abuse = account takeover, spam). Leave the public read-only redirect unthrottled
(where throttling would break viral traffic, and where protection is assumed to come
from the CDN/reverse proxy). The infra is right there and pointedly not applied to
the redirect.

## polr — verdict: NO on redirect; YES on API writes (custom, not throttle middleware)

### Redirect route — `app/Http/routes.php:32`
```php
$app->get('/{short_url}', ['uses' => 'LinkController@performRedirect']);
$app->get('/{short_url}/{secret_key}', ['uses' => 'LinkController@performRedirect']);
```
Bare route definition. **No `middleware` key.** The only route-level middleware the
app registers is `'api'` (`bootstrap/app.php:67-69`), and it is attached only to the
`/api/v2` route group (`routes.php:65`), not the redirect.

### Global middleware — `bootstrap/app.php:59-65`
```php
$app->middleware([
    Illuminate\Cookie\Middleware\EncryptCookies::class,
    Illuminate\Session\Middleware\StartSession::class,
    Illuminate\View\Middleware\ShareErrorsFromSession::class,
    App\Http\Middleware\VerifyCsrfToken::class,
]);
```
Cookies, session, view errors, CSRF. **No throttle, no rate limiter.**

### Redirect handler — `app/Http/Controllers/LinkController.php:50-103`
```php
public function performRedirect(Request $request, $short_url, $secret_key=false) {
    $link = Link::where('short_url', $short_url)->first();
    if ($link == null) { return abort(404); }
    // ... disabled / secret-key checks ...
    $clicks = intval($link->clicks) + 1;   // increment click count
    $link->clicks = $clicks;
    $link->save();
    if (env('SETTING_ADV_ANALYTICS')) { ClickHelper::recordClick($link, $request); }
    return redirect()->to($long_url, 301);  // 301, not 302
}
```
Lookup → increment → save → 301. Zero rate-limit code.

### Write limiting — `app/Http/Middleware/ApiMiddleware.php` + `app/Helpers/ApiHelper.php`
The `api` middleware is the ONLY place limiting happens:
```php
// ApiMiddleware.php:43-47
$api_limit_reached = ApiHelper::checkUserApiQuota($username);
if ($api_limit_reached) {
    throw new ApiException('QUOTA_EXCEEDED', 'Quota exceeded.', 429, $response_type);
}
```
The quota check is a **custom DB COUNT query, not Laravel's `throttle` middleware**:
```php
// ApiHelper.php:13-35
$last_minute_unix = time() - 60;
$last_minute = new \DateTime();
$last_minute->setTimestamp($last_minute_unix);
$api_quota = $user->api_quota ?? (env('SETTING_ANON_API_QUOTA') ?: 5);
if ($api_quota < 0) { return false; }  // -1 = unlimited
$links_last_minute = Link::where('is_api', 1)
    ->where('creator', $username)
    ->where('created_at', '>=', $last_minute)
    ->count();
return $links_last_minute >= $api_quota;
```
- **Algorithm:** fixed-window (60s) via `COUNT(*)` query. Not a token bucket, not
  in-memory, not Redis.
- **Keyed on USERNAME / API KEY** (per-developer). Anonymous API synthesizes username
  as `'ANONIP-'.$request->ip()` — so anon limiting is effectively per-IP.
- **Default:** anon 5/min (`SETTING_ANON_API_QUOTA`); authenticated users use a
  per-user `api_quota` DB column.
- **Scope:** applies only to `/api/v2/action/shorten`, `/shorten_bulk`, `/lookup`,
  `/data/link` (the `middleware='api'` group at `routes.php:65-78`). The web
  `POST /shorten` (`routes.php:40`, `LinkController@performShorten`) has NO middleware
  and NO rate-limit.

**⚠ KEY PITFALL:** `grep -ri "throttle"` finds nothing in polr. A naive audit relying
on the framework keyword would report "no rate-limiting" and be wrong — polr limits
writes, just not via the framework idiom. **Always read the middleware body, not just
the route/middleware names.** This is the Lumen/Laravel equivalent of the kutt.it
trap: the framework has a well-known mechanism (`throttle` / `helpers.rateLimit`), and
the project implements its own instead.

## yourls — verdict: NO on redirect; YES on writes (per-IP cooldown gap limiter)

### Redirect entry point — `yourls-go.php:1-28`
```php
define( 'YOURLS_GO', true );
require_once( dirname( __FILE__ ) . '/includes/load-yourls.php' );
if( !isset( $keyword ) ) { yourls_redirect( YOURLS_SITE, 301 ); }
$keyword = yourls_sanitize_keyword($keyword);
if( $url = yourls_get_keyword_longurl( $keyword ) ) {
    yourls_redirect_shorturl($url, $keyword);   // ← the redirect
    return;
}
yourls_redirect( YOURLS_SITE, 302 );  // not found → redirect home, no 404
```
No framework, no middleware stack — a flat PHP entry-point file. **No call to
`yourls_check_IP_flood` anywhere in this path.**

### Redirect function — `includes/functions.php:355-368`
```php
function yourls_redirect_shorturl($url, $keyword) {
    yourls_do_action( 'redirect_shorturl', $url, $keyword );
    yourls_update_clicks( $keyword );      // increment click count
    yourls_log_redirect( $keyword );        // stats log
    yourls_robots_tag_header();             // X-Robots-Tag: noindex
    yourls_redirect( $url, 301 );
}
```
Action hook → increment → log → robots header → 301. Zero rate-limit code.

### Write limiting — called from exactly ONE site
`yourls_check_IP_flood($ip)` is invoked inside the short-link-creation function only:
```php
// includes/functions-shorturls.php:62-64, inside yourls_add_new_link()
$ip = yourls_get_IP();
yourls_check_IP_flood( $ip );
```
The function itself — `includes/functions.php:741-784`:
```php
function yourls_check_IP_flood(string $ip = ''): mixed {
    if ( yourls_is_private() && yourls_is_valid_user() === true ) return true; // skip logged-in
    if ( in_array( $ip, yourls_get_flood_ip_whitelist() ) ) return true;      // skip whitelist
    $ip = $ip ? yourls_sanitize_ip($ip) : yourls_get_IP();
    $table = YOURLS_DB_TABLE_URL;
    $lasttime = yourls_get_db('read-check_ip_flood')->fetchValue(
        "SELECT `timestamp` FROM $table WHERE `ip` = :ip ORDER BY `timestamp` DESC LIMIT 1",
        ['ip' => $ip]
    );
    if ($lasttime) {
        $now = date('U'); $then = date('U', strtotime($lasttime));
        if (($now - $then) <= $flood_delay) {
            yourls_die('Too many URLs added too fast. Slow down please.',
                       'Too Many Requests', 429);
        }
    }
    return true;
}
```
- **Algorithm:** **cooldown / minimum-interval gap limiter** — not a counter. One
  DB query for the most recent write by this IP; if that was within `flood_delay`
  seconds, 429. Effectively "1 write per window."
- **Keyed on IP ADDRESS** (`yourls_get_IP()`, the clicker/creator's IP) — NOT
  developer identity. This is the key contrast with polr.
- **Default:** 15 seconds (`YOURLS_FLOOD_DELAY_SECONDS` const; `<=0` disables).
- **Exemptions:** logged-in users on private installs; IP whitelist; the whole
  function is plugin-shortcircuitable via the `shunt_check_IP_flood` filter.
- **Implemented as a DB last-timestamp query**, not an in-memory counter, not Redis.

**The vanilla-PHP idiom:** no router, no middleware stack — to audit "is X wired to
route Y," you must find the entry-point file (`yourls-go.php`, `yourls-loader.php`)
and follow the function calls manually. The loader dispatches by URL pattern; there is
no central route table to read.

## False-positive traps hit during this audit

1. `grep -i "limit" composer.json` matched `memory_limit` and `--memory-limit` in
   phpunit coverage scripts. Read the lines before concluding.
2. `grep -ri "rate.?limit" docs/` returned one changelog hit that, on inspection,
   matched nothing (the `.` in the regex picked up line noise). Verify content.
3. `static/libs/htmx.min.js` and `static/libs/chart.min.js` matched `rateLimit` /
   `limit` keyword searches. Vendored static files are never your answer — exclude
   `static/`, `vendor/`, `node_modules/`, `public/` mentally.
4. **polr: `grep -ri "throttle"` returns zero hits, yet polr DOES rate-limit writes.**
   The framework's `throttle` middleware is not used; a custom `checkUserApiQuota()`
   helper does the work. **The framework keyword is not a reliable signal of whether
   limiting exists.** Always read the middleware body attached to a route group.
5. **yourls: `grep -ri "rate.?limit"` returns zero hits, yet yourls DOES rate-limit
   writes.** It calls the feature "flood" (`yourls_check_IP_flood`,
   `YOURLS_FLOOD_DELAY_SECONDS`), not "rate limit." Projects use domain vocabulary
   (`flood`, `quota`, `spam`) that won't match the generic keyword. Search for the
   *effect* (429, "too many", "slow down") and the *HTTP status*, not just the pattern name.

## Cross-project pattern

All four audited shorteners (shlink, kutt.it, polr, yourls; plus dub.co from task
context = 5 total) converge: **the public redirect route is NOT application-level
rate-limited.** Protection is deferred to the infrastructure layer (CDN / reverse
proxy / web server). kutt.it is the strongest evidence this is intentional — it has
rate-limit code for other routes and deliberately excludes the redirect.

### What they DO limit, and how they key it

| project  | redirect limited? | write limit? | algorithm              | keyed on            |
|----------|:-----------------:|:------------:|------------------------|---------------------|
| shlink   | no                | no           | —                      | —                   |
| kutt.it  | no                | auth only    | fixed-window (Redis/mem) | `METHOD+path+IP`  |
| polr     | no                | API only     | fixed-window DB COUNT  | **developer/API key** (anon→IP) |
| yourls   | no                | yes          | **per-IP cooldown gap** | **IP address**      |
| dub.co   | no                | per-user (POST) | @upstash/ratelimit  | user                |

The keying divergence is the design-relevant insight: polr keys writes on the
developer/caller identity (the risky choice for a public-facing click path — limits
the wrong party); yourls keys on the clicker IP (the safer default). Any ADR proposing
application-level redirect rate-limiting is *novel* relative to this prior art, and
should think carefully about keying on clicker IP rather than developer identity.
