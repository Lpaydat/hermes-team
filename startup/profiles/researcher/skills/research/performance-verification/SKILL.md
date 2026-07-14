---
name: performance-verification
description: Verify a performance or behavioral claim by RUNNING a live measurement yourself — EXPLAIN ANALYZE, a timing sweep, a CPU microbenchmark, a reproduction, or a simulation — not by citing docs or blog posts. Use when the ask is "is the proposed design's performance assumption true", "at what scale does X degrade", "prove it's sub-millisecond / within budget", "what hit rate / memory footprint / queue depth will size N give", or any ADR/architecture question where the decisive evidence is empirical. Covers three measurement classes — DB plan-driven queries (EXPLAIN, plan shape, forced-path contrast), CPU-bound library/runtime microbenchmarks (percentile timing, warmup, variant contrast), and analytical/simulation modeling (Zipf/access-distribution hit-rate, memory sizing, queue theory) for quantitative design answers when you can't run the real system. Sibling to docs-verification, source-code-verification, and library-state-verification — load THIS one when the source of truth is a measurement you generate.
---

## When to load this (not its siblings)

Pick the skill by **where the decisive evidence lives**:

| Question shape | Evidence lives in... | Skill |
|----------------|----------------------|-------|
| "Do the docs guarantee X?" | documentation/spec | `docs-verification` |
| "Does the code actually implement Y?" | source code | `source-code-verification` |
| "Is this library maintained / what version?" | package registry | `library-state-verification` |
| **"Is X fast enough / does it actually behave this way at N?"** | **a measurement you run** | **`performance-verification`** (this one) |

The trap to avoid: answering a performance question with a doc quote. Docs describe what's *supposed* to happen; a measurement shows what *actually* happens on a given version, config, and data shape. "The index supports ordered scans" (doc claim) is weaker than "the plan shows `Index Only Scan → WindowAgg` with no intervening Sort, 0 heap fetches, 0.5ms at 365 rows" (measurement). When a design rests on a performance/behavior assumption, **demonstrate it; don't just cite it.**

## The methodology (4 steps)

### 1. Reproduce the target shape, not a toy
Build a schema and data that mirror the real query path the architect is worried about — the actual index, the actual cardinality, realistic gaps/distribution. A `SELECT 1` timing proves nothing. For the habit-tracker streak question this meant the real `UNIQUE(habit_id, date)` PK index and generated data with a known answer (365 consecutive days → longest streak 365).

### 2. Read the PLAN SHAPE, not just the milliseconds
Execution time is the headline, but the **plan tree** is the proof of *why*. For databases:
- **PostgreSQL**: `EXPLAIN (ANALYZE, BUFFERS, TIMING)`. The nodes tell you the mechanism: `Index Only Scan` vs `Seq Scan`, presence/absence of a `Sort` node, `Heap Fetches: 0` (covering index), `shared hit` counts.
- The decisive question for index-driven queries is almost always *"is there a Sort node between the scan and the consumer?"* — that's the difference between an index-ordered plan and a fallback. See `references/empirical-benchmarking.md` for how to read PostgreSQL plans.

### 3. SWEEP the scale, don't just test one point
A single timing at one row count doesn't answer "at what scale does it degrade?" Generate data across a range (e.g. 255 → 365 → 1,825 → 3,650 → 7,300 → 18,250 rows) and tabulate execution time vs row count. This reveals:
- Whether scaling is linear / sublinear / superlinear.
- The threshold where you cross a budget (e.g. 1ms, 200ms p99).
- Whether you're measuring fixed overhead or per-row cost.
A reusable scaffold for the sweep is in `templates/explain-analyze-scaling-sweep.sql`.

### 4. Run a FORCED-PATH CONTRAST to prove the mechanism
To prove "the index is what makes it fast", disable the index path (`SET enable_indexscan=off; SET enable_indexonlyscan=off` in PostgreSQL) and re-run the same query. If the plan gains a `Sort` node (or a `Seq Scan` replaces an `Index Scan`), you've *demonstrated causally* what the index buys you — far stronger than asserting it. State both plans side by side in the findings.

