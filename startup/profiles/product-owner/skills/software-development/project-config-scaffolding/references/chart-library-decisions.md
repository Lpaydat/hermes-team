# Chart Library Selection — Included, Excluded, and Why

Verified from installed source code, npm bundlephobia, and uPlot's benchmark suite (Aug 2026).
Performance measured, not claimed.

## Performance hierarchy (rendering speed + data capacity)

```
uPlot > Chart.js > ECharts > Lightweight Charts >> Recharts
```

| Library   | Render Engine          | 10K pts  | 100K pts           | 1M pts              | Bundle (gzip) |
|-----------|------------------------|----------|--------------------|--------------------|---------------|
| uPlot     | Canvas + TypedArrays   | 34ms     | ~90ms              | ~400ms             | 22KB          |
| Chart.js  | Canvas                 | fast     | OK                 | laggy              | 68KB          |
| ECharts   | Canvas + SVG + WebGL   | fast     | OK (progressive+LTTB) | OK (scatterGL WebGL) | 332KB    |
| Light Charts | Canvas              | fast     | OK                 | OK (time-series)   | 45KB          |
| Recharts  | SVG (DOM per point)    | lag starts | freezes (100K DOM nodes) | dead          | 148KB      |

## INCLUDED in tech-preferences (9 tools)

| Tool                | Score | Use Case                                    | Why Included |
|---------------------|-------|---------------------------------------------|--------------|
| Chart.js            | 9/10  | General charts (bar, line, pie)             | Canvas, fast, framework-agnostic, free. Beats Recharts on size and performance. |
| ECharts             | 9/10  | Complex charts, 100+ types, real-time, 3D   | Canvas+WebGL, LTTB downsampling built-in. Handles most scientific charts natively (3D scatter, surface, heatmap, box plot, parallel coords). |
| Lightweight Charts  | 10/10 | Financial/trading (candlestick, volume)     | TradingView's library, battle-tested, 45KB. Only serious choice for trading. |
| uPlot               | 10/10 | Real-time time-series streaming             | Fastest of all. TypedArrays (0.21MB vs 8MB+ for 100K points). 22KB. |
| Plotly.js           | 7/10  | Scientific only (contour, violin, isosurface, SPLOM) | Only library with native contour/violin/isosurface/volume rendering. 1.36MB — ADR required. |
| Visx                | 8/10  | Custom React charts (D3 + React primitives) | Full D3 control inside React without chart-library abstraction. |
| Cytoscape.js        | 9/10  | Graph/network visualization (Obsidian-style)| What Obsidian actually uses for graph view. Mature, built-in graph algorithms. |
| React Flow          | 9/10  | Interactive node editors, flow diagrams     | Node-based UIs (workflow builders, circuit designers). Different from Cytoscape. |
| deck.gl             | 8/10  | Large-scale geospatial/map visualization    | Only serious choice for geospatial at scale. |

## EXCLUDED (ditched) — with score and reason

| Tool          | Score | Why Excluded |
|---------------|-------|--------------|
| Recharts      | 6/10  | SVG-only (worst performance — 100K DOM nodes freezes browser). 148KB. Fully overlapped by Chart.js (simpler) and ECharts (more capable). shadcn/ui wraps it, but architect can still pick it for shadcn projects via ADR. |
| ApexCharts    | 4/10  | 229KB gzip (heaviest of all). Revenue-based license (no longer free). Poor tree-shaking. No reason to choose over Chart.js or ECharts. |
| Highcharts    | 7/10  | Mature, polished. But commercial license required ($). We only include free tools. |
| D3.js         | 8/10  | Powerful but too low-level. Visx covers the "D3 + React" use case with better DX. Including raw D3 means every chart is a custom build. |
| Nivo          | 7/10  | Nice DX but React-only, 50+ deps, Chart.js/ECharts cover same ground with less weight. |
| Tremor        | 6/10  | Dashboard React components, not a real chart library. Wraps Chart.js. Use shadcn/ui + Chart.js directly. |
| Unovis        | 7/10  | Only cross-framework chart lib. Good concept but smaller community, less mature than ECharts. |
| AnyChart      | 5/10  | Commercial/paid. Less capable than free ECharts. |
| LightningChart| 8/10  | Highest raw performance (GPU). But commercial license. uPlot covers performance use case for free. |
| Sigma.js      | 7/10  | Graph rendering alternative to Cytoscape. Lower-level (rendering only, no graph theory). Cytoscape has built-in algorithms and Obsidian pedigree. |

## ECharts scientific coverage (verified from echarts@6.1.0 + echarts-gl@2.1.0 source)

- Native: 3D scatter, surface plots, heatmaps, box plots, parallel coordinates, GL-accelerated rendering, LTTB downsampling
- NOT native: contour plots, violin plots (buildable via custom series but not out of box)
- ECharts cannot fully replace Plotly. Plotly still needed for: contour, violin, isosurface, volume rendering, SPLOM, native error bars.
- For 90% of scientific use cases, ECharts + echarts-gl covers it.

## Decision matrix (which to use when)

```
Need general charts?              → Chart.js
Need complex/100+ types?          → ECharts
Need real-time streaming?         → uPlot
Need trading/financial?           → Lightweight Charts
Need scientific (contour/violin)? → Plotly.js (ADR required)
Need custom React D3 charts?      → Visx
Need graph/network visualization? → Cytoscape.js
Need node editor/flow diagrams?   → React Flow
Need maps/geospatial?             → deck.gl
Already in shadcn/ui project?     → Recharts via shadcn (not in prefs, ADR if needed)
```
