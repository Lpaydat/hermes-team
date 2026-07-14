---
name: source-code-audit
description: "Answer 'does project X implement pattern Y?' by reading the actual source code of an open-source project — clone, locate the route/handler/feature wiring, trace the full call chain, and report exact file paths and code. Distinct from doc-search or wiki synthesis: the deliverable is a definitive yes/no (or partial) backed by file:line evidence, including honest negative findings. Use for ADR prior-art analysis, security reviews, dependency audits, and any 'how does project X actually do Z in code' question."
version: 1.1.0
metadata:
  hermes:
    tags: [audit, source-code, investigation, prior-art, implementation]
    category: research
    related_skills: [deep-research, research]
---

# Source-Code Audit

Answer "does project X implement pattern Y?" from the code itself — not from blog
posts, not from docs, and never from inference. The deliverable is a **definitive
yes/no (or partial) backed by exact file paths and quoted code.**

Use this when:
- A question hinges on a specific implementation detail (rate-limiting, auth flow,
  caching, validation, error handling, session storage) that docs omit or gloss.
- You need prior art for an architecture decision (ADR) and must cite real code.
- A security/correctness claim must be verified against what the code actually does.

Do NOT use this for general "how does framework X work" questions (use docs) or
knowledge-synthesis across many sources (use deep-research).

## Core principle: prove the answer from the route backwards

The single most important rule: **finding the pattern's code somewhere in the repo is
not enough. It must be wired to the specific entry point the question asks about.**
A `RateLimit` helper that exists but is never called on the target route is a
*deliberate non-implementation*, not a bug — and that distinction is often the whole
answer.

Always trace: route definition → middleware chain → handler → service layer →
dependencies. An answer is complete only when you've confirmed whether the pattern
appears at the right place in that chain.

## Method (7 steps)

### 1. Clone shallow
```
git clone --depth 1 https://github.com/<org>/<repo>.git
```
You want HEAD, not history. A local tree lets you grep comprehensively — web search
and the GitHub UI cannot match this thoroughness.

### 2. Locate the entry point
For web questions this is the **route registration** file. Search broadly:
```
grep -r "Action::class\|router\.\(get\|post\|use\)\|@Route\|@Get\|\.get(\|\.post("
grep -r "<PatternName>\|<feature>Route"
```
Common homes: PHP/Mezzio `config/autoload/routes.config.php`; Express `server/server.js`
or `server/routes/*.js`; Rails `config/routes.rb`; Django `urls.py`; Spring `@RestController` classes;
Lumen/Laravel `app/Http/routes.php` (route groups carry a `middleware` key — check the group
declaration, not just the individual route line).

**Framework-less projects (vanilla PHP, plain scripts):** there is no route table. Find the
entry-point file the web server maps the URL to (e.g. `yourls-go.php`, `index.php`), then follow
function calls manually. A grep for the handler function name is your route trace.

### 3. Trace the middleware stack for THAT route
Read the route definition. Note every middleware in its chain. The pattern must appear
**in that chain or in a global pipeline wrapping it.** Finding it in an unrelated file
proves nothing about this route.

**Read the middleware body, not just its name.** A route group declaring
`'middleware' => 'api'` tells you *something* runs — open the class and read `handle()`.
The limiter may be a custom helper call (`ApiHelper::checkUserApiQuota(...)`) rather
than the framework's stock throttle. The route/middleware name alone is not the answer.

### 4. Read the global middleware pipeline in full
- Mezzio/PSR-15: `config/autoload/middleware-pipeline.global.php`
- Express: `app.use(...)` calls in `server.js` / `app.js`
- Lumen/Laravel: `bootstrap/app.php` `$app->middleware([...])` (global) and
  `$app->routeMiddleware([...])` (named, attached per-route-group)
- Rails: `config/application.rb` + initializers
- Django: `settings.MIDDLEWARE`

