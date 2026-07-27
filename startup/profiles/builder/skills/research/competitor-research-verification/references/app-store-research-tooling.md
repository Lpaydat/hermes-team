# App Store Research Tooling — iTunes API + Google Play scraping

When researching mobile-app ventures (impersonation, clone detection, app
ecosystem sizing, mobile competitor pricing), the two stores have a critical
**asymmetry**: Apple has a legitimate public search API; Google Play does NOT
and must be scraped. Both are reliable from headless.

## Apple — iTunes Search/Lookup API (official, no auth)

### Endpoints

```
# Search apps by keyword (returns ranked results, up to 200 per call)
curl -s "https://itunes.apple.com/search?term=spotify&entity=software&limit=200"

# Lookup by trackId (the app's numeric ID from search results)
curl -s "https://itunes.apple.com/lookup?id=324684580"

# Lookup ALL apps by a developer (via their artistId)
curl -s "https://itunes.apple.com/lookup?id=324684583&entity=software"
```

### Fields returned (verified 2026-07-25)

| Field | Use | Example |
|-------|-----|---------|
| `trackName` | App display name | "Spotify: Music and Podcasts" |
| `bundleId` | Reverse-DNS bundle id | `com.spotify.client` |
| `artistName` / `sellerName` | Developer/seller | "Spotify" |
| `artistId` | Developer ID (for catalog lookup) | 324684583 |
| `artworkUrl60/100/512` | App icon (multiple sizes) | mzstatic.com URL |
| `genres` | Category list | ["Music", "Entertainment"] |
| `price` / `formattedPrice` | App price | 0.0 / "Free" |
| `trackViewUrl` | App Store web link | itunes.apple.com link |
| `version` / `currentVersionReleaseDate` | Update metadata | |

### Search attributes (for software entity)

- `softwareDeveloper` — search by developer name specifically
  (`attribute=softwareDeveloper`)
- Default search does typo-tolerance server-side (searching "spottify"
  returns the real Spotify first)

### Rate limit: ~20 calls/minute

Per Apple docs. For heavier usage they suggest the Enterprise Partner Feed
(EPF). At 20/min × 200 results = ~5.76M records/day theoretically reachable —
sufficient for monitoring, NOT for full-store crawling.

**Source:** https://performance-partners.apple.com/search-api

### facundoolano/app-store-scraper (community library)

Same author as the Google Play scraper. 1,395 stars, JavaScript/Node.js, MIT.
Scrapes the iTunes App Store beyond what the public API exposes.
https://github.com/facundoolano/app-store-scraper

---

## Google Play — scraping ONLY (no official search API)

### The asymmetry

The **Google Play Developer API** (`developers.google.com/android-publisher`)
is for *publishing and managing your own apps* (uploads, in-app purchases,
reviews, subscriptions). There is **no public search-by-name or
search-by-developer endpoint**. Google Play search must be scraped.

### google-play-scraper (two maintained libraries)

| Library | Language | Stars | Last push | License |
|---------|----------|-------|-----------|---------|
| `facundoolano/google-play-scraper` | Node.js | 2,920 | 2026-07-18 | MIT |
| `JoMingyu/google-play-scraper` | Python | 998 | 2024-08-05 | MIT |

### Python usage (verified 2026-07-25)

```bash
pip install google-play-scraper
```

```python
from google_play_scraper import search, app

# Search apps by keyword (returns ranked results)
results = search('spotify', n_hits=5, lang='en', country='us')
for r in results:
    print(f"{r['title']} | appId={r.get('appId')} | dev={r['developer']}")

# App detail by appId (package name)
d = app('com.spotify.music', lang='en', country='us')
# Returns: title, developer, developerId, genre, price, free, score,
#          installs (bucketed: "1,000,000,000+"), released, updated, etc.
```

### Key fields (Python library)

