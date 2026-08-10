# Animation & Media Player Library Comparison

Condensed knowledge bank from a verified Aug 2026 comparison of 6 animation libraries and 7 media player libraries. Bundle sizes, download counts, and versions are point-in-time data from Aug 2026 — re-verify before using as load-bearing for a production decision. Scores are on a 1-10 scale with anchored definitions.

## Animation Libraries

### Key facts (verified Aug 2026)

| Library | Version | gzip (KB) | Weekly DLs | Score | Notes |
|---|---|---|---|---|---|
| Motion (ex-Framer Motion) | 13.0.0 | ~45 | 17.4M (`motion`) / 42.2M (`framer-motion`) | 9 | React-first. `framer-motion` renamed to `motion`; `framer-motion` still published as redirect. `import { motion } from "motion/react"` |
| GSAP | 3.15.0 | ~27 (tree-shakeable core) | 4.4M | 9 | Now free — Webflow acquired GSAP (was previously commercial for premium plugins). ScrollTrigger/MorphSVG/DrawSVG all free now |
| anime.js v4 | 4.5.0 | ~27 (tree-shakeable, modular) | 1.1M | 8 | Complete rewrite from v3. New API: `animate()`, `createTimeline()`, `createDraggable()`, `createSpring()`, `morphTo()`. Bundle shown on homepage: 27.13 KB gzip |
| Auto-Animate | 0.10.0 | ~3 | 1.2M | 7 | Zero-config layout animations. `autoAnimate(ref)` — one line. By FormKit |
| Motion One (`@motionone/*`) | 10.18.0 | ~4-6 per module | 2.2M | 6 | WAAPI-native. Now largely superseded by `motion` package which absorbed the Motion One engine |
| CSS Animations | N/A | 0 | N/A | 8 | Zero cost. `animation-timeline: scroll()` now in Chrome for scroll-driven CSS animations |

### Use-case winners

| Use case | Winner | Why |
|---|---|---|
| Micro-interactions (hover, tap) | **Motion** | Declarative `whileHover`, `whileTap`, gesture props |
| Page transitions | **Motion** | `AnimatePresence` + `layout` prop = seamless enter/exit |
| Complex timelines | **GSAP** | Unmatched timeline precision: labels, nesting, scrubbing |
| SVG morphing | **GSAP** (MorphSVG) | Industry gold standard. anime.js v4 `morphTo()` is viable alternative |
| Scroll storytelling | **GSAP** (ScrollTrigger) | Pinning, scrubbing, horizontal scroll — most mature |
| Data viz animation | **GSAP** or Motion | GSAP for framework-agnostic; Motion for React |
| Zero-config layout anim | **Auto-Animate** | One line of code, auto-detects DOM insertions/removals |

### Can anime.js do everything Motion does?

**No.** anime.js v4 covers ~80% of Motion's capabilities (timelines, SVG, scroll, springs, drag, stagger are all comparable). The gaps are React-specific: no declarative `<motion.div>` component API, no `AnimatePresence` (exit animations), no `layout` prop (automatic layout transitions). For vanilla JS / framework-agnostic projects, anime.js is a strong lightweight GSAP alternative. For React projects, Motion is the clear choice.

### Critical ecosystem facts

- **Framer Motion → Motion rename:** The package `framer-motion` (42M weekly) was renamed to `motion` (17M weekly). Both work; `motion` is the current name. Import path changed from `framer-motion` to `motion/react`. The `@motionone/*` packages (Motion One) were absorbed into `motion`.
- **GSAP is now free:** Webflow acquired Greensock and made all previously-commercial plugins (MorphSVG, SplitText, etc.) free under the standard GSAP license. This was previously a major cost barrier — it no longer exists.
- **Auto-Animate pairs well with Motion:** Use Auto-Animate for list reordering (zero config) and Motion for complex orchestrated animations.

## Media Player Libraries

### Key facts (verified Aug 2026)

