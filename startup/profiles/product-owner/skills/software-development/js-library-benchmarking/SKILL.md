---
name: js-library-benchmarking
description: Empirically benchmark and compare JS/TS libraries — bundle size (esbuild tree-shaking), query/build runtime overhead, cold-start, memory per operation. Install locally, write reproducible microbenchmarks, measure rather than trust documentation claims. Use when the user asks to compare libraries by performance, measure bundle size or tree-shaking effectiveness, benchmark query-building or API overhead, or wants "actual measured, not claimed" data. Complements web-research (source-based) by adding hands-on measurement.
---

# JS Library Benchmarking

Measure, don't claim. When a user asks "which library is faster / smaller / better for edge", the answer comes from **installing both, bundling both, and benchmarking both** — not from documentation, blog posts, or model priors. Documentation claims about bundle size and tree-shaking are frequently wrong or outdated.

This skill covers the measurement methodology. For source-code feature analysis (what APIs exist, what's supported), use `web-research` — they complement each other.

## When to reach this skill

- "Compare X vs Y by performance / bundle size / capabilities"
- "How bloated is library Z?" / "Measure the actual bundle size"
- "Which ORM/query builder is faster?"
- "Does library X tree-shake well?"
- "Benchmark the cold start / memory usage of..."
- Any "actual measured, not claimed" request

## Step 1: Gather package metadata (parallel)

Batch these in one terminal call:

```bash
npm view <pkg> version dependencies
npm view <pkg> dist.unpackedSize
npm pack <pkg> --dry-run 2>&1 | tail -5  # total files, unpacked size
```

Then install both packages into a scratch project:

```bash
mkdir -p /tmp/orm-test && cd /tmp/orm-test
npm init -y --silent && npm install <pkg-a> <pkg-b> esbuild --silent
```

**Record:** version, dependency count, unpacked size, total file count. These are context, not conclusions — the real signal comes from bundling.

## Step 2: Measure bundle size with esbuild tree-shaking (the critical test)

npm unpacked size is **misleading** — it includes every dialect, platform adapter, and type declaration. What matters is what survives tree-shaking in a real app. Write entry-point files that mirror realistic usage, then bundle:

```bash
# Entry point importing only what a real app uses
npx esbuild entry.js --bundle --minify --format=esm --external:pg \
  --outfile=/tmp/bundle.js 2>&1 | grep -E "size|errors"
ls -la /tmp/bundle.js | awk '{print $5, "bytes minified"}'
gzip -c /tmp/bundle.js | wc -c | awk '{print $1, "bytes gzipped"}'
```

**Test multiple usage levels** — they reveal tree-shaking effectiveness:
1. **Minimal** (e.g., `import { sql }` only) — shows core overhead
2. **Realistic** (schema + query builder + driver) — what a real app ships
3. **Full** (all features) — worst case

The ratio between minimal and realistic reveals whether the library tree-shakes well. A 4x gap means poor tree-shaking; a 1.5x gap means good tree-shaking.

### Mark driver deps as `--external`

Database drivers (`pg`, `pg-pool`, `mysql2`, `better-sqlite3`) are always external — the user brings their own. Mark them `--external:pg --external:pg-pool` to avoid spurious resolution errors that mask the real bundle size.

See [`scripts/measure-bundle-size.sh`](scripts/measure-bundle-size.sh) for a reusable measurement harness.

## Step 3: Write microbenchmarks for runtime overhead

Use `process.hrtime.bigint()` for nanosecond precision. Structure:

```javascript
// Warmup (JIT optimization)
for (let i = 0; i < 3000; i++) { buildQueryA(i); buildQueryB(i); }

// Measure
const N = 100000;
let start = process.hrtime.bigint();
for (let i = 0; i < N; i++) buildQueryA(i);
let end = process.hrtime.bigint();
const usPerQuery = Number(end - start) / N / 1000; // microseconds
```

**Always verify both paths produce valid output** before benchmarking — a broken query builder that returns garbage will be "fast" for the wrong reason:

```javascript
const resultA = buildQueryA(0);
console.log('Lib A SQL:', resultA.sql.slice(0, 100));
```

### The mock DB driver pattern (critical for query builders)

Query builders (Drizzle, Kysely, Prisma) need a DB instance to build queries, but you want to measure **build overhead, not I/O**. Create a mock:

```javascript
// Kysely: minimal mock driver
class MockDriver {
  async init() {}
  async acquireConnection() { return {}; }
  async releaseConnection() {}
  async destroy() {}
}
const db = new Kysely({
  dialect: {
    createDriver: () => new MockDriver(),
    createAdapter: () => ({}),
    createQueryCompiler: () => new DefaultQueryCompiler(),
    createIntrospector: () => ({}),
  },
});
// Now db.selectFrom('t').compile() measures pure build overhead
```

```javascript
// Drizzle: use pg-proxy driver with mock callback
const db = drizzle(async (sql, params, method) => {
  return { rows: [] };
}, { schema: { users }, mode: 'default' });
// db.select().from(users).toSQL() measures pure build overhead
```

**Pitfall:** Drizzle's `drizzle-orm/node-postgres` requires the `pg` package at import time. Use `drizzle-orm/pg-proxy` for benchmarks — it has the same query-building path but no hard `pg` dependency.

**Rendering-bound libraries (charting/viz/UI) cannot be benchmarked in Node.js.** The Step 3 pattern measures *build/compute overhead*, which is the right thing for query builders, validators, and serialization libs. But for libraries whose cost is in the render path (Canvas draw calls, SVG DOM node creation, WebGL shader compilation), Node.js benchmarks produce misleading near-zero results — option/config construction is O(1) while the actual cost is browser-bound. If your `process.hrtime.bigint()` benchmark returns `0.00ms` for a library processing 1M data points, you are not measuring rendering — you're measuring `new Object({ data: [...] })`. For these libraries, either (a) run the benchmark in a headless browser (Playwright/Puppeteer with `page.evaluate`), or (b) cite an authoritative browser-based benchmark suite from the maintainer rather than producing a misleading Node.js number. See [`references/chart-library-benchmarking.md`](references/chart-library-benchmarking.md) for the charting-library worked example and verified data.

See [`scripts/benchmark-template.mjs`](scripts/benchmark-template.mjs) for a copy-paste benchmark scaffold.

## Step 4: Measure cold start (module load time)

Cold start matters for serverless/edge. Use dynamic import to isolate load time:

```javascript
const start = process.hrtime.bigint();
const { pgTable, serial } = await import('drizzle-orm/pg-core');
const { drizzle } = await import('drizzle-orm/pg-proxy');
const importEnd = process.hrtime.bigint();
console.log(`Import: ${Number(importEnd - start) / 1e6 | 0}ms`);
```

Run 3 times and report the median. OS cache warming makes run 1 slower; runs 2-3 are stable.

**Pitfall:** Some libraries (e.g., Kysely's `PostgresDialect`) require their driver package at construction time. For cold-start measurement, use the mock driver pattern from Step 3, not the real dialect constructor.

## Step 5: Measure memory per operation

```javascript
if (global.gc) global.gc(); // requires --expose-gc

let before = process.memoryUsage().heapUsed;
const results = [];
for (let i = 0; i < 10000; i++) results.push(buildQuery(i));
let after = process.memoryUsage().heapUsed;
console.log(`${((after - before) / 10000).toFixed(0)} bytes/query retained`);
results.length = 0; // release
```

This measures **retained** object size (what stays in memory if you hold the result). Transient allocation during build is higher but GC'd — retained is what matters for long-lived references.

## Step 6: Analyze feature support from source code

For capability comparison (CTEs, window functions, streaming, etc.), grep the installed source:

```bash
# Feature presence check
find node_modules/<pkg>/ -name "*.js" | xargs grep -li "<feature>" 2>/dev/null
# API surface check
grep -n "<method>" node_modules/<pkg>/dist/*.d.ts
# Operation node types (AST-based libraries)
ls node_modules/<pkg>/dist/operation-node/ | grep -i "window\|cte\|partition"
```

**Distinguish native API from raw-SQL escape hatch.** A library having `sql\`OVER (...)\``  is not the same as having a typed window-function builder. Check for dedicated builder classes / operation nodes, not just whether the keyword appears in source.

**Charting/viz libraries: inspect `lib/chart/` (or equivalent) directories for native series types.** Documentation can claim "supports X" but the truth is in the shipped source. For Apache ECharts: `ls node_modules/echarts/lib/chart/` reveals the actual native series (boxplot, heatmap, parallel, sankey, etc.). For ECharts-GL (3D/WebGL): `ls node_modules/echarts-gl/lib/chart/` (scatter3D, surface, bar3D, scatterGL, graphGL, flowGL). For Plotly: grep the dist for trace type strings. A series type absent from the directory is not natively supported — it may be buildable via a `custom` series (ECharts) or similar escape hatch, but that is not the same as native support. See [`references/chart-library-benchmarking.md`](references/chart-library-benchmarking.md) §1 for the ECharts scientific capability checklist derived this way.

## Step 7: Synthesize — scorecard + conditional recommendation

Present results as a **scorecard table** with measured numbers, not prose. Then give a **conditional recommendation** — "choose A if X, choose B if Y" — because the winner usually depends on the deployment context (edge vs Node.js, bundle-critical vs throughput-critical).

Never present a flat "X is better" — real benchmarking reveals trade-offs.

## Pitfalls

1. **npm unpacked size ≠ bundle size.** A 17MB package on disk can bundle to 17KB after tree-shaking. Always measure the bundled output, never quote `npm pack` size as the user-facing footprint.

2. **Package `exports` field blocks deep imports.** Many packages (Drizzle, Kysely) restrict subpath access via the `exports` map in package.json. `import { PgDialect } from 'drizzle-orm/pg-core/dialect.js'` will throw `ERR_PACKAGE_PATH_NOT_EXPORTED`. Use the exported paths (`drizzle-orm/pg-core/dialect` without `.js`) or access internals via the public API surface.

3. **Use `.toSQL()` / `.compile()` for query builders, not `.execute()`.** You're measuring build overhead, not DB round-trip. Drizzle: `.toSQL()`. Kysely: `.compile()`. Never let a query hit a real DB in a build-overhead benchmark.

4. **CJS vs ESM dual shipping inflates npm size.** Drizzle ships 444 `.js` + 444 `.cjs` files. This doubles on-disk size but has zero bundle impact — bundlers only include one format. Don't count both formats when assessing bloat.

5. **Source maps and `.d.ts` files are zero runtime cost.** They inflate npm package size significantly (Drizzle: 888 type files) but never enter a production bundle. Exclude them from bloat analysis.

6. **Run benchmarks with `--expose-gc`** for accurate memory measurement. Without it, `global.gc()` is undefined and memory readings include uncollected garbage.

7. **Warmup matters.** V8 JIT optimization makes the first 1000-3000 iterations significantly slower. Always warmup before measuring, or you'll report 2-3x worse numbers than steady-state.

8. **The label bug.** When printing benchmark results, double-check the ratio label. "A is 0.25x faster than B" is mathematically wrong when A is 4x slower — it should be "B is 4x faster". A surprising number of benchmark scripts get this backwards in their stdout formatting.

9. **Libraries with internal deep imports break esbuild bundling.** Some packages import their own internal modules via deep relative paths (e.g., `echarts-gl` imports `echarts/lib/util/layout`, `zrender/lib/core/matrix`) that esbuild can't resolve from the package root, producing `You can mark the path "..." as external` errors for many files. Fix: bundle the package's **pre-built UMD/CJS dist** instead of its source/ESM entry. `import 'echarts-gl/dist/echarts-gl.js'` bundles cleanly where `import 'echarts-gl'` (resolving to `index.js`) fails. Check `package.json` — the `main` field points to the pre-built dist; the `module` field may point at unbundled source that has unresolved internal paths. Use `main` for benchmarking when `module` breaks.

10. **React component libraries need JSX config for esbuild.** Bundling React component libraries (Recharts, Radix, etc.) without JSX flags produces a 131-byte stub — esbuild strips the JSX without `--jsx=automatic` and can't resolve React without `react` installed. Minimum config: `npm install react`, then `npx esbuild entry.js --bundle --minify --format=esm --jsx=automatic --loader:.js=jsx --outfile=out.js`. Without `--jsx=automatic`, the import resolves but the component code is empty.

11. **Node.js lacks `bc`; use `python3 -c` or `awk` for arithmetic in shell output formatting.** Shell scripts printing KB/MB from byte counts fail with `bc: command not found` on many minimal Linux images (Arch, Alpine). Replace `echo "$size/1024 | bc -l"` with `python3 -c "print($size/1024)"` or `awk "BEGIN{print $size/1024}"`.

## Output format

Deliver a Markdown analysis file with:
1. **Scorecard table** — every category, measured numbers, winner
2. **Per-category detail** — what was measured, how, the raw numbers
3. **Conditional recommendation** — "choose X if..., choose Y if..."
4. **Bottom line** — one paragraph summary

Save to the workspace or repo. The user will want to reference it.

## Reference: Drizzle vs Kysely worked example

See [`references/drizzle-vs-kysely-findings.md`](references/drizzle-vs-kysely-findings.md) for a complete worked example of this methodology applied to a real comparison, including all measured numbers and the final scorecard.