## Three measurement classes — pick the right technique

The 4 steps above are for **Class A: DB-engine / plan-driven queries** — where the *plan tree* is the proof and a forced-path contrast isolates the mechanism. The other two classes are:

**Class B: CPU-bound library / runtime microbenchmarks.** "How many µs does JWT HMAC verification take?", "is JSON serialization faster than protobuf at 2KB?", "what's the per-call overhead of this middleware?". There is no plan to read — the cost is pure CPU on fixed input. The DB steps (EXPLAIN, forced-path, VACUUM ANALYZE) don't apply; use this protocol instead:

1. **Reproduce the real call shape.** Don't benchmark `hash(secret)` in isolation if the real path is full `jwt.decode(token, secret, algorithms=[...])` with claim validation. Measure the function the hot path actually invokes.
2. **Warmup, then percentiles — never just the mean.** Run 1–2k warmup iterations (JIT/cache/branch-prediction stabilization), then 10k–100k measured iterations recording each with `perf_counter_ns` (Python) / `process.hrtime.bigint()` (Node) / `time.Nanoseconds()` (Go). Report **p50, mean, and p99** plus **ops/s**. The mean hides the tail; p99 is what budget math needs.
3. **Record the exact runtime + version.** Microbenchmarks are interpreter-sensitive. A Python number is a *conservative upper bound* for the same algorithm in Go/Node/Rust (often 5–20× faster compiled) — say so when extrapolating. Always state `Python 3.11.15`, `Node 20.x`, `go1.22`, etc.
4. **Contrast variants to prove the mechanism.** Compare HMAC-vs-RSA, sign-vs-verify, raw-crypto-vs-full-library. The delta *is* the finding ("RSA verify is 3.5× slower than HMAC but still 0.04% of budget → immaterial").
5. **Validate inputs before the timing loop.** A subtly invalid fixture (e.g. an already-expired test token) throws inside the loop and wastes a full run. Construct the token with `exp = now + 86400` and confirm one decode succeeds *before* entering `bench()`.

A reusable scaffold (the `bench()` percentile helper + a JWT worked example) is in `references/cpu-microbenchmarking.md`.

**Class C: Analytical / simulation modeling.** "What cache hit rate will a 10K-entry LRU give me at 100 QPS?", "how much memory will 100K cached records use?", "what queue depth do I need for p99 < 150ms at this arrival rate?". You can't run the real system (it isn't built, or the load/distribution is hypothetical), but the design needs a number. This is modeling, not measurement — be honest about that label. Protocol:

1. **Pick a defensible distributional model, don't invent one.** Web content popularity (page views, short-link clicks, cache keys) is **Zipf/power-law** — `P(rank i) = i^−s / H(N,s)`, exponent `s ≈ 0.8–1.2`. Queue/latency questions use **M/M/1 or M/M/c** (Poisson arrivals, exponential service). Memory questions use **direct measurement of one record** × N. State the model and its parameters explicitly; the number is only as trustworthy as the model.
2. **Sweep the parameter the architect is deciding over.** If the question is "what LRU size?", tabulate hit rate across cache sizes (100 → 1K → 10K → 100K), not just one. If it's memory, sweep record counts. This is the Class-A "sweep the scale" discipline applied to a model instead of a live query.
3. **Report results as a table, label each row with the model parameters.** A reader must be able to see "Zipf(1.0), N=50K, cache=10K → 86%" and judge whether those parameters fit their system. Include the top-1%/top-10%/top-50% concentration numbers — they're what make the hit rate intuitive.
4. **Discount for non-stationarity.** Stationary-distribution models *overestimate* real cache hit rates by ~5–15 pts because real traffic has bursts, new-key arrival, and diurnal patterns. State this correction explicitly: "modeled 86% → expect ~75–81% in production."
5. **Contrast with at least one alternative parameter.** Show `s=1.0` vs `s=1.2`, or "full record" vs "minimal record" for memory. The sensitivity *is* part of the answer — it tells the reader how much the conclusion hinges on the assumed distribution.
6. **Memory sizing: measure one record, don't estimate.** For Python, deep `sys.getsizeof` (following dict/list references) on a representative record gives a real per-entry byte count; multiply by N and add the container's per-entry overhead (OrderedDict/LRU node ≈ 56B in CPython 3.11). Don't eyeball "a record is ~1KB" — Python object headers, interned-str overhead, and datetime objects balloon the real number (a 6-field dict that *looks* like ~300B of text measured 1.3KB).