| Library | Version | Weekly DLs | Score | Notes |
|---|---|---|---|---|
| Vidstack | 1.x-RC | 68K | 9 | Modern component architecture. React/Svelte/Vue first-class. Built-in HLS/DASH/YouTube/Vimeo providers. From creators of Plyr + Vime |
| Video.js | 8.23 | 1.0M | 8 | Battle-tested 10+ years. Plugin ecosystem. VHS plugin for HLS. Heavy bundle |
| Media Chrome | 4.19 | 3.5M | 8 | Web components for custom UI only (no engine — bring your own hls.js/shaka). Mux-backed |
| hls.js | 1.6.17 | 7.8M | 8 | Industry-standard HLS engine. NO UI — pure streaming. Pair with Media Chrome or Vidstack |
| shaka-player | 5.2.4 | 294K | 7 | Best DASH engine + DRM (Widevine/PlayReady/FairPlay). Google-maintained. Heavy, basic UI |
| Plyr | 3.8.4 | 408K | 7 | Beautiful default UI out-of-box. **Development slowed** — Vidstack is successor from same creator (Rahim Eminov). No native DASH |
| React Player | 3.4.0 | 2.2M | 6 | Simplest for external embeds (YouTube/Vimeo/etc.). ~40KB. No streaming support |

### Use-case winners

| Use case | Winner | Why |
|---|---|---|
| Simple video embed | **React Player** (external) / **Plyr** (self-hosted) | Minimal code |
| HLS streaming | **hls.js** + Media Chrome or Vidstack | hls.js is THE industry standard |
| DASH streaming | **shaka-player** + Media Chrome or Vidstack | Best DASH engine |
| Audio player | **Vidstack** | First-class audio components + React hooks |
| Custom UI | **Media Chrome** | Web components = full control over every control |
| DRM-protected content | **shaka-player** | Widevine/PlayReady/FairPlay |

### Architecture model: engine vs UI vs all-in-one

Media libraries split into three layers (analogous to the headless/styled split in UI components):

1. **Streaming engines** (no UI): hls.js, shaka-player — provide adaptive bitrate, codec support, DRM. You must build controls separately.
2. **UI control layers** (no engine): Media Chrome — web components for play/pause/seek/volume controls. You bring your own streaming engine.
3. **All-in-one players** (engine + UI): Vidstack, Video.js, Plyr — both streaming and UI in one package.

The **composable stack** (engine + UI layer separately) gives maximum flexibility. The **all-in-one** gives fastest setup. Vidstack uniquely bridges both: it's component-based (like a UI layer) but bundles provider integrations (like an all-in-one).

### Critical ecosystem facts

- **Plyr → Vidstack succession:** Vidstack was created by Rahim Eminov (also created Plyr and Vime). Plyr's last meaningful release is v3.8.4; the maintainer moved to Vidstack. This is the "maintainer moved to successor" pattern (see js-library-research.md §3) — Plyr isn't archived but is on borrowed time.
- **hls.js adoption:** At 7.8M weekly downloads, hls.js is more widely used than every player UI library combined. It powers streaming under the hood for many platforms (Twitch, Dailymotion, Akamai clients).
- **Media Chrome is Mux-backed:** Mux (video API company) maintains Media Chrome. It's actively developed and has overtaken Plyr in weekly downloads (3.5M vs 408K).
- **React Player v3:** The v3 rewrite (2024+) uses lazy-loaded players per platform. It does NOT support HLS/DASH streaming — it's purely for embedding external platforms (YouTube, Vimeo, SoundCloud, etc.) via their iframe APIs.

## tech-preferences.json output shape

For library comparison tasks that feed into a project's tech decisions, the output should include a structured `tech-preferences.json` with:
- `primary`: the recommended library
- `score`: 1-10
- `alternatives`: keyed by library short name, each with score + description
- `use_cases`: maps use-case strings to recommended library names
- `recommended_stacks`: named stack combinations (e.g., "best-hls": "hls.js + media-chrome")

Validate the JSON with an ad-hoc script: parse validity, required-key presence, score ranges (1-10), and use_case → library reference integrity (no dangling references to libraries not in alternatives or primary).
