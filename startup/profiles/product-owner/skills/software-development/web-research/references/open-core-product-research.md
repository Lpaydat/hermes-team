# Open-Core Product Research (CE vs EE, licensing, SDK coverage)

Domain-specific tactics for "research product X in depth" tasks where the product has a Community Edition (free/open) and an Enterprise Edition (paid/proprietary) — Neo4j, GitLab, Grafana, Supabase, SuperTokens, etc. The user typically asks: what's in CE vs EE? What's the license? Can I use it commercially? Does it support language/platform Y? Where does CE hit walls?

Complements `web-research-tactics.md` §16 (GitHub API mechanics) and `js-library-research.md` (library comparison) with the conceptual workflow that makes those calls load-bearing for open-core questions.

## 1. The official docs "features per edition" table — the primary source

Open-core vendors publish a feature comparison matrix showing what each edition includes. This is THE primary source for "what do I get in Community vs Enterprise?" — more authoritative and complete than any blog post or third-party comparison.

**Where to find it:**
- Neo4j → Operations Manual → Introduction → "Key features per edition" table (`neo4j.com/docs/operations-manual/current/introduction/`)
- GitLab → "GitLab feature comparison" (`about.gitlab.com/features/`)
- Grafana → docs or pricing "Feature comparison by Grafana edition"
- Supabase → pricing page feature matrix

**Navigation pattern:** the table is usually on the product's *introduction*, *overview*, or *pricing* page — not deep in a feature-specific chapter. Try `docs.<product>.com/introduction/`, then `/overview/`, then `/pricing/`.

**Extraction:** these tables are often wide HTML tables that the browser snapshot truncates. Use `read_file` on the truncated cache file (tactics §1) to page through the full table cell-by-cell. For very large tables, extract via `browser_console`:
```js
// browser_console, expression= — extract feature table rows with edition checkmarks
(() => {
  const rows = document.querySelectorAll('table tr');
  return [...rows].map(r => {
    const cells = [...r.querySelectorAll('td, th')].map(c => {
      const hasCheck = c.querySelector('svg, .check, [data-icon]') || /✓|✔|check/i.test(c.className);
      const text = c.textContent.trim().substring(0, 80);
      return hasCheck && !text ? '✓' : text;
    });
    return cells.join(' | ');
  }).join('\n');
})()
```
This recovers the full CE/EE/Infinigraph checkmark matrix even when the snapshot drops the cell content.

**What to extract from it:** the features CE *lacks* (empty CE column) are the upgrade triggers. Group them: scale/HA (clustering, replicas, sharding), operations (online backup, monitoring), security (RBAC, LDAP, SSO, Kerberos), performance (faster runtimes, parallel execution), multi-tenancy (multiple databases, isolation). This grouping directly maps to the "where does CE hit walls?" question.

## 2. Repo-structure analysis — determine the open-core boundary from the source tree

Before reading any docs, a 30-second check of the public repo's directory structure reveals the licensing model:

**Check for edition-segregated directories:**
- `neo4j/neo4j` has `community/` + `packaging/` but **no `enterprise/`** → Enterprise source is proprietary (binary-only distribution).
- `gitlab-org/gitlab` has `ee/app/` alongside `ee/` → EE source IS public (but under a different license).
- Many open-core repos have an `ee/` or `enterprise/` directory with a separate `ee/LICENSE.md`.

**How to check:** use the git tree API (tactics §16) or navigate to the repo root on GitHub and scan top-level directories:
```sh
curl -sL "https://api.github.com/repos/<org>/<repo>/git/trees/<branch>?recursive=1" \
  | python3 -c "
import json,sys; d=json.load(sys.stdin)
top = set()
for item in d.get('tree',[]):
    parts = item['path'].split('/')
    if len(parts) <= 2: top.add(item['path'])
print('\n'.join(sorted(top)))"
```

**What the structure tells you:**
- No `enterprise/` or `ee/` dir → **fully proprietary EE** (source not published). CE = the entire public repo.
- `ee/` dir present with same license → **open-core, dual-license** (both editions open source, EE adds features).
- `ee/` dir with different license file → **open-core with proprietary overlay** (CE is OSS, EE code is visible but commercially licensed).

