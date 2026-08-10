# JS/TS Frontend Library Comparison Research

Domain-specific tactics for "compare N JS/TS libraries / component libraries / frameworks" research tasks. Complements the generic GitHub API mechanics in `web-research-tactics.md` §16 with the conceptual framework that makes those calls load-bearing.

## 1. The two-layer architecture — headless primitives vs styled components

The modern JS/TS UI ecosystem is split into two layers. Evaluating a library without knowing which layer it sits in produces shallow comparisons.

**Layer 1: Headless primitives (behavior + accessibility, zero styling)**
Examples: Radix Primitives, Base UI, Headless UI, bits-ui (Svelte), Ark UI, Melt UI.
These provide the keyboard nav, ARIA, focus management, state machines. You bring all styling. Quality here determines accessibility correctness.

**Layer 2: Styled components (visual design built on a headless layer)**
Examples: shadcn/ui (builds on Radix), shadcn-svelte (builds on bits-ui), Mantine (own styling), MUI (own styling + Emotion), Chakra (builds on Ark UI/Zag.js).
These provide the look. Their quality is bounded by the headless layer underneath.

**The load-bearing question for any styled component library is: what headless primitive does it build on, and is THAT primitive still maintained?** A beautiful component library built on a stale/abandoned primitive inherits all its bugs and accessibility gaps forever. This is why `npx shadcn add button` is safe (Radix is battle-tested) while a library built on a stale primitive is not.

## 2. Trace the dependency stack — "which primitive, and is it alive?"

When evaluating a styled/component library, don't stop at its own repo. Trace down:

1. Read its README/package.json to identify the headless primitive dependency.
2. Check THAT primitive's GitHub repo for liveness (§16 repo metadata API).
3. If the primitive is stale, the component library is on borrowed time — flag this even if the component library itself shows recent commits.

**Concrete example from a 2025 UI library comparison:**
- shadcn-svelte (9K★, active Aug 2026) → builds on **bits-ui** (3.5K★, active Jul 2026) ✅ healthy stack
- shadcn-svelte (older versions) → built on **Melt UI** (4.2K★, last push Sept 2025) ⚠️ stale primitive — the migration to bits-ui happened because Melt UI went dormant

The same pattern applies to React (shadcn/ui → Radix), Chakra v3 (→ Ark UI → Zag.js), and any library that delegates behavior to a lower layer.

## 3. The "maintainer moved to successor" liveness signal

JS-ecosystem maintainers frequently sunset a project by **starting a successor under a new name** rather than archiving the original. The old repo keeps `archived: false` and no deprecation notice — the GitHub API signals look healthy. The real signal is elsewhere:

**Detection pattern:**
1. Notice a stale `pushed_at` (3+ months with no commits) on a repo that isn't archived.
2. Check the maintainer's other repos: `api.github.com/users/<maintainer>/repos?sort=updated&per_page=10`.
3. Look for a newer repo in the same domain whose README **credits the stale project as inspiration** — the phrase "inspired the internal architecture" or "built on the ideas of" is the tell.

**Concrete example:** Melt UI (`melt-ui/melt-ui`, last push Sept 2025) looked alive by the API (not archived, 4.2K stars). But the same maintainer (huntabyte) had created **bits-ui**, whose README explicitly credits "Melt UI — A powerful builder API that inspired the internal architecture of Bits UI." That credit line is the deprecation signal — the maintainer moved on without marking the old repo.

This pattern is common in the JS ecosystem because renaming/migrating npm packages is painful, so maintainers start fresh repos instead. Always cross-reference a maintainer's repo list when a project looks dormant-but-not-archived.

**Variant — monorepo consolidation (the repo is archived but the project is thriving):** A repo can return `archived: true` while the library itself is fully alive and actively developed — the code was folded into a parent monorepo. This is NOT a deprecation signal. Example: `expo/router` returned `archived: true` (last push 2024-06-27) in a sweep, which naively reads as "Expo Router is dead." In reality, Expo Router was consolidated into the `expo/expo` monorepo (51K★, active Aug 2026, 5M+ weekly npm downloads under `expo-router`). The npm package (`expo-router`) and its 5M/wk download count are the real liveness signal — the archived standalone repo is just an old home. **When a repo is archived, check the npm registry for the package's current download count before concluding the library is dead.** A live package under an archived org repo = monorepo consolidation, not abandonment.

## 4. Copy-paste (shadcn pattern) vs npm dependency — changes what you evaluate

