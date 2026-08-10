# Drizzle vs Kysely: Worked Example Findings

Complete benchmark data from a hands-on comparison of **drizzle-orm@0.45.2** vs **kysely@0.29.4** (Node.js 24.18.0, esbuild 0.25.x). This file is both the reference data and a template for how to structure a comparison findings document.

---

## 1. Bundle Size (esbuild tree-shaken, ESM)

### Minified bytes after bundling

| Usage Pattern | Drizzle | Kysely | Ratio |
|---|---|---|---|
| SQL tag only (`import { sql }`) | 16,979 B (16.6 KB) | 70,619 B (69.0 KB) | Drizzle 4.2x smaller |
| PG schema + select (realistic app) | 90,729 B (88.6 KB) | 174,818 B (170.7 KB) | Drizzle 1.9x smaller |
| PG driver + queries (full app) | 94,005 B (91.8 KB) | 174,900 B (170.8 KB) | Drizzle 1.9x smaller |

### Gzipped (realistic app)

| Library | Gzipped |
|---|---|
| Drizzle | ~22.2 KB |
| Kysely | ~36.7 KB |

### Why Drizzle bundles smaller

- **Per-dialect subpackages**: `drizzle-orm/pg-core`, `drizzle-orm/mysql-core`, `drizzle-orm/sqlite-core` are separate import paths. Using only Postgres means MySQL/SQLite code never enters the bundle.
- **Kysely is monolithic**: The `kysely` package includes all dialect adapters, all 50+ operation nodes, and the full `DefaultQueryCompiler` (178 visit methods) in one tree. Bundlers can't tree-shake individual class methods, so the entire compiler ships.

### npm package metadata (misleading without bundling)

| Metric | Drizzle | Kysely |
|---|---|---|
| Unpacked size | 10.4 MB | ~1.5 MB |
| Total files | 2,666 | 610 |
| JS files | 444 ESM + 444 CJS | 303 |
| Type declarations | 888 | 304 |
| Source maps | 888 | 0 |

Drizzle looks 7x larger on disk but bundles 2x smaller — the disk size is inflated by 13+ dialect adapters + dual ESM/CJS + thorough type declarations, all of which tree-shake to zero.

---

## 2. Query Building Overhead (µs per query)

Measured via `process.hrtime.bigint()`, 100k iterations after 3k warmup, using mock DB drivers (no I/O).

### Using native query builder API (db.select)

| Query Type | Drizzle | Kysely | Ratio |
|---|---|---|---|
| Complex (joins, AND/OR, ORDER, LIMIT, OFFSET) | 59 µs | 10 µs | **Kysely 6x faster** |
| Simple (SELECT WHERE id = ?) | 18 µs | 2.6 µs | **Kysely 7x faster** |

### Using sql template tag (Drizzle only)

| Query Type | Drizzle (sql tag) | Drizzle (db.select) |
|---|---|---|
| Complex | 43 µs | 59 µs |
| Simple | 11 µs | 18 µs |

The sql template tag is faster than the db.select builder because it skips the builder chain overhead.

### Architecture explanation

- **Kysely**: AST node construction → visitor-compiler walk. Lightweight objects, single pass.
- **Drizzle**: SQL chunk-tree construction → recursive `buildQueryFromSourceParams` walk. Heavier object allocation (StringChunk, Param, SQL, SQL.Aliased instances per chunk).

---

## 3. Memory Per Query (retained, 10k queries)

| Library | Bytes/query |
|---|---|
| Drizzle | ~714 B |
| Kysely | ~2,559 B |

Drizzle's compiled query objects are **3.6x smaller** in memory. Kysely retains more because its CompiledQuery carries the full AST node references.

---

## 4. Cold Start (module import → first query)

| Metric | Drizzle | Kysely | Ratio |
|---|---|---|---|
| Import time | ~371 ms | ~80 ms | Kysely 4.6x faster |
| First query build | 1-2 ms | <1 ms | Comparable |

Drizzle's slower import is due to loading 39 subdirectory modules (all dialect adapters are resolved at import time even if tree-shaken later). Kysely has fewer modules to resolve.

---

## 5. Feature Matrix

| Feature | Drizzle | Kysely | Winner |
|---|---|---|---|
| CTEs (WITH) | ✅ `.with()` | ✅ `.with()` + `withRecursive()` + CTEBuilder | Kysely |
| Recursive CTEs | ⚠️ via sql tag | ✅ First-class | Kysely |
| Window functions | ⚠️ sql tag only | ✅ Native (OverNode, PartitionByNode) | Kysely |
| Raw SQL escape | ✅ `sql` tag | ✅ `sql` tag | Tie |
| Transactions | ✅ All drivers | ✅ All drivers | Tie |
| Batch queries | ✅ `batch()` API | ❌ No native batch | Drizzle |
| Streaming | ✅ MySQL drivers | ✅ All drivers | Kysely |
| UNION/INTERSECT/EXCEPT | ✅ | ✅ `union()`, `intersect()`, etc. | Tie |

---

## 6. Edge Runtime Support

| Platform | Drizzle | Kysely |
|---|---|---|
| Cloudflare Workers (D1) | ✅ First-party `drizzle-orm/d1` | ⚠️ Community `kysely-d1` |
| Cloudflare Workers (PG) | ✅ `neon-http`, `neon-serverless` | ⚠️ Custom dialect needed |
| Vercel Edge | ✅ `vercel-postgres`, `neon-http` | ⚠️ Community adapters |
| PlanetScale serverless | ✅ `planetscale-serverless` | ⚠️ Community `kysely-planetscale` |
| Neon HTTP | ✅ `neon-http` | ⚠️ Community `kysely-neon` |
| Turso/LibSQL | ✅ `libsql` | ⚠️ Community |
| Xata HTTP | ✅ `xata-http` | ❌ |
| Core edge-safety (no Node APIs) | ✅ | ✅ |

Drizzle ships **13 first-party edge/serverless drivers** in the main package. Kysely's core is edge-safe but every edge database requires a separate community package.

---

## 7. Final Scorecard

| Category | Winner | Margin |
|---|---|---|
| Query building speed | **Kysely** | 6-7x faster |
| Cold start | **Kysely** | 4.6x faster |
| Per-query memory | **Drizzle** | 3.6x smaller |
| Bundle size | **Drizzle** | 1.9-4.2x smaller |
| Edge runtime drivers | **Drizzle** | 13 first-party vs community-only |
| CTEs / Window functions | **Kysely** | Native vs raw-SQL-only |
| Batch queries | **Drizzle** | Native vs absent |
| Tree-shaking | **Drizzle** | Subpackages vs monolithic |

### Recommendation

- **Edge/serverless-first → Drizzle** (better edge support, smaller bundles, lower memory)
- **High-throughput Node.js analytical → Kysely** (faster query building, native window functions, faster cold start)
- The 6-7x query-building speed gap is the most consequential runtime difference for hot-path throughput.