This determines whether you can self-compile EE features or must buy a license. It's faster and more authoritative than reading the vendor's marketing page.

## 3. License triangulation — verify a license claim three ways

License is a load-bearing claim for "can I use this commercially?" questions. Don't trust a single source — triangulate:

1. **Raw LICENSE file** — `raw.githubusercontent.com/<org>/<repo>/<branch>/LICENSE.txt` (or `.md`). Read the first few lines: "GNU GENERAL PUBLIC LICENSE Version 3" = GPLv3; "Apache License Version 2.0" = Apache 2.0. For dual-licensed or NOASSERTION repos, see tactics §16 (License NOASSERTION fallback).
2. **GitHub sidebar badge** — the repo page shows "GPL-3.0 license", "Apache-2.0 license", etc. in the repo files navigation list. Quick confirmation but derived from SPDX detection (can be wrong for dual/custom licenses).
3. **Vendor legal page** — the vendor's own `/legal-terms/`, `/licensing/`, or `/policies/` page. This is the authoritative statement of what license applies to which edition. Neo4j's legal page explicitly lists "Neo4j Community Edition (GPL v3)" separately from the Enterprise Software Agreement.

All three agreeing = high confidence. Disagreement = investigate further (common with dual-licensed or open-core projects where the repo license and the product license differ).

## 4. GPLv3 vs AGPL — the SaaS viability filter

For "is the license a problem for commercial use?" questions, the GPL family distinction is decisive:

| License | Network/SaaS use triggers copyleft? | Embedded (same-process linking) risk? | Distribution triggers copyleft? |
|---------|:---:|:---:|:---:|
| **GPLv3** | ❌ No | ⚠️ Yes (linking) | ✅ Yes |
| **AGPLv3** | ✅ **Yes** (network-use clause) | ⚠️ Yes | ✅ Yes |
| **Apache 2.0** | ❌ No | ❌ No | ❌ No (attribution only) |

**Key insight:** GPLv3 (unlike AGPL) has **no network-use clause**. This means you can run a GPLv3 server (like Neo4j CE) as a SaaS backend without opening your application code — your app communicates over a protocol (Bolt, HTTP, gRPC) and is a separate program. This is why many open-core databases choose GPLv3, not AGPL, for their community edition.

**When AGPL is the dealbreaker:** if the product is AGPL and the user wants SaaS/cloud deployment, they typically must buy a commercial license. MongoDB, Elasticsearch (post-2021), Redis (post-SSPL) all moved to AGPL-equivalent licenses specifically to close the SaaS loophole.

**The drivers/clients are usually Apache 2.0** — even when the server is GPL/AGPL. Check the driver repos separately; they're not derivative works of the server (they communicate over a protocol). This means client-side code has no copyleft concern regardless of the server license.

## 4b. BSL (Business Source License) — the "source-available, not open source" model

Increasingly common for open-core databases and infrastructure tools (CockroachDB, Sentry, HashiCorp since 2023, Memgraph, MariaDB). BSL is a **fourth category** alongside GPL/AGPL/Apache, with materially different mechanics:

| Property | BSL 1.1 | GPLv3 | AGPLv3 | Apache 2.0 |
|----------|:---:|:---:|:---:|:---:|
| OSI-approved open source? | ❌ **No** | ✅ Yes | ✅ Yes | ✅ Yes |
| Can modify/redistribute? | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes |
| Production use? | ⚠️ **Restricted by Additional Use Grant** | ✅ Yes | ✅ Yes | ✅ Yes |
| SaaS/DBaaS hosting allowed? | ❌ **Typically no** | ✅ Yes | ❌ No (network clause) | ✅ Yes |
| OEM/embedding allowed? | ❌ **Typically no** | ⚠️ Linking | ⚠️ Linking | ✅ Yes |
| Converts to open license? | ✅ **Yes, on Change Date** | — | — | — |

