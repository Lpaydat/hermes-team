# Demand Validation & Competitive Intelligence Research Pattern

How to research whether a product pain point is real, widespread, and
already being solved — using only the alternative-search toolkit
(HN Algolia, DuckDuckGo via jina.ai, GitHub API).

## When to Use This Pattern

- Validating a venture/product idea: "does this pain exist?"
- Competitive landscape scanning: "who already solves this?"
- Market sizing via demand signals (forum posts, tool launches, search
  result density)

## The 4-Channel Search Strategy

Run these in parallel (batch into one turn). Each channel catches
different signal types:

### Channel 1: Hacker News (Algolia API)

Search both stories AND comments — they surface different things:

```bash
# Stories (Show HN, Ask HN, Launch HN) — finds product launches, pain-point discussions
curl -sL "https://hn.algolia.com/api/v1/search?query={pain+keywords}&tags=story&hitsPerPage=10"

# Comments — finds raw complaints, opinions, tool recommendations
curl -sL "https://hn.algolia.com/api/v1/search?query={pain+keywords}&tags=comment&hitsPerPage=10"
```

Signal types: Show HN posts (people building solutions = demand proof),
Ask HN threads (people describing pain), comment complaints.

Tip: Use multiple query phrasings — the exact words matter. Try both
the activity ("reviewing PRs") and the outcome ("situational awareness")
framings.

### Channel 2: DuckDuckGo via jina.ai (Blog/Forum Discovery)

```bash
curl -sL "https://r.jina.ai/https://duckduckgo.com/html/?q={pain+keywords}"
```

Signal types: Blog posts from EM-focused sites (dev.to, Medium,
Substack), product pages (SaaS tools solving the problem), listicles
("best tools for X").

Tip: For Reddit content, use `site:reddit.com` in the query — Reddit's
own JSON API is blocked (see SKILL.md pitfall).

### Channel 3: GitHub API (Competitive Tool Landscape)

```bash
# Find repos that solve the problem — sort by stars for signal
curl -sL "https://api.github.com/search/repositories?q={tool+keywords}&sort=stars&per_page=10" \
  | python3 -c "import sys,json; [print(f'{r[\"full_name\"]} ⭐{r[\"stargazers_count\"]} - {r.get(\"description\",\"\")[:80]}') for r in json.load(sys.stdin).get('items',[])]"
```

Signal types: Open-source tools (star count = demand proxy), CLI tools
(growing niche), abandoned projects (market tested but failed).

Tip: Check creation dates. Many 2025-2026 repos in a space = hot
emerging market. Many repos from 2014-2018 with no recent updates =
stale market or solved problem.

### Channel 4: Full Content Extraction (Deep Reads)

Once search surfaces promising URLs, read them in full:

```bash
curl -sL "https://r.jina.ai/https://{article-url}"
```

Extract verbatim quotes with URLs — these are your evidence. A blog
post from someone in the target persona describing the pain in their
own words is the strongest demand signal.

## Evidence Quality Framework

Rate each piece of evidence:

| Signal Strength | What It Looks Like | Example |
|----------------|-------------------|---------|
| **Strong** | Target persona describing pain in their own words, with quantification | EM blog: "I spend 2hrs/month per engineer reviewing PRs" |
| **Medium** | Entrepreneur building a solution (implies they see demand) | Show HN post for a tool solving the exact problem |
| **Weak** | General industry discussion, vendor content, listicles | "Top 10 tools for engineering managers" |
| **Counter-signal** | Evidence the pain is NOT widespread | No viral threads, consensus that the activity "isn't the manager's job" |

## Competitive Density Assessment

Count existing solutions by category:

- **Direct competitors** (same exact problem, same persona): How many?
  When were they launched? Are they growing?
- **Adjacent tools** (solve part of the problem): Enterprise platforms
  (LinearB, Jellyfish) that include this feature as one of many.
- **CLI/open-source** alternatives: GitHub repos with star counts.

If 5+ purpose-built tools launched in the last 12-18 months, the
market is already being served. The "no tool exists" claim is almost
certainly false — search harder before claiming novelty.

## Red Flags in Idea Briefs

Watch for these claims that demand validation can refute:

- "No purpose-built tool exists" — almost always false. Search GitHub
  and DuckDuckGo thoroughly before accepting this.
- "Engineers spend X hours on Y" — check if X is sourced or assumed.
  If no one in the target persona has publicly quantified it, treat
  the number as speculation.
- "This is a $B market" — demand validation doesn't prove market size,
  but absence of organic complaints/search activity disproves urgency.

## Output Format

Structure the demand validation report as:

1. **Specific URLs with quotes** — verbatim evidence from target persona
2. **How widespread is the complaint?** — moderate/universal/niche
3. **Are people actively seeking solutions?** — tool launches, forum
   "how do I..." questions, Show HN posts
4. **Honest assessment** — what the evidence supports vs doesn't,
   including counter-signals and competitive density