| Field | Use | Example |
|-------|-----|---------|
| `appId` | Package name | `com.spotify.music` |
| `title` | App display name | "Spotify: Music and Podcasts" |
| `developer` / `developerId` | Developer name + ID | "Spotify AB" / "Spotify+AB" |
| `genre` | Primary category | "Music & Audio" |
| `installs` | Install bucket | "1,000,000,000+" |
| `score` | Aggregate rating | 4.34 |
| `free` / `price` | Pricing | True / 0 |
| `released` / `updated` | Date metadata | |

### Risk

Google Play scraping relies on **undocumented internal endpoints**. Google can
change them or rate-limit/block at any time. The Node.js library
(facundoolano) was last pushed 2026-07-18 (active maintenance). Monitor for
breakage; consider residential proxies if blocked.

---

## Impersonation-detection techniques (for clone/impersonation ventures)

### Fuzzy name matching — RapidFuzz

```bash
pip install rapidfuzz
```

```python
from rapidfuzz import fuzz
legit = 'Spotify: Music and Podcasts'
# fuzz.ratio, fuzz.partial_ratio, fuzz.token_sort_ratio
# Impersonator "Spotify Music Player Pro" → 70.6 ratio (flag)
# Competitor "Apple Music" → 36.8 ratio (safe)
```

**Threshold heuristic:** flag candidates with `partial_ratio > 60` AND
containing the brand token. RapidFuzz is C++-backed (10-100x faster than
fuzzywuzz).

### Icon similarity — imagehash (perceptual hashing)

```bash
pip install imagehash
```

```python
from imagehash import phash
from PIL import Image
h = phash(Image.open('icon.jpg'))   # e.g. d5ff5ac2616834e0
# Compare two icons via Hamming distance:
#   distance = phash(img1) - phash(img2)
#   <5 = near-identical, <10 = likely related, >15 = different
```

Available algorithms: `phash` (perceptual, best general), `dhash` (difference),
`average_hash`, `whash` (wavelet). For AI-modified/recolored icons, escalate
to CLIP embeddings (semantic similarity).

### Web search monitoring (fake download sites)

For catching fake download sites beyond app stores, monitor SERPs for
`"download <app name>"`, `"<app name> apk"`. Use:
- **SerpAPI / Serper.dev / Bright Data** — commercial, $50–$250/mo
- **Bing Web Search API** — $3/1,000 transactions
- **Google Custom Search JSON API** — free 100/day, $5/1K after
- Discover vendor URLs via the DuckDuckGo HTML endpoint
  (see `references/duckduckgo-html-search.md`)

---

## Market-sizing data points (verified 2026-07-25)

| Metric | Value | Source |
|--------|-------|--------|
| Apple App Store apps worldwide | ~1.8M–2M | apple.com/app-store ("Nearly 2M apps") |
| Apple storefronts | 175 | apple.com/app-store |
| App submissions rejected in 2024 | 1.9M+ | apple.com/app-store |
| Apps reviewed per week | 130K+ (by ~500 reviewers) | apple.com/app-store |
| Apps distributed daily | 5B+ | apple.com/app-store |
| Google Play apps | ~2.7M–3.5M (est.) | Statista |

### GitHub repo counts (app ecosystem proxy, API queries 2026-07-25)

| Query | Count |
|-------|-------|
| `topic:ios-app` | 7,439 |
| `topic:android-app` | 16,016 |
| `topic:flutter` | 76,417 |
| `topic:react-native` | 59,196 |
| `ios app in:readme` | 1,539,356 (broad/noisy) |
| `android app in:readme` | 2,504,164 (broad/noisy) |
| `swift ios language:swift` | 60,759 |
| `kotlin android language:kotlin` | 88,910 |

**Interpretation:** ~23K explicitly-tagged app projects (ios-app + android-app
topics); realistically 30K–100K OSS projects with *shipped* apps.

### TAM derivation pattern (bottom-up)

```
Total apps (~4.5M) ÷ avg apps/developer (~3) = ~1.5M unique publishers
× % indie/SMB (~70%) = ~1M indie/SMB publishers
× willingness-to-pay (2–5%) = 20K–50K potential paying customers
```
