# Competitive Landscape Research Pattern

How to systematically catalog ALL tools in a product category —
direct competitors, adjacent tools, and enterprise platforms —
with feature-level differentiation analysis.

## When to Use This Pattern

- "What existing tools already solve or overlap this?"
- Competitive landscape scan for a venture/product idea
- Differentiation analysis: "is our proposed wedge actually unique?"

## Discovery Methods (Run All of These)

### 1. GitHub Topic Pages (Broad Discovery)

Browse `https://github.com/topics/{topic}` for each relevant topic.
Topic pages surface repos that keyword search misses, sorted by stars.

Example: for a "git activity summary" product, check:
- `github.com/topics/git-statistics`
- `github.com/topics/git-analytics`
- `github.com/topics/git-activity`
- `github.com/topics/developer-productivity`

Star counts on topic pages are authoritative — no API needed.
Note which repos are abandoned (check last commit date on repo page).

### 2. GitHub Search (Targeted Discovery)

```bash
curl -sL "https://api.github.com/search/repositories?q={keywords}&sort=stars&per_page=10" \
  | python3 -c "import sys,json; [print(f'{r[\"full_name\"]} ⭐{r[\"stargazers_count\"]} - {r.get(\"description\",\"\")[:80]}') for r in json.load(sys.stdin).get('items',[])]"
```

**PITFALL: Overly specific search terms understate the landscape.**
Searching `"git standup weekly summary engineering team"` returns 4
results with 0-5 stars. Searching `"git weekly report standup"`
or just `"git standup"` surfaces the 7.8k-star tool. Start broad,
then narrow. Prior rounds of research that reported "17+ tools with
0-2 stars" were wrong because the queries were too specific.

### 3. Competitor Comparison Pages (Fastest Full-Set Discovery)

**This is the highest-signal technique.** Most SaaS tools list their
own competitors on a "Compare" or "X Alternative" page. Visit one
competitor's site, find their comparison section, and you get the
full competitive set in one click.

Example: gitmore.io's pricing page footer listed:
Geekbot, LinearB, Swarmia, Waydev, GitClear, GitDailies, GitRecap
— the entire direct + enterprise competitive set from one page.

Workflow:
1. Find ONE SaaS competitor via search
2. Look for their "Compare" / "Alternative" / "vs" pages
3. Visit each named competitor to verify and catalog

### 4. SaaS Pricing Pages (Feature + Pricing Intel)

Use `browser_navigate` directly to pricing pages. These are usually
JS-rendered but load without CAPTCHA (they're marketing pages, not
search engines). Extract:
- Pricing tiers (Free / Pro / Enterprise)
- Feature lists per tier
- AI/narrative capabilities (look for "AI-written", "AI-generated",
  "in your voice", "narrative summary")
- Integration support (GitHub, GitLab, Bitbucket, Slack, Teams)

### 5. Direct Navigation to Repo Pages (Star Verification)

Visit each repo's GitHub page directly to get:
- Exact star count and fork count
- Last commit date (is it maintained or abandoned?)
- README description and feature list
- Topic tags (which lead back to method #1)

For star counts, `browser_navigate` to the repo page and read the
sidebar — no API call needed.

## Cataloging Structure

Organize findings into tiers:

### Tier 1: CLI/Open-Source Tools
Table columns: Tool, Stars, URL, What It Does, Narrative Synthesis?
- All CLI tools produce raw stats/dashboards. NONE produce narrative.
- This validates the gap but shows CLI is a commodity space.

### Tier 2: SaaS Direct Competitors
Table columns: Tool, URL, Pricing, What It Does, Narrative Synthesis?
- The critical tier. Check each for AI/narrative capability.
- Free tier availability matters for competitive positioning.

### Tier 3: Enterprise Engineering Intelligence Platforms
Table columns: Tool, URL, Pricing, What It Does, Narrative Synthesis?
- $500-$2000+/mo, target VP Engineering/CTO buyers.
- Check for Gartner MQ positioning (Leader, Challenger, Niche Player).
- AI features are usually "bolt-on" (natural language Q&A) not
  pre-written narrative summaries.

### Tier 4: Platform Native Features
- GitHub Pulse, GitHub Insights, GitLab analytics.
- All raw data/dashboards. Never narrative synthesis.
- Risk: platform could add this feature anytime.

## Differentiation Assessment Method

For each tool, assess the specific wedge being claimed:

1. **State the proposed wedge** (e.g., "narrative synthesis",
   "question-answering format", "local-first")
2. **Check each direct competitor** for that exact capability
3. **Verdict**: Differentiated / Table Stakes / Taken

If 2+ direct competitors already ship the claimed wedge, it is NOT
differentiated — it is table stakes. Say so directly.

### Common Differentiation Claims and How to Evaluate Them

| Claim | How to Check | Red Flag |
|-------|-------------|----------|
| "Narrative synthesis" | Search competitor copy for "AI-written", "in your voice", "summary" | If 2+ SaaS competitors already do this, it's table stakes |
| "No purpose-built tool exists" | Search GitHub + DuckDuckGo thoroughly with BROAD terms | Almost always false; prior research was probably too narrow |
| "Individual contributor focus" | Check if competitors target managers vs ICs | Most tools target managers; IC focus may be genuinely narrow |
| "Local-first / CLI-first" | Check if all competitors are SaaS | CLI narrative is genuinely rare (all narrative tools are SaaS) |

## Output Format

Write a structured Markdown report with:
1. Executive summary with key finding (differentiated or not?)
2. Tier tables with all columns above
3. Differentiation assessment with explicit verdict
4. Correction of any prior research that understated the landscape
5. Methodology note (what was checked, what couldn't be accessed)

## Browser vs curl/jina.ai for This Task

| What | Best Tool | Why |
|------|----------|-----|
| GitHub repo star counts | browser_navigate to repo page | Page loads cleanly, stars in sidebar |
| GitHub topic browsing | browser_navigate | JS-rendered topic pages |
| SaaS pricing/feature pages | browser_navigate | JS-rendered marketing pages |
| Competitor comparison mining | browser_navigate | Need to read full page |
| GitHub API repo search | curl (terminal) | Structured JSON, faster |
| Blog/article deep reads | curl via jina.ai | Clean Markdown extraction |
| HN/Reddit demand signals | curl (HN Algolia, DDG+jina.ai) | APIs work without browser |

**Key lesson:** When dispatched as a kanban worker doing research,
LOAD THE web-research SKILL FIRST even if it wasn't in the card's
skills field. The skill's curl/jina.ai patterns are faster than
browser navigation for many research subtasks, and the reference
files prevent repeating prior research mistakes.