The "copy-paste component" model (shadcn/ui, 2023+) has spread across the ecosystem: shadcn-svelte, gluestack v5, React Native Reusables all use it. In this model, components are **not an npm dependency** — a CLI copies their source code into your codebase. This fundamentally changes what you evaluate:

| Evaluation criterion | npm dependency library | Copy-paste library (shadcn pattern) |
|---|---|---|
| Bundle size | Matters (tree-shaking, import cost) | Irrelevant (you own the code) |
| Update cadence | Matters (you get updates via npm) | Less relevant (you merge manually) |
| Underlying primitive health | Important | **Critical** — you inherit it permanently |
| CLI / registry quality | N/A | Important (how you add/update components) |
| Customizability | Limited by library's theming API | Total (you edit the source) |
| Version lock-in | Real (breaking changes on upgrade) | None (you control when to update) |

When a library uses the copy-paste model, say so explicitly in findings — it's often the decisive factor for the user's architecture decision. Detect it by README phrases like "copy and paste into your apps," "Use this to build your own component library," "not a pre-packaged dependency," or the presence of a CLI init command (`npx <lib> init` / `npx <lib> add <component>`).

## 5. GitHub API batch for N-library comparison — the proven sequence

For "compare N frontend libraries" tasks, run this sequence (all via parallel curls, §16 mechanics):

**Step 1 — Currency sweep (one batched curl loop):**
```sh
for repo in "org1/repo1" "org2/repo2" "org3/repo3"; do
  echo "--- $repo ---"
  curl -s "https://api.github.com/repos/$repo" \
    | grep -E '"(stargazers_count|pushed_at|archived|full_name)"' | head -4
done
```
Drop or flag any library with `pushed_at` > 6 months stale. This prevents wasting a full research pass on a dead project.

**Distinguish two failure modes in the sweep output** — they need different responses, and confusing them wastes turns:
- **Rate-limit hit** → the API returns valid JSON but all fields are `null`/`None` (`stars: None`, `pushed: None`), or a 403 with `"message": "API rate limit exceeded"`. Response: wait, or fall back to `raw.githubusercontent.com` for READMEs (no rate limit). Do NOT conclude the library doesn't exist.
- **Wrong org/repo path (NOT FOUND)** → the API returns `{"message": "Not Found"}`. This means your guessed `org/repo` was wrong — extremely common because org paths are not guessable. Examples hit in a 25-library sweep: `jotaijs/jotai` → actually `pmndrs/jotai`; `expo/router` → actually `expo/expo`; `ciscoheat/sveltekit-superforms` → actually `ciscoheat/superforms`; `Lp-js/svelte-forms-lib` → actually `tjinauyeung/svelte-forms-lib`. Response: jump straight to Step 2 (search API) to find the correct path. Do not keep guessing path variants — the search API resolves it in one call.

**Step 2 — Discover missing repos via search API:**
When you don't know the exact org/repo for a named library, use the search API rather than guessing:
```sh
curl -sL "https://api.github.com/search/repositories?q=<library-name>&sort=stars&per_page=5" \
  | python3 -c "
import json,sys; d=json.load(sys.stdin)
[print(f\"{r['full_name']} ({r['stargazers_count']}★): pushed={r['pushed_at'][:10]}\")
 for r in d.get('items',[])[:5]]"
```
This also surfaces adjacent libraries you didn't know about (e.g., searching "nativewind" surfaced `react-native-reusables` at 8.5K★ — a shadcn port for RN that wasn't in the original request but was highly relevant).

**Step 3 — README batch (parallel curls via raw.githubusercontent.com):**
```sh
for repo in "org1/repo1" "org2/repo2"; do
  echo "=== $repo ==="
  curl -sL "https://raw.githubusercontent.com/$repo/main/README.md" -A "Mozilla/5.0" | head -50
done
```
READMEs carry the positioning claims ("headless," "unstyled," "built on Tailwind," "cross-platform") that are the primary evidence for the comparison. The first 50 lines usually contain the self-description, badges, and feature list — enough to classify the library without reading the whole doc.

**Step 4 — Trace dependency stacks** (§2 above) for any library whose README mentions building on another project.

**Rate-limit pitfall (unauthenticated GitHub API = 60 requests/hour):** A multi-library sweep (5+ libraries, multiple repos each) burns through 60 fast. The sweep returns valid JSON but all fields are `null`/`None`, or a 403 `rate_limit` error. Two mitigations: (1) batch currency + search in as few API calls as possible; (2) fall back to `raw.githubusercontent.com` for READMEs and registry JSON — these are served from the raw content CDN, NOT the API, and have no per-hour limit. Always check `api.github.com/rate_limit` at the first sign of null fields so you know which mode you're in.

