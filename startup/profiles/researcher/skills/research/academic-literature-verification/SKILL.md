---
name: academic-literature-verification
description: "Find, retrieve, and cite primary-source academic literature — papers, surveys, benchmarks, algorithm descriptions — when the authoritative answer lives in a peer-reviewed paper rather than vendor docs or source code. Use when the ask is 'cite the primary source for X', 'what does the seminal paper on Y say', 'find the original definition of clone Type-1/2/3', 'what is the complexity of algorithm Z (cite the paper)', 'which benchmark measures this', or fact-checking an ADR/spec claim against the research literature. Carries the retrieval ladder that defeats paywalls and bot-walls (university mirrors, DBLP API, arXiv, GitHub repos) and a distilled knowledge bank of CS-software-engineering facts (clone taxonomy, algorithm complexities) so you don't re-derive each session. Sibling to docs-verification (vendor docs), source-code-verification (code), library-state-verification (package metadata), and performance-verification (your own measurement); load THIS when the source of truth is a paper."
---

# Academic literature verification

Retrieve and cite primary-source academic literature. The authority here is the **published paper** (conference/journal proceedings, technical report, arXiv preprint) — not a blog summary of it, not a textbook paraphrase, not the paper's abstract alone. Every claim you report must trace to a named paper with a retrieval path (DOI, URL, or arXiv ID) and an exact quoted phrase.

The hard part of this class of task is **not** reading the paper — it's *getting the paper*. Most CS publishers (IEEE, Elsevier/ScienceDirect, ACM, Springer) paywall the full text and/or bot-wall automated access; the open mirrors are scattered and the discovery routes (Google Scholar, Semantic Scholar) are themselves heavily rate-limited. This skill's core value is the **retrieval ladder** in §1, which gets you a full-text PDF or text for ~80% of cited papers without any subscription.

## When to load

- "Cite the primary source for [the clone taxonomy / algorithm X's complexity / the BigCloneBench benchmark]."
- "What does the seminal [Roy & Cordy / Zhang-Shasha / Broder] paper say about Y?"
- "Find the original definition of [Type-1/2/3 clones / tree edit distance / MinHash]."
- "Which benchmark measures [clone-detection recall by type]?"
- "Cite a paper that [measured recall of exact-hash vs near-duplicate detection]."
- "What's the complexity of [Zhang-Shasha / Deckard LSH], and cite the source."
- Fact-checking an ADR/spec/decision claim whose evidence is a research paper.
- Any "from primary sources" / "cite the paper" / "quote the survey" request where the source is academic.

If the claim is about **what vendor docs guarantee**, load `docs-verification`. If it's about **how code is implemented**, load `source-code-verification`. If it's about **library maintenance status**, load `library-state-verification`. This skill is for the case where the authority is the **research paper itself**.

## The retrieval ladder (in order — climb until you have full text)

This is the core of the skill. A direct `curl` to `doi.org`/`sciencedirect.com`/`ieeexplore.ieee.org`/`link.springer.com` will almost always return a 403/429/bot-wall or a paywall. Do not start there. Climb the ladder:

### R1. arXiv (open preprints, fastest)
Many CS papers have an arXiv version identical or near-identical to the published version.
- Find: `https://arxiv.org/abs/<id>` (use arxiv skill or search arxiv.org).
- Full text PDF: `https://arxiv.org/pdf/<id>` or click "View PDF" on the abstract page.
- Caveat: arXiv is the *preprint*. Section/figure numbering can differ from the camera-ready; fine for facts, double-check exact page numbers for a verbatim quote in the final version if precision matters.

