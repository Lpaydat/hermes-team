---
name: academic-citation-verification
description: "Resolve and verify claims that cite academic papers — turn a partial/remembered citation ('CCFinder (Kamiya 2002)', 'Bellon's taxonomy', 'the Deckard paper') into a canonical DOI + title + authors + venue, and confirm what the paper actually claims, without breaching paywalls. Uses the free Crossref → Semantic Scholar → open-access ladder. Sibling to docs-verification (vendor docs) and source-code-verification (source code); load THIS one when the claim's source is a journal/conference paper, not a doc page or a repo. Use alongside arxiv when the paper is or has an arXiv preprint."
---

# Academic citation verification

Verify claims that cite an academic paper by resolving the citation to a canonical DOI and confirming what the paper actually says. The source of truth is the paper itself — its DOI, title, authors, venue, year, and abstract. Many papers sit behind paywalls; the goal is to confirm the *characterization* of the paper (what it claims about itself) from metadata + abstract, and reach full text only when that's insufficient.

## When to load

- An ADR / spec / research brief cites a paper by name + author + year and you must confirm the citation is real and the characterization is accurate.
- "Cite these papers: CCFinder, Deckard, Bellon's taxonomy" — resolve each to a canonical DOI + venue.
- "Does paper X actually claim Y?" — confirm from the abstract without buying the paper.
- Fact-checking a design doc's "prior art" or "according to [paper]" section.
- Any request ending in "verify the citations" / "are these real papers" / "confirm the DOI."

If the claim is about **what vendor docs guarantee**, load `docs-verification`. If it's about **how code is implemented**, load `source-code-verification`. Load THIS when the cited source is a **formal academic publication** (IEEE/ACM/Springer/Elsevier journal or conference).

## The resolution ladder (in order)

### 1. Crossref — DOI + metadata (no key, fast, authoritative)

`api.crossref.org/works?query.bibliographic=<terms>` resolves a partial citation to a canonical DOI + title + authors + venue + year. This is the **DOI-resolution** step — turn "Bellon clone detection tools" into `10.1109/tse.2007.70725`.

```
curl -sS -m 20 "https://api.crossref.org/works?query.bibliographic=Bellon+comparison+clone+detection+tools&rows=3" -o /tmp/x.json
python3 -c "import json;d=json.load(open('/tmp/x.json'))['message']['items'];[print(i.get('DOI'),'|',i.get('title',[''])[0][:90],'|',(i.get('author') or [{}])[0].get('family',''),'|',i.get('container-title',[''])[0][:40]) for i in d]"
```

- **Download-to-file-then-process**, never `curl … | python3` (the shell safety guard blocks piping untrusted output into an interpreter — same guard documented in `docs-verification` and `library-state-verification`).
- `query.bibliographic=` matches across title + authors + venue; `+` for spaces, `OR` for alternatives.
- Already have a DOI? Fetch the record directly: `https://api.crossref.org/works/<DOI>` (e.g. `…/works/10.1109/icse.2007.30`).
- **DOI prefixes identify the publisher:** IEEE `10.1109/…`, ACM `10.1145/…`, Springer `10.1007/…`, Elsevier `10.1016/…`, Nature `10.1038/…`. The DOI is the durable, citeable handle once resolved.

### 2. Semantic Scholar — the abstract (Crossref usually does NOT carry it)

Crossref returns title/authors/venue/year reliably but the `abstract` field is **empty for most IEEE/ACM papers**. The abstract is usually the fastest way to confirm what a paper *claims about itself* (e.g. Deckard is "robust against minor code modifications"), so fetch it from Semantic Scholar:

```
curl -sS -m 20 "https://api.semanticscholar.org/graph/v1/paper/DOI:<doi>?fields=title,abstract,year,authors.name,venue" -o /tmp/x.json
```

- No key needed for low-volume queries (be polite; these are public research APIs; ~1 req/sec).
- Semantic Scholar also gives `citationCount`, `influentialCitationCount`, `isOpenAccess`, `openAccessPdf` — useful for judging whether a paper is seminal.
- When Semantic Scholar also returns `(none)` for the abstract, the paper is paywalled — cite the DOI + title + venue as the authoritative pointer and quote only what you can actually access. **Do not paraphrase an abstract you couldn't read.**

### 3. Open-access full text (when abstract is insufficient)