If neither the route chain nor the global pipeline contains the pattern → no
application-layer implementation.

### 5. Verify dependencies (build the negative case)
```
grep -iE "rate|limit|throttle" composer.json package.json Cargo.toml go.mod
```
Then **inspect the matched lines.** A negative-finding is strongest when the
pattern's library isn't even a dependency.

**⚠ The framework keyword is not a reliable signal.** `throttle` (Laravel/Lumen),
`@Throttle` (Symfony/Play), or `express-rate-limit` may exist in the ecosystem but the
project can implement its own limiter under a different name (`checkUserApiQuota`,
`check_IP_flood`, `quota`). Grepping for the framework keyword alone produces false
negatives. Confirm by reading the middleware body actually attached to the route (step 3).

**⚠ Domain vocabulary ≠ your keyword.** Projects name the feature in their own words —
`flood`, `quota`, `spam` — not `rate limit`. Search for the *effect* (HTTP `429`,
"too many", "slow down", a `die()`/`abort` with a 4xx status) when the pattern name
returns nothing.

### 6. Repo-wide file-name sweep
```
find . -iname "*<pattern>*" -o -iname "*<synonym>*"
```
A dedicated module/class file for the pattern is a strong positive; zero results
supports a negative.

### 7. Check docs/changelog only as corroboration
```
grep -ri "<pattern>" docs/ CHANGELOG.md README.md
```
Docs may state the intended approach ("rate limiting handled by CDN"). If code says
"no" and docs are silent, report "no application-layer implementation; no documented
approach." Never infer a positive from doc silence.

## Reporting

Per audited project:
Per audited project:
- **Verdict** (Yes / No / Partial) in the first sentence.
- **Negatives stated explicitly** — "no package, no middleware, no docs" is a complete
  and honest answer.
- **Cross-project patterns** — when auditing multiple projects for the same question,
  summarize the convergence/divergence. That's often the real insight. A comparison
  table (redirect limited? write limited? algorithm? keyed on?) surfaces design
  trade-offs that prose buries.

## Pitfalls

- **"Code exists" ≠ "code is wired in."** The #1 error. Always trace from the route
  backwards. (Worked examples: kutt.it has a Redis-backed rate-limit helper — but only
  auth routes call it; the redirect route is deliberately exempt. polr has a quota
  helper — but it's only on the `/api/v2` group, not the redirect or web shorten.)
- **Framework keyword false-negatives.** A repo with zero `throttle`/`RateLimit` hits
  can still rate-limit — via a custom helper. polr's `checkUserApiQuota()` and yourls's
  `yourls_check_IP_flood()` both hide from a keyword grep. Read middleware bodies.
- **Domain-vocabulary false-negatives.** "flood", "quota", "spam" won't match
  `rate.?limit`. Search for the HTTP status (429) and the effect ("too many", "slow down").
- **Keyword false-positives.** `limit` matches `memory_limit` (PHP ini), coverage
  `--memory-limit`, CSS/chart libs. Use `search_files` with `output_mode: content` and
  read the lines, never trust `files_only`.
- **Vendored/static noise.** `htmx.min.js`, `chart.min.js`, `vendor/`, `node_modules/`
  match almost anything. Exclude them mentally.
- **Proving absence is the hard part.** One empty grep is weak. Cross-check across
  route wiring + global pipeline + dependency manifest + file-name sweep. Multiple
  independent empty vectors → confident negative.
- **Fabrication is the worst outcome.** If you can't find evidence, say so plainly.
  "No rate-limiting code and no documented approach" is a better answer than an
  invented mechanism. The user can tell the difference; trust is hard to rebuild.

## References

- `references/codebase-audit.md` — full worked example: rate-limiting the public
  `GET /:code` redirect across four shorteners (shlink, kutt.it, polr, yourls),
  including the false-positive traps and a cross-project comparison table. The polr
  and yourls sections demonstrate the framework-keyword and domain-vocabulary traps.