### R2. University / author-hosted technical reports (open, often the full survey)
Surveys especially are published as open technical reports at the authors' university. This is a high-leverage move — these are the *same paper*, free, full-text.
- Pattern: `https://research.<univ>.edu/TechReports/Reports/<year>-<num>.pdf` (e.g. Queen's University `research.cs.queensu.ca/TechReports/Reports/2007-541.pdf` = Roy & Cordy 2007 survey, full text).
- Author homepage / lab page often hosts a "publications" PDF link.
- Search the author's name + "technical report" + the paper's year.

### R3. HAL / institutional open archives (open, but bot-walled for curl)
HAL (France), other national open archives. **Render in the browser** — `curl` gets a bot-wall HTML page; `browser_navigate` to the HAL landing page then click "PDF" downloads the real file.
- HAL landing: `https://hal.science/hal-<id>` → follow the PDF link in the browser.
- These are legitimate open-access copies; the wall is anti-bot, not paywall.

### R4. The DBLP API (NO rate-limit problem, use it for citation metadata + discovery)
**This is the most reliable programmatic access for CS papers.** Unlike Semantic Scholar and Google Scholar, DBLP's API does not aggressively rate-limit. Use it to:
- **Confirm a paper exists** with exact title, venue, year, DOI (cite-metadata verification).
- **Find the DOI** when you only have a title/author (then try R1–R3 with the DOI).
- **Discover related papers** in a subfield.
- Query: `https://dblp.org/search/publ/api?q=<query>&format=json&h=<N>`. Parse the JSON `result.hits.hit[].info` for `{title, year, venue, doi}`.
- **Download-to-file-then-parse** — do NOT pipe `curl` into an interpreter (the shell safety guard blocks it, and rightly so):
  ```
  curl -sL "https://dblp.org/search/publ/api?q=..." -o /tmp/dblp.json
  ```
  then `python3` reading `/tmp/dblp.json` from disk. DBLP *can* time out under burst load (4 parallel calls once 429'd in one session) — if you get curl exit 28 / HTTP 000, back off and serialize.

### R5. The tool/benchmark's own GitHub repo (open, authoritative for tools+benchmarks)
For clone-detection / ML / systems **tools** and **benchmarks**, the canonical reference is often the repo README + the paper. The repo is open and browser-renderable even when the paper PDF is walled.
- Benchmark repos: `github.com/<org>/<benchmark>` — README lists the publications and the evaluation methodology.
- Tool repos: README cites the paper (BibTeX) and documents the algorithm + complexity.
- Example: GumTree's README carries the Falleri 2014 BibTeX + a 2024 ICSE scalability follow-up DOI; BigCloneBench + BigCloneEval repos document the per-type recall methodology.

### R6. Wikipedia (open, for well-established algorithm facts/complexity)
For **textbook-level algorithm facts** (MinHash error bound O(1/√k), tree edit distance definition), Wikipedia is acceptable AND its complexity/definition statements are stable and citable. Always cross-check a complexity claim against the primary paper (R1–R4) when precision matters, but Wikipedia is a valid R6 floor.
- Fetch: `curl -sL "https://en.wikipedia.org/wiki/<Topic>" -o /tmp/x.html` then strip tags locally.

### R7. Semantic Scholar API (use sparingly — rate-limited)
`api.semanticscholar.org/graph/v1/paper/...` returns title/abstract/externalIds. **Expect 429 "Too Many Requests" on even light use.** Treat as a fallback for abstracts/IDs only, not a workhorse. Prefer DBLP (R4) for metadata.

### Extracting text from the PDF you retrieved
Once you have a real PDF (verify `file <x>.pdf` says "PDF document" AND the size is sane — a 9–12 KB "PDF" that `file` reports as "HTML document" is a bot-wall landing page, not the paper):
```
curl -sL -A "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36" -o /tmp/paper.pdf "<mirror-url>"
file /tmp/paper.pdf          # MUST say "PDF document"
pdftotext /tmp/paper.pdf /tmp/paper.txt
```
Then `search_files` the `.txt` for the section/term you need (e.g. `Type I Clones`, `complexity`, `recall`). The PDF→text route gives you the *full untruncated* paper, which beats trying to find a passage in a truncated browser snapshot.

## The method (full procedure)

1. **Identify the seminal/source paper(s).** If the task names an algorithm (Zhang-Shasha, GumTree, Deckard, MinHash) or a concept (clone Type-1/2/3, tree edit distance), the paper is usually well-known. Confirm exact title/venue/year/DOI via DBLP (R4) before you go hunting for full text.
2. **Climb the retrieval ladder (R1→R6)** until you have a full-text PDF or text artifact on disk. Prefer the university-TR mirror (R2) for surveys; arXiv (R1) for ML/systems papers; the GitHub repo (R5) for tools/benchmarks.
3. **Extract the relevant section with `pdftotext` + `search_files`** — quote verbatim. Note the section number (e.g. "Roy & Cordy 2007 §7.2.3") so the citation is locatable.
4. **Quote verbatim for definitions and complexity claims.** A taxonomy definition or an O(…) complexity is a falsifiable claim — quote it, don't paraphrase. "Type III clones are copied fragments with further modifications. Statements can be changed, added or removed" is the citation; "Type-3 is edited code" is not.
5. **Distinguish qualitative (primary-sourced) from quantitative (needs the table).** You can often retrieve the paper's *definitions and qualitative findings* as verbatim quotes. The *specific experimental numbers* (e.g. "tool X gets Y% recall on benchmark Z") live in result tables that you may not reach — label these honestly: "the paper reports this; the specific percentage was not independently re-fetched this run." Never invent a percentage.
6. **Report a citation scorecard.** For each claim: the paper (authors, year, venue, DOI/URL) + the verbatim quote + the retrieval path used (so a reviewer can re-find it). Flag any claim where you have the qualitative finding but not the quantitative table.

## Pitfalls

- **Opening with a Google/Scholar search.** Google serves a `google.com/sorry` CAPTCHA to automated IPs; DuckDuckGo returns a 202 JS challenge; Bing renders but yields empty JS shells for academic queries. Go **direct to a known source** (arXiv, the author's university, DBLP) rather than searching.
- **Treating a 403 from ScienceDirect/IEEE as "paper unavailable."** It's a paywall/bot-wall, not absence. Climb the ladder — the same paper is almost certainly on an open mirror (university TR, arXiv, HAL, author homepage).
- **Citing the abstract as if it were the paper's finding.** Abstracts are summary/marketing, not evidence. If you only reached the abstract page, say so — don't quote the abstract as the paper's result.
- **Piping `curl` into `python3`/`grep`.** The shell safety guard blocks this ("Pipe to interpreter"). Always **download-to-file-then-process** (`curl -o /tmp/x.json` then read the file). This is also more robust against transient network failures.
- **A "PDF" that's actually a bot-wall HTML page.** After download, run `file <name>.pdf`. If it says "HTML document" or the size is ~10–15 KB, you got the anti-bot landing page, not the paper. Re-try via the browser (R3) or a different mirror.
- **DBLP burst timeouts.** DBLP is reliable but will curl-timeout (exit 28, HTTP 000) if you fire 4+ parallel queries. Serialize DBLP calls or add a small backoff.
- **Paraphrasing a definition.** Taxonomy definitions, algorithm complexity bounds, and benchmark structure are the falsifiable core. Quote them verbatim with the section number. Paraphrase only in your summary scorecard.
- **Asserting a number you didn't fetch.** If the paper's result table was behind a wall, do NOT fill in a plausible percentage. Say "the paper reports [qualitative]; the specific X% was not re-fetched." Fabricated numbers are the cardinal sin of literature citation.
- **Confusing a tool's repo README with the paper.** The README is authoritative for *tool usage and algorithm description* but not for *experimental results* — those are in the paper. Cite the paper for numbers, the repo for the implementation contract.
- **arXiv preprint vs camera-ready.** For facts, fine. For an exact page number or figure, the camera-ready (publisher) version may differ — note which version you cited.

## Verification (self-check before reporting)

- [ ] Is every definition/complexity claim backed by a **verbatim quote** + paper citation (authors, year, venue, DOI/URL) + section number?
- [ ] Did I climb the retrieval ladder rather than giving up at the first paywall?
- [ ] Did I `file`-check every downloaded PDF (not a 10 KB bot-wall HTML)?
- [ ] Did I distinguish **qualitative findings** (primary-sourced, verbatim) from **quantitative tables** (label honestly if not fetched)?
- [ ] Did I confirm the paper's metadata (title/venue/year/DOI) via DBLP, not just assume?
- [ ] Is every citation locatable by a reviewer (retrieval path noted)?

## Output shape

A findings file (Markdown): per-question verdict with the verbatim quote, the full citation (authors, year, venue, DOI/URL, section), and the retrieval path used; a "Sources" list at the end with every paper's DOI/URL; an honesty-flag section naming any quantitative claims not independently re-fetched. For a kanban council, post a condensed `[swarm:evidence]` scorecard to the blackboard as a comment so downstream workers inherit the citations.

## Related skills

- `docs-verification` — sibling. Load THAT when the authority is vendor docs (Cloudflare/AWS/nginx). This skill is the paper-as-authority analog with a paper-specific retrieval ladder.
- `source-code-verification`, `library-state-verification` — siblings for code and package-metadata respectively.
- `performance-verification` — sibling for claims settled by your own measurement rather than a citation.
- `arxiv` — use it for R1 (arXiv search) when you need to *find* an arXiv ID.
- `research` (mattpocock) — the general research umbrella; this skill specializes its "primary sources" step for the academic-literature case.

## Reference

- `references/academic-retrieval-and-clone-detection-bank.md` — (1) the condensed retrieval-ladder cheat sheet with concrete worked examples (Roy & Cordy via Queen's TR, GumTree via GitHub README + DBLP, MinHash via Wikipedia), and (2) a distilled knowledge bank of software-engineering clone-detection facts grounded in primary papers: the Bellon/Roy-Cordy Type-1/2/3/4 taxonomy (verbatim definitions + which "AI near-duplicate" patterns fall into which type), exact-hash recall ceiling (Type-1/2 caught, Type-3 structurally missed — with the Roy & Cordy §10.1.2 fragility quote), and complexity/feasibility of near-duplicate techniques (Zhang-Shasha O(n²m²), GumTree, subtree hashing, MinHash O(N·k') error O(1/√k), Deckard/LSH) for one-vs-N retrieval. Read this on any clone-detection or algorithm-complexity task; re-verify live before citing.
