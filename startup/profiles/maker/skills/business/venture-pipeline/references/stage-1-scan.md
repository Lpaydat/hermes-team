# Stage 1 — Scan

Disclosed detail for the Scan stage. Reached from [SKILL.md](../SKILL.md).

Continuously ingest demand-side signals. You are looking for **real human frustration** —
complaints, unmet needs, willingness-to-pay evidence, and underserved niches.

## Primary sources (demand-side)

- **Reddit** — subreddit discussions, complaint threads, "is there a tool for…" posts, people
  describing workarounds.
- **App Store / Play Store reviews** — 1–3 star reviews on popular apps (people describing
  what's broken/missing).
- **Online communities** — specialized forums, Discord servers, Slack groups, niche subreddits.
- **Hacker News** — "Ask HN" posts, Show HN reactions, comment threads discussing pain points.
- **X/Twitter** — complaints, feature requests, "I wish there was…" posts.

## Secondary source (read-only)

- **Scout's tech/innovation signals** — new capabilities that unlock new solutions to known
  problems.

## Signal patterns — what you're hunting for

| Pattern | What it looks like | Why it matters |
|---------|--------------------|----------------|
| **Frequency** | Same complaint repeated across independent sources | Real, persistent pain |
| **Intensity** | Strong emotional language ("I hate…", "wasted hours…", "so frustrating…") | High willingness-to-pay |
| **Workaround** | People describing manual hacks, spreadsheets, or duct-taped solutions | They're already paying in time/effort |
| **Willingness-to-pay** | "I'd pay for…", existing paid solutions that are hated | Revenue path exists |
| **Underserved** | Existing solutions are old, expensive, or missing a specific capability | Gap in the market |
| **"Why now"** | New tech, regulation, or behavior shift makes this newly solvable | Timing window |

## Tools for scanning

- **`requesthunt`** — CLI that scrapes and analyzes feature requests, complaints, and
  questions across Reddit, X, GitHub, YouTube, LinkedIn, and Amazon. Generates structured
  demand research reports with representative quotes and vote counts. Primary tool for
  high-volume signal ingestion. Requires API key setup (see skill).
- **`review-mining`** — Systematic extraction of pain points, switching triggers, and
  voice-of-customer language from review platforms (G2, Capterra, Trustpilot, App Store,
  Play Store). Use when deep-diving specific competitors or categories.

## Output

A raw list of candidate signals with source URLs and quotes. No filtering yet — capture
everything.
