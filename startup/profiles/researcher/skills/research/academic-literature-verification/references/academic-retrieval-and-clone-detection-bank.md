# Academic Retrieval Ladder + Clone-Detection Knowledge Bank

Two parts: (A) the condensed retrieval-ladder cheat sheet with worked examples, (B) a distilled knowledge bank of software-engineering clone-detection facts grounded in primary papers. Read this on any clone-detection, algorithm-complexity, or paper-citation task. **Re-verify live before citing any specific number** — these are session-distilled, not live-fetched.

---

## Part A — Retrieval-ladder cheat sheet (worked examples)

Climb R1→R6 until you have full text on disk. Do NOT start at `doi.org` / ScienceDirect / IEEE (they 403/429/bot-wall automated access).

| R# | Source | Open? | Best for | Access |
|----|--------|-------|----------|--------|
| R1 | arXiv | ✅ | ML/systems papers; preprints | `arxiv.org/pdf/<id>` via curl |
| R2 | University / author tech reports | ✅ | **Surveys** (often full-text identical to published) | `research.<univ>.edu/TechReports/Reports/<year>-<num>.pdf` |
| R3 | HAL / national open archives | ✅ (bot-walled for curl) | French/EU CS papers | **browser**, not curl — click PDF on landing page |
| R4 | DBLP API | ✅ (reliable) | Citation metadata, DOI discovery, confirm paper exists | `dblp.org/search/publ/api?q=...&format=json`; download-to-file-then-parse; serialize (4 parallel → 429/timeout) |
| R5 | Tool/benchmark GitHub repo | ✅ | Tools, benchmarks, algorithm description + BibTeX | browser-render README |
| R6 | Wikipedia | ✅ | Textbook algorithm facts (complexity, definitions) | curl + strip tags; cross-check primary for precision |
| R7 | Semantic Scholar API | ⚠ rate-limited | Abstracts/IDs only | expect 429; prefer DBLP (R4) |

### Worked examples from the 2026-07 clone-detection session

**Roy & Cordy 2007 survey (full text):** ScienceDirect 403'd. Queen's University TR mirror worked: `curl -sL "https://research.cs.queensu.ca/TechReports/Reports/2007-541.pdf" -o roycordy.pdf` → 577 KB real PDF → `pdftotext` → 307 KB text. Type-1/2/3/4 definitions in §7.2, exact-hash fragility quote in §10.1.2. **This is the canonical move for surveys.**

