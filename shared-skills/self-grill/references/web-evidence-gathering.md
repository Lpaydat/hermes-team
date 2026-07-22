# Web Evidence Gathering

Sections 2 (Evidence & Signals) and 3 (Competitive Landscape) of dossiers require **real quotes, URLs, and dates — never fabricated**. Major search engines and Reddit aggressively block datacenter/headless IPs.

## Discover URLs → Brave Search

```bash
curl -s -L -A "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36" \
  "https://search.brave.com/search?q=site:reddit.com+r/smallbusiness+lead+generation+pain"
```

Google, Bing, and DuckDuckGo all return captchas from datacenter IPs — don't waste iterations.

## Extract Reddit content → .rss endpoint

```bash
curl -s -L -A "Mozilla/5.0" "https://www.reddit.com/r/smallbusiness/comments/THREAD_ID/.rss"
```

- Returns full post + comments as Atom XML
- **Pace 22-25 seconds between requests** (rate-limited)
- Entry 0 = original post, Entry 1 = AutoModerator (skip), rest = comments

## Extract HN content → Algolia API

```bash
curl -s "https://hn.algolia.com/api/v1/search?query=AI+home+service+business"
curl -s "https://hn.algolia.com/api/v1/items/48769010"
```

No rate limits. Full text: `comment_text` for comments, `story_text` for stories.

## Competitor data → Wikipedia + pricing pages

```bash
curl -s -L "https://en.wikipedia.org/wiki/Podium_(company)"
curl -s -L "https://www.gohighlevel.com/pricing"
```

Parse pricing pages for dollar amounts with regex: `\$[0-9][0-9,]*(?:\.[0-9]{2})?(?:\s*(?:/|per)\s*(?:mo|month))?`

**Pitfall:** Customer testimonials on pricing pages contain dollar amounts (e.g., "$96K additional monthly revenue"). These are NOT prices. Always verify: does the dollar amount appear in a plan name/feature column, or in a testimonial quote?

## Honesty Protocol

When you can't verify a stat live, flag it explicitly: "widely attributed to X study; could not re-verify primary URL this session." Always better than a fake citation.