## 6. shadcn/ui registry JSON — the primary source for "what does this copy-paste library actually use?"

For copy-paste component libraries (§4), the registry JSON is the primary source — it IS the code the CLI copies into your project. For shadcn/ui specifically, the registry endpoints serve the raw component source:

```
https://ui.shadcn.com/r/styles/new-york/<component>.json
```

Each returns a JSON object with a `files` array; each file has a `path` (where it lands in your repo) and `content` (the full source code). This lets you answer "what does shadcn/ui use internally for X?" by reading the actual copied code, not docs or blog posts.

**Concrete example — confirming the styling stack (Aug 2026):**
```sh
# The 'utils' registry entry — this is what becomes lib/utils.ts
curl -sL "https://ui.shadcn.com/r/styles/new-york/utils.json" -A "Mozilla/5.0"
# → files[0].content:
#   import { clsx } from "clsx"
#   import { twMerge } from "tailwind-merge"
#   export function cn(...inputs) { return twMerge(clsx(inputs)) }

# The button component — uses cva for variants
curl -sL "https://ui.shadcn.com/r/styles/new-york/button.json" -A "Mozilla/5.0"
# → import { cva, type VariantProps } from "class-variance-authority"

# The chart component — wraps Recharts
curl -sL "https://ui.shadcn.com/r/styles/new-york/chart.json" -A "Mozilla/5.0"
# → import * as RechartsPrimitive from "recharts"

# The toast component — wraps Sonner
curl -sL "https://ui.shadcn.com/r/styles/new-york/sonner.json" -A "Mozilla/5.0"
# → import { Toaster as Sonner } from "sonner"
```

**Why this matters:** blog posts and docs can be stale, but the registry JSON is the source of truth that ships into every project. When someone asks "does shadcn/ui use cva / Recharts / Sonner?" the registry endpoint is a definitive, one-curl answer. The same pattern applies to shadcn-svelte's registry (`shadcn-svelte.com/registry/...`) — check the port's docs for its endpoint format.

The `<component>.json` path convention is consistent: try the component name lowercased (`button`, `table`, `chart`, `sonner`, `dialog`, `dropdown-menu`). For a full list of available component names, scrape the registry index page.

## 7. Bundle size: use badgen.net, not bundlephobia's gzip field

The bundlephobia API (`bundlephobia.com/api/size?package=<pkg>`) returns `gzipSize` as **0** for many packages — the field is unreliable. For accurate min+gzip sizes, use the **badgen.net bundlephobia badge** instead:

```sh
# Returns SVG with aria-label="minzipped size: 44.2 KB"
curl -sL "https://badgen.net/bundlephobia/minzip/motion" | grep -oP 'minzipped size: \K[0-9.]+ KB'
# → 44.2 KB
```

Batch example (verified sizes from an Aug 2026 chart/animation comparison):

| Package | bundlephobia gzip | badgen minzip |
|---|---|---|
| motion | **0.0 KB** ❌ | **44.2 KB** ✅ |
| recharts | **0.0 KB** ❌ | **144.1 KB** ✅ |
| chart.js | **0.0 KB** ❌ | **66.8 KB** ✅ |
| gsap | **0.0 KB** ❌ | **26.7 KB** ✅ |

The bundlephobia `size` field (minified, pre-gzip) is reliable — it's only `gzipSize` that returns 0. If you only need approximate sizes and don't want the badge-parse step, `size/1024 * 0.3` is a rough gzip estimate, but prefer badgen for any load-bearing number.

## 8. Collapsed-accordion FAQ/doc extraction

Modern component-library doc sites (Base UI, Tamagui, many Docusaurus sites) hide key positioning text behind clickable FAQ accordions or tab panels. The `browser_snapshot` shows the headings but not the collapsed body text. Extract via `browser_console`:

```js
// browser_console, expression= — extract all body text including collapsed sections
(() => {
  const els = document.querySelectorAll('h2,h3,p,li,div');
  const texts = [...els].map(el => el.textContent.trim())
    .filter(t => t && t.length > 20 && !t.includes('{') && !t.includes('._'));
  const seen = new Set();
  const result = [];
  for (const t of texts) {
    const key = t.substring(0, 80);
    if (!seen.has(key)) { seen.add(key); result.push(t.substring(0, 300)); }
  }
  return result.slice(0, 30).join('\n---\n');
})()
```