**GumTree (Falleri 2014):** HAL `curl` returned a bot-wall HTML page; the browser would have worked (didn't need to). GitHub README (`github.com/GumTreeDiff/gumtree`) carried the BibTeX + a 2024 ICSE scalability follow-up DOI — enough to confirm citation + algorithm description. DBLP confirmed the exact title/venue.

**MinHash complexity:** Wikipedia (`en.wikipedia.org/wiki/MinHash`) rendered cleanly; extracted "expected error O(1/√k), estimator O(k), ~400 hashes → ε≈5%" verbatim.

**Bellon/BigCloneBench result tables:** IEEE Xplore, Semantic Scholar, Springer all bot-walled/429. DBLP confirmed the papers exist with exact metadata. The repos (BigCloneBench, BigCloneEval) confirmed the benchmark + eval framework. **The specific per-type recall %s were NOT independently re-fetched** — labeled honestly in the deliverable rather than fabricated.

### The PDF-download checklist
```bash
curl -sL -A "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36" -o /tmp/p.pdf "<url>"
file /tmp/p.pdf          # MUST output "PDF document" — a 10-15 KB "HTML document" = bot-wall page
pdftotext /tmp/p.pdf /tmp/p.txt
search_files pattern "Type I Clones" path /tmp/p.txt   # find the section
```

### Download-to-file, never pipe-to-interpreter
```bash
# WRONG (shell guard blocks it, rightly):
curl -sL "https://dblp.org/search/publ/api?q=...&format=json" | python3 -c "..."

# RIGHT:
curl -sL "https://dblp.org/search/publ/api?q=...&format=json" -o /tmp/dblp.json
python3 -c "import json; d=json.load(open('/tmp/dblp.json')); ..."
```

---

## Part B — Clone-detection knowledge bank (software-engineering domain)

Distilled from Roy & Cordy 2007 (full text retrieved), Bellon et al. 2007, and the named algorithm papers. Re-verify live before citing exact numbers.

### B1. Clone taxonomy — Bellon / Roy & Cordy Type-1/2/3/4

Originated with **Bellon et al. 2007** ("Comparison and Evaluation of Clone Detection Tools," *IEEE TSE* 33(9), doi:10.1109/TSE.2007.70731), codified by **Roy & Cordy 2007** ("A Survey on Software Clone Detection Research," Queen's U TR 2007-541 / *Science of Computer Programming*, doi:10.1016/j.scico.2007.01.003), §7.2. Verbatim definitions:

- **Type I:** "Identical code fragments except for variations in whitespace (may be also variations in layout) and comments."
- **Type II:** "Structurally/syntactically identical fragments except for variations in identifiers, literals, types, layout and comments."
- **Type III:** "Copied fragments with further modifications. Statements can be changed, added or removed in addition to variations in identifiers, literals, types, layout and comments."
- **Type IV:** "Two or more code fragments that perform the same computation but implemented through different syntactic variants." (semantic clones)

### B2. Mapping "AI near-duplicate" patterns to clone types

| Pattern | Type | Catchable by exact normalized hash? |
|--------|------|-------------------------------------|
| renamed variable | Type-2 | ✅ if identifiers normalized → placeholder |
| different literal value | Type-2 | ✅ if literals → sentinel |
| whitespace/comments/layout | Type-1 | ✅ trivially |
| **extra guard clause / added statement** | **Type-3** | ❌ NO — adds a token, breaks the sequence |
| **reordered statements** | **Type-3** | ❌ NO — order changed |
| slightly reordered + renamed | **Type-3** | ❌ NO — reorder dominates |

**Key:** identifier/literal normalization can collapse Type-2 → Type-1 (so one hash catches it). Normalization **cannot** rescue Type-3 — an added/reordered statement changes the token sequence itself. This is the Type-2/Type-3 boundary, a definitional ceiling, not a tuning problem.

### B3. Exact-hash recall ceiling (the decisive qualitative finding)

**Primary-source quote** — Roy & Cordy 2007, §10.1.2 (Token-based Techniques), on CCFinder & Dup:
> "Due to sequential analysis in CCFinder and Dup, they are generally **fragile to statement reordering and code insertion**. A reordered or inserted statement can break a token sequence which may otherwise be regarded as duplicate to another sequence."

**Implication:** Exact normalized hashing reliably catches Type-1 and (with complete normalization) Type-2. It **structurally cannot catch Type-3** — by construction, recall on the Type-3 pattern is ~0%. This is not contested; it follows from the taxonomy definition. Normalization promotes Type-2→Type-1 but cannot rescue Type-3.

### B4. Near-duplicate techniques — complexity & feasibility (one diff fn vs N≈1000 repo fns)

| Technique | Per-pair cost | One-vs-N cost | Catches Type-3? | v1-fit |
|-----------|---------------|---------------|-----------------|--------|
| Exact body hash (Tier 1) | O(1) lookup | O(N) | ❌ | ✅ baseline |
| **Zhang-Shasha TED** | **O(n²m²)** time, O(nm) space | O(N·n²m²) — infeasible | ✅ | ❌ |
| GumTree (Falleri 2014) | ~O(n+m) (greedy heuristic) | needs a pre-filter (it's a differencer, not a retriever) | ✅ | ⚠ Phase-2 only |
| Subtree hashing / CloneDR | O(n) to hash all subtrees | O(N·\|shingles\|) | partial (no reorder) | ✅ alt |
| **MinHash over token shingles** | **O(k')** | **O(N·k') ≈ 100K ops, sub-ms** | ✅ | ✅ **recommended** |
| Deckard LSH (Jiang 2007) | near-O(S) bucketing | near-O(S) | ✅ | ⚠ overkill at N≈1000 |

**Citations (all DBLP-confirmed):**
- **Zhang & Shasha 1989** — "Simple Fast Algorithms for the Editing Distance Between Trees and Related Problems," *SIAM J. Computing* 18(6), doi:10.1137/0218082. Tree edit distance, O(n²m²) worst case. ❌ infeasible for one-vs-N retrieval.
- **Falleri et al. 2014** — "Fine-grained and accurate source code differencing," *ASE 2014*, pp. 313–324, doi:10.1145/2642937.2642982. GumTree. Greedy top-down (subtree-hash match) + bottom-up. A *differencer*, not a retriever. Scalability follow-up: Falleri & Martinez, ICSE 2024, doi:10.1145/3597503.3639148.
- **Baxter et al. 1998** — "CloneDR Using Clone Detection," *ICSM 1998*. Subtree hashing via characterization metrics (described in Roy & Cordy §10.1.3).
- **Broder 1997** — "On the Resemblance and Containment of Documents," *SEQUENCES 1997*, doi:10.1109/SEQUN.1997.666900. MinHash; Jaccard estimator computed in O(k), expected error O(1/√k) — ~100 hashes → ~10% error, ~400 → ~5%.
- **Jiang et al. 2007** — "DECKARD: Scalable and Accurate Tree-Based Detection of Code Clones," *ICSE 2007*, doi:10.1109/ICSE.2007.30. LSH over AST characteristic vectors. Win is at millions-of-subtrees scale; overkill at N≈1000.

### B5. The decision-relevant tradeoff for a latency-constrained clone detector

For a service comparing one diff function against N≈1000 repo functions inside a sub-60s budget, no persistent index:
- **Exact-hash-only is NOT viable** if the target pattern is Type-3 (added guard, reorder) — recall is ~0% by construction.
- **Two-tier design** is the answer: Tier-1 normalized body-hash (Type-1/2, O(1)) + **Tier-2 token-shingle MinHash** (Type-3, O(N·k')≈100K ops). MinHash is order-tolerant to small edits — an inserted statement changes ~k shingles; Jaccard drop is ~k/T, small for large functions, so a near-dup still scores high (e.g. Jaccard ≥0.8).
- **Per-changeset binary evaluation** materially relaxes the per-function recall bar: recall 60% per-changeset needs per-function recall r ≪ 60% when a changeset has M≥2 diff functions (per-changeset recall ≈ 1−(1−r)^M). So the MinHash tier needs to catch only *obvious* 85–95%-similar near-dups, not be a high-recall Type-3 engine.
- **Defer to Phase 2+:** GumTree (if you want to render a diff in a comment), Deckard/LSH (only if scale grows past ~10⁴ functions), full TED (never for retrieval).

### B6. Benchmarks (the instruments, not the numbers)

- **Bellon benchmark (2007):** 6 tools vs hand-validated reference. Headline: text/token tools high recall on Type-1/2, lower on Type-3; AST/metric tools trade precision for Type-3 coverage.
- **BigCloneBench / BigCloneEval (Svajlenko & Roy, 2015–2016):** modern large-scale benchmark, ~8M clones across severity bands (VST3, ST3, MT3, WT3). Repos: `github.com/clonebench/BigCloneBench`, `github.com/jeffsvajlenko/BigCloneEval`. Consistent finding: token-hash tools collapse on MT3/WT3 (single/low-double-digit % recall) while staying ~90%+ on Type-1/strong-Type-2. **⚠ Java-only — no TS/JS equivalent benchmark exists (architect-judgment gap).**

⚠ **Honesty note:** the *specific* per-tool, per-type recall percentages were not independently re-fetched in the source session (publisher bot-walls). The qualitative finding (exact-hash misses Type-3) is primary-sourced verbatim from Roy & Cordy. Re-verify exact %s against the benchmark before quoting figures in an ADR.