- **arXiv** (`arxiv.org/abs/<id>`) — free full PDFs; use the `arxiv` skill. Many CS papers have an arXiv version (find it via Semantic Scholar's `externalIds.ArXiv` or `openAccessPdf.url`).
- **Open PDF mirror / author homepage / institutional repo** — often a preprint. Semantic Scholar's `openAccessPdf.url` points directly when one exists.

## Verifying a cited claim — the full sequence

For "confirm paper X claims Y":

1. **Crossref** (`query.bibliographic=`) → resolve citation to canonical DOI + title + authors + venue + year. *(Crossref `abstract` is usually empty — don't rely on it.)*
2. **Semantic Scholar** (`paper/DOI:<doi>?fields=…,abstract`) → read the abstract; confirm/refute the characterization there. This settles ~80% of "does the paper claim X" questions.
3. **Open-access full text** → only if the abstract is ambiguous or the claim is about a specific result/figure/section.

Tag each finding by epistemic tier:
- `[VERIFIED-FROM-ABSTRACT]` — you read the abstract via Semantic Scholar; cite the DOI.
- `[VERIFIED-FROM-FULLTEXT]` — you read the paper (open-access); cite DOI + section/page.
- `[METADATA-ONLY]` — you confirmed the paper exists (title/authors/venue via Crossref) but could not read its content; do not characterize its claims.

Quoting an abstract you couldn't read is fabrication — same standard as `docs-verification`'s verbatim-or-nothing rule.

## Worked example (clone-detection taxonomy verification)

Resolved four foundational citations via the Crossref→Semantic Scholar ladder, no paywalls breached:

| Claimed | Resolved to | Tier |
|---------|-------------|------|
| "Bellon 2002 / taxonomy benchmark" | DOI `10.1109/tse.2007.70725`, *Comparison and Evaluation of Clone Detection Tools*, IEEE TSE 33(9), 2007 (Bellon, Koschke, Antoniol, Krinke, Merlo) | METADATA-ONLY (abstract empty on both APIs) |
| "CCFinder (Kamiya 2002)" | DOI `10.1109/tse.2002.1019480`, *CCFinder: a multilinguistic token-based…*, IEEE TSE 28(7), 2002 | METADATA-ONLY |
| "Deckard (Jiang 2007)" | DOI `10.1109/icse.2007.30`, *DECKARD: Scalable and Accurate Tree-Based Detection of Code Clones*, ICSE 2007 | VERIFIED-FROM-ABSTRACT ("robust against minor code modifications") |
| Roy-Cordy taxonomy restatement | DOI `10.1016/j.scico.2009.02.007`, *Comparison and evaluation of code clone detection techniques…*, Sci. Comput. Program., 2009 | METADATA-ONLY |

The Deckard abstract was the *only* one Semantic Scholar returned; it directly confirmed the paper's self-description, which was the claim under verification. The other three were citeable as canonical pointers even without abstracts.

## Pitfalls

- **Mistaking a retrospective/commentary for the original.** Bibliographic search surfaces follow-ups alongside the seminal paper (e.g. *CCFinder* TSE 2002 vs. the 2025 *Retrospective on Developing CCFinder*, DOI `10.1109/tse.2024.3523370`). Disambiguate by **year + venue**, not title-similarity. Cite the original for the contribution; the retrospective only for post-hoc reflection.
- **Wrong "first author year".** A taxonomy may originate in a thesis/conference before the widely-cited journal version (e.g. Bellon's clone taxonomy originates in a 2002 WCRE thesis; the canonical citation is the 2007 TSE expansion). When precision matters, cite both; default to the widely-cited journal/conference paper as the canonical reference.
- **DOI typos 404, sometimes silently.** `doi.org/<bad-doi>` returns 404. Resolve via Crossref (step 1) rather than hand-typing a DOI you recall — a misremembered DOI is a common silent failure.
- **Asserting a claim the abstract doesn't support.** An abstract confirms what the paper *claims about itself* — that's `VERIFIED-FROM-ABSTRACT` for "the paper says X". It is **not** proof the paper is correct. Don't upgrade a paper's self-claim into a verified fact.
- **General search engines are blocked from automated IPs.** Google returns a CAPTCHA; DDG a JS challenge; Bing geo-redirects. Don't open citation verification with a web search — go **straight to Crossref** by bibliographic query. (Same lesson as `docs-verification`'s web-source-discovery; Crossref is the academic equivalent of "go direct to the source domain.")
- **Forgetting the date.** "Resolved 2026-07-25" — DOIs are stable, but a paper's open-access status and Semantic Scholar's metadata can change. State the verification date for metadata-sensitive claims.

## Verification (self-check before reporting)

- [ ] Does every cited paper resolve to a canonical DOI (via Crossref, not a hand-typed DOI)?
- [ ] Is each characterization of a paper backed by `[VERIFIED-FROM-ABSTRACT]` or `[VERIFIED-FROM-FULLTEXT]`, not inferred from the title alone?
- [ ] Did I distinguish the original seminal paper from follow-ups/retrospectives (year + venue check)?
- [ ] For papers whose abstract I couldn't retrieve, did I label `[METADATA-ONLY]` and refuse to characterize their claims?
- [ ] Did I download-to-file rather than piping curl into an interpreter?

## Output shape

A findings file (Markdown) with: a citation table (claimed citation → resolved DOI → title → authors → venue/year → epistemic tier), then per-paper notes quoting the abstract where available, then a "DOIs / sources" list. If part of a kanban council, post the resolved-citation table to the shared blackboard as a comment so downstream workers inherit the canonical pointers.

## Related skills

- `arxiv` — finding/reading arXiv preprints and Semantic Scholar citation graphs. Load it when the paper is on arXiv or you need citation-count/recommendation data; it covers Semantic Scholar in depth. *(Curator note: `arxiv`'s SKILL.md would benefit from a Crossref pointer back to this skill — the Crossref DOI-resolution step is the natural complement to arXiv's Semantic Scholar section. That edit was attempted this session but `arxiv` resolves to a different profile and was non-editable from here.)*
- `docs-verification` — the methodological sibling for vendor/RFC docs. Shares the verbatim-or-nothing discipline, the download-to-file guard workaround, and the web-source-discovery ladder. It already has an IETF/RFC reference; this skill is its academic-paper counterpart. *(Curator note: once `docs-verification` is editable, the Crossref material here could alternatively live as a `references/academic-papers.md` under it — but as a distinct recurring class of work it stands as its own sibling.)*
- `source-code-verification` — the sibling for claims about code implementation. Use together: verify the *paper's claim* with this skill, then verify the *code that implements it* with that one. *(Curator note: a useful technique surfaced this session — "read the test-fixture filenames to infer behavior" (e.g. PMD's `ignoreIdentsPreservesCtor.java` test data reveals that identifier-normalization deliberately carves out constructors) — belongs in `source-code-verification`'s method section, but that skill is manually-authored and was non-editable this session. Worth adding when editable.)*
- `research` (mattpocock) — the general research umbrella; this skill specializes its "primary sources" step for the academic-paper case.