This works because the DOM contains the full text even when the visual accordion is collapsed — the content is hidden via CSS, not removed from the DOM. The dedup logic prevents the same paragraph (which appears in both the accordion header and body) from printing twice. This is how Base UI's decisive "the most important difference is that Base UI is actively maintained... with a dedicated team of 7" FAQ answer was extracted.

## 9. npm registry + downloads API — the rate-limit-free data layer

The GitHub API sequence in §5 is powerful but burns through the 60/hr unauthenticated rate limit fast on an N-library sweep. The **npm registry and downloads APIs have no per-hour limit** and carry four comparison dimensions that are often more current than GitHub stars: version, last-modified date, unpacked size, and weekly downloads. When GitHub rate-limits you, pivot here first — don't wait.

**Three endpoints, batched in terminal loops:**

```sh
# 1. Package metadata — version + last-modified (liveness signal) + unpacked size
npm view <pkg> version time.modified dist.unpackedSize

# 2. Weekly downloads (community/adoption signal, no rate limit)
curl -s "https://api.npmjs.org/downloads/point/last-week/<pkg>" \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('downloads','?'))"

# 3. Bundle size (bundlephobia — see caveat below)
curl -s "https://bundlephobia.com/api/size?package=<pkg>" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('gzip','?'), d.get('size','?'))"
```

**Batch all three in one terminal call per library group** (parallel calls across groups). Verified in a 25-library charting/viz comparison (Aug 2026):

| Dimension | npm API field | Why it's load-bearing |
|---|---|---|
| Version | `npm view <pkg> version` | Currency — is it on a recent major? |
| Last modified | `time.modified` | Liveness — more reliable than `pushed_at` for maintenance signal |
| Unpacked size | `dist.unpackedSize` | On-disk footprint (NOT bundle size — see js-library-benchmarking skill) |
| Weekly downloads | `downloads/point/last-week` | Real adoption signal; a package with 55M/wk (recharts) vs 7K/wk (@unovis/react) tells you community size |
| Bundle gzip | bundlephobia `gzip` | User-facing footprint (with caveats — §7 + below) |

**Scoping package names — common gotchas:** Many libraries publish under scoped names or have a legacy unscoped redirect. Always probe both:
- `nivo` → package is `@nivo/core` (the bare `nivo` is a different, unrelated package)
- `visx` → package is `@visx/<module>` (e.g., `@visx/group`); bare `visx` doesn't exist
- `reactflow` → renamed to `@xyflow/react` in v12; old name still works but is deprecated
- `three.js` → package is `three`
- `tremor` → React package is `@tremor/react`; bare `tremor` is an unrelated log-parsing tool
- `@unovis/core` → does NOT exist; the scoped package is `@unovis/react` (and `@unovis/ts` for vanilla)

When `npm view <scoped-pkg>` returns E404, check if the bare name redirects, then search npm for the scoped variant.

