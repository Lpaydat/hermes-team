# Backend Ecosystem Tool Comparison (Rust / Python / Go)

Domain-specific methodology for "research the standard/must-have tools for [language] backend development" or "compare N libraries across one or more backend language ecosystems." Distinct from `js-library-research.md` (frontend component libraries, headless/styled layers) and `js-library-benchmarking` (hands-on performance measurement) — this is about **scoring and ranking** the canonical package ecosystem per language category, using registry data as quantitative evidence.

## 1. The output shape: scored table per category

The deliverable is one table per category (e.g., "HTTP client", "error handling", "database"), with columns: tool name, what it does, score (1–10), is-it-canonical (yes/no), alternatives, pros, cons. Followed by a "→ tech-preferences.json" recommendation line per category.

End the report with a summary table of recommended tech-preferences.json entries, one per language.

## 2. Registry data as the quantitative backbone

Don't score from priors alone. Pull **download counts and latest versions** from each registry to back the canonical/alternative classification. For Rust/Python/Go comparisons, batch three registries in parallel:

```sh
# Rust (crates.io) — needs User-Agent header, no rate limit
for crate in serde tokio reqwest sqlx; do
  curl -s -H "User-Agent: research-agent/1.0" "https://crates.io/api/v1/crates/$crate" \
    | python3 -c "import sys,json; c=json.load(sys.stdin)['crate']; print(f'$crate: recent={c[\"recent_downloads\"]}, max_ver={c[\"max_version\"]}')"
done

# Python (pypistats) — rate-limited (429), add sleep(1) between calls (see tactics §16)
# pypi.org/pypi/<name>/json for versions is NOT rate-limited — batch freely

# Go (module proxy) — version + timestamp, no rate limit, no download counts
for pkg in "github.com/go-chi/chi/v5" "gorm.io/gorm"; do
  curl -s "https://proxy.golang.org/$pkg/@latest" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['Version'], d['Time'][:10])"
done
```

Download volume is the primary "canonical" signal: a crate with 200M+ recent downloads (serde, tokio, clap, anyhow, thiserror) is canonical by definition. A crate with 3M vs a competitor's 30M is clearly the alternative. See `web-research-tactics.md` §16 for per-registry command details, pypistats 429 handling, and the Go module proxy.

## 3. The canonical vs alternative classification

**Canonical** = the default the ecosystem converges on; the tool other tools assume you're using. Mark canonical when:
- Download count is 5–10x+ the nearest alternative (e.g., tokio 203M vs async-std 9M)
- Other ecosystem-defining tools hard-depend on it (axum/hyper/reqwest/sqlx all require tokio)
- It's the documented standard in the framework's own docs (pydantic for FastAPI)

**Alternative** = viable but non-default; list when there's a reason to diverge:
- Compile-time/footprint optimization (ureq instead of reqwest for CLIs; lexopt instead of clap)
- Different abstraction level (sqlc vs GORM — SQL-first vs ORM)
- Niche/rising (granian vs uvicorn; SQLModel vs SQLAlchemy)

## 4. Interdependency tracking — the decisive backend signal

Unlike frontend libraries, backend tools form **hard dependency chains**. Track and call out these interdependencies — they're often the decisive factor:

| Pattern | Example | Impact |
|---|---|---|
| Runtime lock-in | axum, hyper, reqwest, sqlx all hard-depend on **tokio** | async-std/smol are non-viable for axum projects |
| Framework core coupling | FastAPI built on **pydantic v2** + **httpx** (TestClient) | Diverging (attrs, aiohttp) breaks framework interop |
| Sync/async mismatch | **diesel** (sync ORM) in axum handlers requires `spawn_blocking` | Makes diesel awkward in async stacks; sqlx is natural |
| Stacked layers | **pydantic-settings** builds on pydantic; **SQLModel** builds on SQLAlchemy | Thin wrappers inherit parent's complexity |
| Ecosystem shift | Go 1.22 enhanced `ServeMux` (path params, method routing) | Obsoleted the core reason for chi/gin/echo for most services |

When interdependencies exist, note them as "compatibility notes" in the findings — they're often more decisive than the score itself.

## 5. Scoring rubric (1–10)

| Score | Meaning | Example |
|---|---|---|
| 9–10 | Canonical, ecosystem-defining, massive adoption | serde, tokio, clap, pydantic, httpx, net/http (Go 1.22+) |
| 7–8 | Strong, widely used, clear use-case | ureq, rusqlite, sqlc, uvicorn, alembic, chi |
| 5–6 | Viable but niche/declining/rising-unproven | async-std, eyre, SQLModel, GORM, Tortoise ORM |
| 1–4 | Avoid for new projects / effectively dead | slog, async-std (4) |

Score relative to the category and the stated use-case. A "7" for a CLI tool (ureq) might be a "3" for an async backend — context matters.

## 6. Pitfalls

1. **Download counts are a trailing signal, not a quality signal.** A tool with fewer downloads may be better for the specific use-case (ureq is excellent for CLIs despite 1/3 of reqwest's downloads). Always pair download volume with the pros/cons analysis.

2. **"Latest version" recency ≠ maintenance quality.** A version bump that only updates a dependency doesn't signal active development. Cross-reference with the GitHub repo-metadata API (pushed_at, CHANGELOG substance) for maintenance-liveness verification.

3. **Go's lack of download stats.** Go has no equivalent of crates.io/npm/pypistats download counts — the module proxy only gives version + timestamp. Use GitHub stars + pushed_at (repo-metadata API) as the adoption/liveness proxy for Go libraries instead. Don't leave the Go column without quantitative backing — use stars + release recency.

4. **Ecosystem shifts change canonical status overnight.** Go 1.22's enhanced ServeMux moved `net/http` from "you need chi" to "canonical default" in one release. When a major language/framework version drops, re-check whether it changes the calculus for the category. Flag version-gated recommendations ("Go 1.22+" or "SQLAlchemy 2.0 async" not just "SQLAlchemy").

5. **Score the version, not the name.** "SQLAlchemy" scored 9 means SQLAlchemy **2.0** (async, typed Mapped[]). SQLAlchemy 1.4 is a different, lower score. Pin the version in the recommendation.