**Three BSL parameters that determine everything** (they're at the top of every BSL LICENSE file):

1. **Additional Use Grant** — defines what production use is *allowed*. Typically: "internal business purposes" with exclusions for (a) embedding/distributing as a standalone product, (b) hosting as a DBaaS, (c) building a competing product. Read this section carefully — it's the actual contract.
2. **Change Date** — the date the license auto-converts to the Change License (e.g., "2030-15-07" → Apache 2.0). After this date, it becomes truly open source. For long-term projects, check how far out this is.
3. **Change License** — what it converts to (usually Apache 2.0 or GPL).

**How to identify BSL:** the LICENSE file starts with "BUSINESS SOURCE LICENSE" or "MEMGRAPH BUSINESS SOURCE LICENSE" and contains the PARAMETERS block. The license text itself states: *"The Business Source License is not an 'open source' license."* GitHub's sidebar badge may show "Other" rather than a recognized SPDX identifier.

**Research implications:**
- Don't label BSL products as "open source" in findings — say "source-available" or "BSL-licensed." This distinction matters for procurement and legal review.
- The Additional Use Grant is the load-bearing section for commercial-use questions. Quote it verbatim in findings (it's short — usually one paragraph).
- For most internal/SaaS-backend use, BSL's Additional Use Grant permits production use. The walls are OEM embedding, DBaaS resale, and competing products.
- Compare the Change Date to the project's expected lifetime. A 4-year Change Date is low risk for most projects; a 6+ year one may be a concern for long-lived infrastructure.

**Don't give legal advice.** State the license mechanics factually and recommend consulting counsel for edge cases (especially embedded/same-JVM usage of GPLv3 software in proprietary apps, which is a gray area).

## 5. SDK/driver ecosystem mapping — does it support language/platform Y?

When the user asks "does it support Rust/Python/TS/browser/WASM?", map the vendor's language coverage:

1. **List org repos** (tactics §16: `api.github.com/orgs/<org>/repos`) and filter for SDK-shaped names (`*-driver`, `*-sdk`, `*-client`, `<lang>-<product>`).
2. **For each driver repo**, capture: stars, commits, last-push date, current branch (liveness), license (usually Apache 2.0 — separate from the server).
3. **Cross-check package registries** when a repo 404s or doesn't exist:
   - `pypi.org/pypi/<name>/json` → Python package existence + version + license
   - `registry.npmjs.org/<name>` → npm package existence
   - `crates.io/api/v1/crates/<name>` → Rust crate existence

   **Resolution pattern:** a GitHub repo for `<lang>-driver` that 404s doesn't mean "no support for that language." Check the package registry for alternate naming. Neo4j has no `neo4j-rust-driver` repo, but `neo4j-rust-ext` exists on PyPI as a Rust-based performance accelerator for the Python driver. The vendor may also embed one language's performance extensions inside another's package.

4. **Browser/WASM support** — check the JS driver README for a "browser" section. Neo4j's JS driver ships a WebSocket-compatible browser build. But "browser driver support" ≠ "runs in the browser" — the database itself is still server-side. WASM builds of databases are rare (they're JVM/native binaries); state clearly what runs where.

## 6. Structuring the output profile

For "research product X in depth" tasks, the proven output structure (from a Neo4j CE research pass):

1. **CE vs EE feature comparison** — grouped by domain (scale, operations, security, performance, multi-tenancy), not a flat list. Table with checkmarks from the official comparison page.
2. **License** — exact license name + what it means for commercial use (GPL vs AGPL distinction §4).
3. **Deployment modes** — embedded vs server, which languages can embed, which must use client-server.
4. **Where CE hits walls** — the practical limits (RAM, concurrency, query runtime, backup, HA) derived from the missing-features list, not speculation.
5. **Platform/language support** — driver quality table (stars, commits, liveness, license).
6. **Commercial use verdict** — clear yes/no/conditional per deployment scenario (server, embedded, SaaS, OEM).
7. **Use-case fit** — "best choice when..." / "falls short when..." summary.

This structure answers all the user's sub-questions (scale limits, clustering, backup, license, embedded, walls, SDK quality, commercial use) in a scannable format.

## 8. Acquisition history and adoption-risk assessment

When the user asks "is it safe to choose for new projects?" — especially for a project that has been acquired, changed hands, or has uncertain stewardship — license and features are necessary but not sufficient. You need to assess **organizational risk**: who owns it now, are they committed to open source, and is the project still actively maintained? This is the layer that makes or breaks a "use or avoid" recommendation.

### Tracking ownership / acquisition history

Open-core projects change hands frequently (especially in the database/infra space). The acquisition chain materially affects risk:

1. **GitHub Discussions pinned posts** — the single best primary source for ownership announcements. Maintainers pin "we've been acquired by X" or "see this press release for details on our new owner" posts. Navigate to `github.com/<org>/<repo>/discussions` and read the pinned threads first. This is how Dgraph's Istari Digital acquisition (Oct 2025, from Hypermode, which had acquired it from Dgraph Labs) was surfaced — not from the README, docs, or any blog.

2. **The press release link** — the pinned discussion usually links to an external press release (PRNewswire, BusinessWire, company blog). Fetch and read it. It states: who acquired whom, from whom, the stated commitment to open source, and the acquirer's strategic rationale. Quote the commitment language verbatim in findings — it's the closest thing to a promise you'll get.

3. **Maintainer GitHub usernames** — check the usernames of recent committers/discussion authors. Names like `shiva-istari`, `matthewmcneely` or org affiliations reveal who the current stewards are. If the most active maintainers have the acquirer's org in their username, the acquisition has taken hold operationally.

4. **Dgraph example chain:** Dgraph Labs (original, ~2016–2023) → Hypermode (AI/ML pivot, ~2023) → Istari Digital (aerospace/defense AI infra, Oct 2025). Three owners in ~3 years is a yellow flag for long-term stewardship stability, even if each acquirer publicly committed to open source.

### Maintenance-liveness verification

Don't just trust the README's "production-ready" claim. Verify with concrete signals:

| Signal | How to check | What "alive" looks like |
|--------|-------------|------------------------|
| **Release cadence** | `CHANGELOG.md` (raw fetch) or `/releases` page | Regular releases within last 1–3 months; not just dependency bumps |
| **Security responsiveness** | CHANGELOG entries with CVE/GHSA references | Active CVE remediation = production support investment |
| **Commit recency** | Repo commits page or metadata API `pushed_at` | Commits within weeks, not years |
| **Discussion activity** | GitHub Discussions tab | Maintainers responding to user questions within days |
| **Roadmap signals** | Discussions in "Announcements" or "Ideas" category | New feature discussions (e.g. vector search, HNSW) = forward investment |

A project with a 21K-star README claiming "production-ready at Fortune 500 companies" but no releases in 18 months is effectively abandoned regardless of the claim. The CHANGELOG + Discussion cadence is the truth.

### The "managed cloud EOL" trap

Open-core database/infra projects often have (or had) a managed cloud offering. During acquisitions or strategic pivots, the cloud offering is frequently **shut down (EOL'd)** while the open-source self-hosted version continues. Dgraph Cloud was EOL'd during the Hypermode→Istari transition. Check for this:

- Search the project's discussions/forum for "cloud" + "EOL" / "migration" / "sunset" / "shutdown".
- If a managed offering existed and is gone, **self-hosting is the only deployment path** — state this explicitly in the recommendation. It changes the operational burden calculation.

### Structuring the adoption-risk recommendation

The output should be a clear **"use" / "avoid" / "conditional"** verdict with risk factors, not just a feature list. Proven structure:

1. **Verdict (one line):** "Cautious use with caveats" / "Avoid" / "Safe to choose"
2. **Use it if:** bullet list matching the project's strengths to concrete use cases (distributed graph, auto-GraphQL, specific language stacks with good SDKs)
3. **Avoid it if:** bullet list matching weaknesses to deal-breakers (no embedded mode, no WASM, missing language SDKs, ownership churn risk, no managed cloud)
4. **Risk assessment paragraph:** the open-source license as a safety net (even if the acquirer deprioritizes, the community can fork), current development velocity, and the ownership-stability concern.

The license is the ultimate risk backstop: a fully Apache 2.0 codebase (like Dgraph v25) can be forked and continued by the community even if the current owner abandons it. A BSL or proprietary license with no change-date removes that safety net and raises the risk accordingly.

## 9. Structuring the output profile
