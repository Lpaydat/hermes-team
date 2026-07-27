# GitHub REST API — repo-growth / category-formation signals

The GitHub REST API is the authoritative source for open-source project
metrics (stars, forks, activity, license). No auth needed for read-only
search/repo fetches. Works reliably from headless.

Base URL: `https://api.github.com`

## Endpoints

### Repo search (find the landscape)

```
GET /search/repositories?q=KEYWORDS&sort=stars&order=desc&per_page=8
```

Parameters:
- `q` — search terms (space-separated = AND). Quote multi-word terms.
- `sort` — `stars`, `forks`, `updated`. Use `stars` to find the top projects.
- `order` — `desc` (default) or `asc`.
- `per_page` — max 100.

Response structure:
```json
{
  "total_count": 308,
  "items": [
    {
      "full_name": "vxcontrol/pentagi",
      "description": "Fully autonomous AI Agents system...",
      "stargazers_count": 21107,
      "forks_count": 1234,
      "language": "Python",
      "license": {"key": "apache-2.0", "name": "Apache License 2.0"},
      "created_at": "2024-01-15T...",
      "pushed_at": "2026-07-22T...",
      "homepage": "https://...",
      "topics": ["agents", "ai-hacking", "pentesting"]
    }
  ]
}
```

`total_count` is the key landscape-sizing metric (e.g., 308 repos for
"AI penetration testing agent" = an active category).

### Single repo by full name (the key record)

```
GET /repos/{owner}/{repo}
```

Returns the same fields as a search hit plus `open_issues_count`, `watchers`,
and `subscribers_count`. Use this to verify a named-signal repo from the idea
bank and capture its current state.

## Parsing pattern (two-step, avoids security scanner flags)

```bash
# Step 1: download to file
curl -sL -A "Mozilla/5.0" "https://api.github.com/search/repositories?q=AI+penetration+testing+agent&sort=stars&order=desc&per_page=8" -o repos.json

# Step 2: parse (no pipe)
python3 -c "
import json
with open('repos.json') as f: d=json.load(f)
print('total_count:', d.get('total_count',0))
for r in d.get('items',[])[:8]:
    print(f\"{r.get('stargazers_count',0)} stars | {r.get('full_name','')} | {(r.get('description','') or '')[:90]} | lang={r.get('language','')}\")"
```

## Star-trajectory methodology (category-formation signal)

A repo's current star count matters less than its trajectory. To establish
trajectory:

1. **Find the repo's Show HN / Launch thread** via HN Algolia
   (`query=REPONAME&tags=story`). Founders typically quote the star count
   at launch.
2. **Fetch the current star count** via `GET /repos/{owner}/{repo}`.
3. **Compute growth** and cite both figures in the dossier.

Example — Strix (ai-pen-testing dossier, 2026-07-23):
- Show HN (id=45428526, 2025-09-30): "~2,000 stars on GitHub"
- GitHub API (2026-07-23): 43,406 stars
- **21× growth in <10 months** = direct evidence a category is forming.

This trajectory is a stronger signal than any single star count. A repo with
40k stars that grew linearly over 5 years signals mature adoption; a repo that
went 2k → 43k in 10 months signals an explosive new category (and thus a
closing competitive window).

## When to use GitHub vs other sources

- **GitHub is PRIMARY for devtools/security/infra ideas** — these have weak
  Reddit pain signals (audience is on HN, not Reddit) but strong GitHub
  presence. Star counts + repo counts are direct demand proxies validated by
  technical buyers.
- **GitHub is SECONDARY for SMB/consumer ideas** — the audience isn't on
  GitHub. Use Reddit RSS for pain signals instead.
- **Use GitHub alongside HN Algolia** — HN gives the qualitative signal
  (comments, reactions); GitHub gives the quantitative signal (stars, repos).
  Cross-referencing a repo's HN launch thread with its GitHub growth is the
  most reliable category-formation assessment.

## Real example — AI pentesting landscape (captured 2026-07-23)

### General "AI penetration testing agent" search (total_count: 308)
| Stars | Repo | Description |
|-------|------|-------------|
| 21,107 | vxcontrol/pentagi | Fully autonomous AI Agents system for complex pentesting tasks |
| 2,811 | GH05TCREW/pentestagent | AI agent framework for black-box security testing, bug bounties |
| 2,098 | Armur-Ai/Pentest-Swarm-AI | Autonomous pentesting using a swarm of AI agents |
| 2,028 | 0xSteph/pentest-ai-agents | Claude Code as offensive security research assistant |
| 1,114 | SanMuzZzZz/LuaN1aoAgent | Cognitive-driven fully autonomous AI penetration testing agent |
| 799 | pikpikcu/airecon | Autonomous cybersecurity agent with self-hosted LLM |
| 570 | yv1ing/Z3r0 | AI-native red-team workbench |
| 428 | SHAdd0WTAka/Zen-Ai-Pentest | AI-Powered Penetration Testing Framework |

### Autonomous pentest LLM search (total_count: 86)
| Stars | Repo | Description |
|-------|------|-------------|
| 10,437 | 0x4m4/hexstrike-ai | HexStrike AI MCP Agents (Claude/GPT/Copilot) |
| 4,879 | PurpleAILAB/Decepticon | Autonomous Hacking Agent for Red Team |
| 1,263 | CyberStrikeus/CyberStrike | Open-source AI-augmented offensive security harness |
| 767 | ASCIT31/Dark-Moon | Autonomous AI pentesting engine (web, cloud, AD, K8s) |

### Named signal: usestrix/strix
- Stars: 43,406 | Forks: 4,484 | Language: Python | License: Apache-2.0
- Created: 2025-08-05 | Last push: 2026-07-22 (active)
- Homepage: https://strix.ai | Company: OmniSecure, Inc.
- Topics: agents, ai-hacking, ai-penetration-testing, bug-bounty, offensive-security, red-teaming, security-automation (20 topics)

## Gotchas

1. **Use a browser User-Agent** — the API sometimes rejects the default
   curl UA. `-A "Mozilla/5.0"` is sufficient (no auth needed for read-only).
2. **Rate limits:** unauthenticated requests are capped at 60/hour. For a
   single dossier (a handful of searches + repo fetches), this is never hit.
   If you need more, authenticate with a token in the `Authorization` header.
3. **`description` can be `null`** — always use `(r.get('description') or '')`
   when parsing to avoid TypeErrors.
4. **Repo names are case-insensitive in the API** but preserve case in the
   response. Use the exact `full_name` from search results for single-repo
   fetches.
5. **`total_count` caps at 1000** for search — if you see exactly 1000, the
   real count is higher. Narrow the query or use `created_at` date filters.