A reusable scaffold (Zipf hit-rate model + Python `sys.getsizeof` deep memory probe) is in `references/analytical-modeling.md`.

## Capturing findings

Write a single Markdown file (match the repo's research-notes convention). Structure:

1. **Verdict up front** — CONFIRMED / REFUTED / PARTIAL, one sentence.
2. **Headline numbers** — a table of row-count → execution-time, plus plan shape in one line.
3. **Why it's fast/slow** — the mechanism, quoting the plan (node names, `Heap Fetches`, buffer hits) and the doc section that explains it.
4. **Scaling** — the sweep table + the growth curve characterization.
5. **Contrast** — the forced-path plan proving what the index/feature does.
6. **Citations** — doc URLs + section for the *explanatory* claims; verbatim plan + environment (version, OS) for the *measured* claims. Both are citations; they cite different source tiers.
7. **Reproducibility** — the exact commands and SQL files to regenerate the numbers. If a reviewer can't re-run it, it's not evidence.

## Pitfalls

- **Timing a cold run and reporting it as the steady state.** Cache matters. Run the query 3–5 times; report the warm range, note the cold first-run separately. (In one session the first run was 0.65ms including a planning-cache miss; warm runs stabilized at 0.44–0.48ms.)
- **Reporting only `Execution Time` and ignoring `Planning Time`.** For sub-millisecond queries, planning time (0.06–0.6ms) is a meaningful fraction. Report both; consider `PREPARE`/prepared statements if planning dominates.
- **Confusing "works on my version" with "works."** Always record the exact engine version (`SELECT version()`). Plan behavior and optimizer choices change between major versions.
- **Forgetting `VACUUM ANALYZE` after loading test data.** Without stats the planner guesses row counts and may pick a plan you won't see in production. Always `VACUUM ANALYZE` before measuring.
- **Claiming "no sort" without checking the plan.** An `ORDER BY` with an index *can* skip the sort — the planner doesn't *have* to. Always confirm from the plan, never from the doc alone.
- **Not testing the degraded/no-index path.** If you only ever show the happy path, you can't tell the reader what they'd lose by dropping the index. The contrast is half the value.
- **Presenting a simulation result as a measurement.** A Zipf hit-rate model or an M/M/1 latency curve is a *projection*, not an observation. Always label modeled numbers as "simulated"/"projected" and state the model + parameters. A design council will (correctly) discount a number that silently conflates "I ran it" with "I computed it from an assumed distribution." Both are valid evidence — at different confidence tiers.

## Tooling notes

- **Containerize the target engine** so the measurement is reproducible and doesn't depend on a host install. PostgreSQL official images: `docker.io/library/postgres:16-alpine`. Connect via `psql` piped from `podman exec -i`.
- **`podman` is a drop-in for `docker`** for these benchmarks and runs rootless without a daemon — use it when the docker socket isn't available. The command surface (`run`, `exec`, `ps`, `rm`) is identical.
- Put the schema, data-generation, and query SQL in separate files so a reviewer can re-run them in order: `schema.sql` → `data.sql` → `query.sql`.

## See also
- `references/empirical-benchmarking.md` — condensed technique: reading PostgreSQL plans, the index-vs-sort question, and a worked example (window-function streak computation).
- `templates/explain-analyze-scaling-sweep.sql` — reusable scaffold: schema, parametric data generation across row counts, the sweep query, and the forced-path contrast block.
- Sibling skills for other evidence tiers: `docs-verification`, `source-code-verification`, `source-code-audit`, `library-state-verification`.
