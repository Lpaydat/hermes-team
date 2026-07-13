---
name: source-code-verification
description: "Verify technical claims ('does library X implement Y?', 'what algorithm does Z use?', 'confirm/deny behavior from source') by cloning the repo and reading the actual code — not secondary writeups. Use when the user asks you to check how something is really implemented, audit a claim against source, or cite exact file paths and line numbers. Distinct from general research — the source of truth here is the codebase itself."
---

# Source-code verification

Verify claims against the actual codebase. The code is the authority — not a blog post, not docs that may lag the code, not your prior belief. Every claim you report must trace to a file, a line, and a snippet, pinned to a commit.

## When to load

- "Does library X rate-limit / cache / retry / log Y?"
- "Verify [claim] from its open-source codebase."
- "What algorithm / data structure / key does X use for Z?"
- "Confirm or deny: [framework] does [behavior]."
- Any request that ends with "check the source" or "cite file paths and line numbers."

If the question is about *what a library does* (behavior) rather than *how the docs describe it*, you are here.

## The method (in order)

### 1. Clone at minimum depth
```
git clone --depth 1 https://github.com/<org>/<repo>.git
```
`--depth 1` is enough — you're reading a snapshot, not history. Record the commit hash immediately for provenance:
```
git -C <repo> log -1 --format="%H %ci %s"
```
Every finding you write should name this commit. Claims about "current" code are meaningless without the pin; the repo will move.

**Single-file fetch when cloning is overkill.** If you only need 1–3 files from a large repo (e.g. one SQLAlchemy dialect + the pool impl), fetch them directly from a tagged release instead of cloning the whole thing:
```
curl -sL "https://raw.githubusercontent.com/<org>/<repo>/<tag>/<path>" -o <file>
```
Use a tag (e.g. `rel_2_0_51`), not `main` — tags are stable pins just like a commit hash. This is dramatically faster than cloning a large monorepo when a grep already told you exactly which file matters. Clone when you need to search; raw-fetch when you already know the path.

### 2. Targeted parallel greps before reading anything
Don't guess where the logic lives. Run several `search_files` (ripgrep) passes in ONE batch:
- The library/dependency name (e.g. `@upstash/ratelimit`, `rate-limiter-flexible`) — finds the factory/registration.
- The API surface (e.g. `slidingWindow|tokenBucket|fixedWindow`, `Ratelimit|ratelimit|rateLimiter`).
- The route/handler identifier (e.g. the endpoint path, an exported function name).

Batch independent greps in the same turn. The hits tell you which 2–4 files to actually read.

### 3. Read the handler(s) in full — not just the matching line
A grep hit is a lead, not a verdict. Open the whole handler/function, because:
- The rate-limit call may be inside an `if (!session)` guard (conditional enforcement).
- The "redirect" may live in middleware, not a `route.ts` (Next.js routes redirects through `middleware.ts`, not the app router).
- Cache headers may be defined once and applied selectively — check *which* responses actually carry them.

### 3b. Follow compat / import indirection to the real implementation
Many libraries route the behavior you care about through a compatibility shim that resolves to **different code per runtime version**. A grep hit like `from . import compat; compat.wait_for(...)` is a lead, not an answer — `compat.wait_for` may be `asyncio.wait_for` on Python 3.12+ but a custom backport (`_asyncio_compat.py`) on older Pythons, and the two can raise **different exception classes**. Trace the import to its resolution (read `compat.py`, then the backport module it delegates to) before you cite the exception or the behavior. This is where "what does it actually raise" answers hide — the function name in the call site is often a facade over version-dependent implementations.

### 4. Prove ABSENCE explicitly — never assert it
This is the highest-stakes step. "It doesn't rate-limit X" must be backed by an empty grep, shown as output, not asserted from intuition:
```
grep -n "ratelimit\|ratelimitOrThrow\|Ratelimit" <file>  →  (none found)
```
If you can't run the proving grep, you don't get to claim absence. Say "I could not confirm" instead. **Do not fabricate.** If you can't find it, say so — verbatim.

### 5. Cite like a lawyer
Each finding carries: **exact relative path**, **line number(s)**, **code snippet**, and the **commit**. Example shape:
> `apps/web/app/api/links/route.ts:65-76` — `ratelimit(10, "1 d").limit(ip)`, guarded by `if (!session)`. Commit `803e789b`.

**Tag the epistemic status of every claim.** When the deliverable feeds a decision (ADR, design council, architecture review), the reader needs to know what's ironclad vs. inferred. Tag each finding:
- `[VERIFIED-FROM-SOURCE]` — you read the actual code; path/line/commit cited.
- `[ASSERTED-FROM-DOCS]` — you're relying on documentation (vendor docs, README), which may lag the code.
- `[EXTRAPOLATED]` — you're reasoning from the evidence but didn't measure or read it directly.

This is a first-class quality standard, not decorative. A reviewer trusting an `[EXTRAPOLATED]` claim as if it were `[VERIFIED-FROM-SOURCE]` is a real failure mode. When in doubt, downgrade the tag — "I couldn't verify" is stronger than an overstated claim.

### 6. Distinguish what the code DOES from what people SAY it does
A common ask is "does X rely on CDN caching?" The code-level answer requires inspecting response headers on the *specific response branch*, not a header defined at the top of the file. A `Cache-Control` constant defined once and applied only to error pages is NOT applied to the success path — verify the spread/usage sites, not just the definition.

## Pitfalls

- **Route location surprises.** Next.js handles redirects in `middleware.ts` → `LinkMiddleware`, not `app/[domain]/route.ts`. Express puts them in `routes/*.js`. PHP/Mezzio in `routes.config.php`. Find the framework's dispatch point first, or you'll search the wrong tree.
- **Conditional enforcement.** Rate-limit calls are frequently wrapped in auth checks (`if (!session)`, `if (!user)`). The limit exists but doesn't apply to everyone — report the guard, not just the call.
- **"Defined" ≠ "applied."** A cache-header object or middleware constant can be defined and then used on only some branches. Count the usage sites (`grep -n CONSTANT_NAME`) and check each one.
- **Trusting the lockfile as evidence of behavior.** A package in `package.json`/`pnpm-lock.yaml` proves a dependency exists, not that it's wired to a route. Always follow to the import + call site.
- **Stale commit.** If you didn't record the hash, your findings have an expiry date you can't state. Pin first.
- **Asserting absence without a grep.** The single most common fabrication vector. Absence = empty grep output, shown.

## Verification (self-check before reporting)

- [ ] Did I name the commit hash?
- [ ] Does every positive claim cite path + line + snippet?
- [ ] Does every negative claim ("does not do X") show the proving empty grep?
- [ ] Did I read the full handler, not just the matched line, to catch guards and conditional branches?
- [ ] Did I distinguish defined-vs-applied for any cache/header/middleware claim?

## Output shape

A findings file (Markdown) with: a verdict table (claim → CONFIRMED / REFUTED / PARTIAL, each linking to evidence), then per-claim detail with paths/lines/snippets, then a "files inspected" list. If the task is part of a kanban council, also post the verdicts to the shared blackboard as a comment.

## Reference

- `references/verification-recipes.md` — worked example (dub.co rate-limit audit), the grep batch pattern, and framework-specific dispatch-location notes (Next.js / Express / PHP-Mezzio). Read this when doing your first verification on a new framework.