**Bundlephobia full-fetch failures (refinement to §7):** §7 documents that bundlephobia's `gzipSize` returns 0. A second failure mode: **the entire fetch fails** (returns null/throws on JSON parse) for some packages — observed on `plotly.js`, `three`, `nivo`, `@observablehq/plot`, `@unovis/react`, `lightningchartjs` in Aug 2026. These aren't rate-limit issues (retrying doesn't help) — they're packages bundlephobia hasn't indexed or can't resolve. Fallback ladder for bundle size when bundlephobia fails:
1. `npm view <pkg> dist.unpackedSize` — on-disk size (always works; overestimates bundle due to type files/dual CJS+ESM, but usable as a relative ranking signal).
2. The badgen.net badge (§7) — sometimes succeeds where the API JSON fails.
3. Known-published `*-dist-min` packages (e.g., `plotly.js-dist-min`) — if the library ships a pre-minified package, bundlephobia can size THAT.

**Bundlephobia rate-limiting (third failure mode, distinct from the above):** When you batch multiple `curl` calls to `bundlephobia.com/api/size?package=<pkg>` — even with `sleep 2-3` between them — bundlephobia throttles aggressively, returning failures (JSON parse error / empty response) for most packages in the batch. Observed in Aug 2026: of 11 sequential requests with 2s gaps, only 2-3 succeeded; the rest silently failed. Unlike the "not indexed" failures (which fail consistently on retry), rate-limit failures will succeed if you space them 5-10s apart — but that's impractical for a 10+ library sweep. **Practical approach: hit bundlephobia for the 3-4 packages you care about most (one at a time), and rely on `npm registry + downloads` for the full sweep.** Do not loop all N packages through bundlephobia in sequence expecting it to work.

**`registry.npmjs.org` as a curl-based alternative to `npm view`:** The `npm view` CLI command (used in §9's snippets) requires npm to be installed and adds CLI startup overhead per call. For pure curl-based batch loops, hit the raw registry endpoint instead — same JSON data, no npm dependency, works in any environment:

```sh
# Package metadata via raw registry API (no npm CLI needed)
curl -s "https://registry.npmjs.org/<pkg>/latest" \
  | python3 -c "
import sys,json; d=json.load(sys.stdin)
print(f'version: {d[\"version\"]}, unpacked: {d[\"dist\"][\"unpackedSize\"]} bytes, files: {d[\"dist\"][\"fileCount\"]}')"

# Batch loop — no rate limit, no npm dependency
for pkg in "animejs" "motion" "gsap" "video.js" "hls.js"; do
  echo "=== $pkg ==="
  curl -s "https://registry.npmjs.org/$pkg/latest" \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  v{d[\"version\"]}, {d[\"dist\"][\"unpackedSize\"]:,} bytes')"
  sleep 0.5
done
```

This returns `version`, `dist.unpackedSize`, `dist.fileCount` — everything `npm view` gives you for comparison purposes, in a portable curl loop.

**Official library websites as a primary feature + bundle-size source:** For active, well-maintained libraries, the maintainer's own homepage often publishes the most current bundle size and a curated feature list — sometimes more accurate than bundlephobia. Examples from an Aug 2026 animation/media comparison:
- `animejs.com` displayed "Bundle size: 27.13 KB" (gzip, tree-shakeable) alongside its full feature matrix (timelines, SVG morphing, scroll observer, draggable, WAAPI).
- `motion.dev` showed v13.0.0, React/JS/Vue platform support, and the "hybrid engine" (WAAPI + JS) positioning.
- `gsap.com` confirmed it's now free (Webflow-owned) and listed the full plugin suite (ScrollTrigger, MorphSVG, DrawSVG, Draggable, Flip, SplitText).

When bundlephobia rate-limits or returns 0 gzip, check the library's own homepage before falling back to `dist.unpackedSize` estimation — the maintainer may publish the exact number you need.

## 10. Multi-dimensional library comparison — the output shape that works

When comparing many libraries (10+) across many dimensions (5-7 scored criteria), the deliverable that serves the user is **three layered views**, not a flat table:

1. **Per-library detail sections** — one section per library with: package name + version + downloads + bundle size (live-fetched), a scoring table for each dimension (1-10 with one-line justification per score), pros, cons, best use case, and pricing (free vs paid — flag paid libraries explicitly). This is the evidence layer.

2. **Summary comparison table** — all libraries in one matrix: rows = libraries, columns = the scored dimensions + free/paid + best-for. Color or bold the winner per category. This is the scan layer — the user looks here first to shortlist.

3. **Per-use-case recommendations** — group libraries by the problem they solve (e.g., "General charts → #1 Chart.js, #2 ECharts"; "Financial → #1 Lightweight Charts"). For each use case, name 1-2 picks with a one-line "why." This is the decision layer — the user acts here.

**Scoring rubric (1-10) — anchor each score to avoid inflation.** Define what 9-10 / 7-8 / 5-6 / 3-4 / 1-2 means (e.g., "10 = best in class, industry standard; 5 = usable with notable caveats; 1 = poor or unsupported"). Without anchored definitions, scores drift toward 7-8 for everything and lose discriminative value.

**Score community from download counts, not just stars.** Weekly npm downloads are a harder adoption signal than GitHub stars (stars accumulate forever; downloads reflect current use). Rough tiers: 10M+/wk = dominant ecosystem (recharts, d3, three, chart.js); 1-5M = major (echarts, highcharts, visx, apexcharts); 100K-1M = established niche (lightweight-charts, plotly, observable-plot); <10K = emerging/risky (@unovis/react at 7.8K).

**Framework support matrix is often decisive.** For frontend libraries, score React integration, Svelte support, and SSR compatibility separately — a library that's excellent in React but has no Svelte story (Recharts, Nivo, Tremor) is a dealbreaker for multi-framework projects. Note when a library has an *official* cross-framework sibling (React Flow → Svelte Flow) vs community wrappers vs nothing.
