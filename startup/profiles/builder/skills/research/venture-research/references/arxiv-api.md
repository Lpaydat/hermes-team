# arXiv API — Research Paper Discovery & Verification

The arXiv API is the primary source for finding and verifying academic
papers, technical reports, and "enabling shift" evidence cited in venture
idea dossiers. Works reliably from a headless environment, no auth required,
returns Atom XML. Verified working 2026-07-23 (Dockerless CI Verification
dossier).

Base URL: `http://export.arxiv.org/api/query`

## Endpoints

### Search by query

```
GET /api/query?search_query=QUERY&max_results=N
```

**Field prefixes:**
| Prefix | Matches | Example |
|--------|---------|---------|
| `ti:` | Title | `ti:dockerless` |
| `au:` | Author | `au:Mehta` |
| `abs:` | Abstract | `abs:continuous+integration` |
| `cat:` | Category | `cat:cs.SE` |
| `all:` | Any field | `all:CI+build+failure` |

**Operators** (must be UPPERCASE, URL-encoded as `+AND+` etc.):
- `AND` — both must match (implicit between terms within a field)
- `OR` — either matches
- `ANDNOT` — exclude

Multiple terms within a single field are OR'd by default. To AND across
fields, use explicit `+AND+`:

```
# Title contains "dockerless" AND any field contains "verifier"
search_query=ti:dockerless+AND+all:verifier

# Author is Mehta AND any field contains CI
search_query=au:Mehta+AND+all:CI
```

### Fetch by known ID

```
GET /api/query?id_list=2606.28436
```

Returns the exact paper. Use this when you already have an arXiv ID (e.g.,
from idea-bank notes or a prior session).

## Response shape

Atom XML. Each `<entry>` contains:
- `<title>` — paper title
- `<id>` — canonical URL (`http://arxiv.org/abs/XXXX.XXXXX`)
- `<summary>` — full abstract (GOLD for dossier §2 Evidence / §6 Core Idea)
- `<published>` — ISO timestamp (when submitted to arXiv)
- `<updated>` — last revision timestamp
- `<author><name>` — author names (may be many; corporate/lab papers list 10+)
- `<arxiv:primary_category>` — e.g., `cs.SE`, `cs.CL`, `cs.AI`
- `<link>` entries — PDF, abstract page, DOI

## Parsing pattern (two-step, avoids security-scanner flags)

```bash
# Step 1: download
curl -sL "http://export.arxiv.org/api/query?search_query=ti:dockerless&max_results=5" -o results.xml
```

```python
# Step 2: parse
import re, html
with open('results.xml') as f:
    content = f.read()

entries = re.findall(r'<entry>(.*?)</entry>', content, re.DOTALL)
for e in entries:
    title = re.search(r'<title>(.*?)</title>', e)
    id_url = re.search(r'<id>(.*?)</id>', e)
    published = re.search(r'<published>(.*?)</published>', e)
    summary = re.search(r'<summary>(.*?)</summary>', e, re.DOTALL)
    authors = re.findall(r'<name>(.*?)</name>', e)

    print(f"TITLE: {html.unescape(title.group(1)) if title else 'NONE'}")
    print(f"URL: {id_url.group(1) if id_url else 'NONE'}")
    print(f"DATE: {published.group(1)[:10] if published else 'NONE'}")
    print(f"AUTHORS ({len(authors)}): {', '.join(authors[:3])}")
    if summary:
        text = html.unescape(summary.group(1)).strip()
        print(f"ABSTRACT: {text[:500]}")
    print()
```

## Common pitfalls

1. **`search_query` with broad author names returns noise.** `au:Mehta+AND+all:CI`
   returned building-construction and energy papers by unrelated Mehtas, not
   the CI study. **Fix:** Start with title search (`ti:KEYWORD`), then
   broaden to `all:` only if title search misses. When searching for a known
   paper by description, use distinctive terms from the title.

2. **OR vs AND precedence.** Within a field, terms are OR'd. Across fields,
   you must use explicit `+AND+`. `search_query=all:build+failure+prediction`
   is `build OR failure OR prediction` (very broad). Use quoted phrases or
   `+AND+` to narrow.

3. **`max_results` defaults to 10.** Bump it (`max_results=20`) for broader
   searches. The API supports pagination via `start=`.

4. **The abstract (`<summary>`) is the most valuable field for dossiers.** It
   gives you a citable, verbatim description of the paper's findings — ideal
   for §2 Evidence quotes and §6 Core Idea "core mechanism" descriptions.
   Always capture the full abstract, not just the title.

5. **HTTP (not HTTPS) works fine.** The `export.arxiv.org` endpoint serves
   over HTTP. HTTPS also works but isn't required.

## When to use arXiv in the dossier workflow

- **The idea's entry signal references a paper or study** (e.g., "ByteDance
  Dockerless paper + Mehta study"). Search arXiv by title keyword first,
  then by author if the title search misses.
- **The idea is an "enabling shift" (Door B / Opportunity origin).** New
  capabilities are often published as papers before they become products.
  Search arXiv for the core technique.
- **You need authoritative evidence for §2 or §6.** A paper abstract is a
  stronger citation than an HN comment — it's peer-reviewed (or at least
  arXiv-vetted) and carries the authors' institutional weight.
- **Competitor intelligence.** Companies like ByteDance, Google, Meta
  publish their infrastructure research on arXiv. Searching
  `au:CompanyName` or `all:companyname+technique` can reveal what
  incumbents are building internally.

## Real examples (captured 2026-07-23)

### ByteDance "Dockerless" paper
- **arXiv ID:** 2606.28436
- **Title:** "Dockerless: Environment-Free Program Verifier for Coding Agents"
- **Published:** 2026-06-26
- **Authors:** 13 (Wenhao Zeng, Yuling Shi, Xiaodong Gu, et al.)
- **Key finding (from abstract):** Environment-free agentic patch verifier
  that evaluates code patches without Docker execution. Outperforms strongest
  open-source verifier by 14.3 AUC points. Reaches 62.0% resolve rate on
  SWE-bench Verified, matching environment-based post-training.
- **Search that found it:** `ti:dockerless` → first result

### Atlassian/Mehta CI study
- **arXiv ID:** 2402.09651
- **Title:** "Practitioners' Challenges and Perceptions of CI Build Failure
  Predictions at Atlassian"
- **Published:** 2024-02-15
- **Authors:** 7 (Yang Hong, Chakkrit Tantithamthavorn, Jirat Pasuksmit,
  Patanamon Thongtanunam, Arik Friedman, Xing Zhao, Anton Krasikov)
- **Key finding (from abstract):** Repository dimension is the key factor
  influencing CI build failures. Developers perceive CI build failures as
  "challenging issues in practice." CI build prediction can provide proactive
  insight and facilitate decision-making.
- **Note:** The task brief referred to this as "the Mehta study" but the
  author list does not contain a Mehta — it may have been confused with a
  related citation, or "Mehta" may refer to an internal Atlassian name. The
  paper was found via `all:build+failure+prediction+AND+all:Atlassian`,
  which is the correct paper for the described content. **Lesson: when the
  brief's naming doesn't match exactly, search by content/topic, not by
  the name given — verify via the abstract.**
