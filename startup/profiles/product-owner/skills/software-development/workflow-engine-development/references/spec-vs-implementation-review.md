# Spec-vs-Implementation Review — Verifying a Diff Against Its Design Doc

> Distilled from reviewing `feat/workflow-dispatch` (5898-line diff) against
> `DESIGN-stateless-graph.md` (933-line spec), 2026-08-02. Caught 7 material
> gaps: 4 unimplemented requirements, 1 implementation bug, 2 scope-creep
> behaviors. Zero false positives.

The companion to **design-review-methodology.md**. That one covers reviewing
the design BEFORE code is written (parallel subagents, iterative rounds). This
one covers reviewing the code AFTER it's written, against the approved design.

## When to use this

- A feature branch is ready to merge and you want to confirm the diff matches
  the spec before review/approval.
- A large diff was written across many commits or by subagents and you need to
  verify completeness.
- The user says "spec review of <branch>" / "review this against the design" /
  "did we implement everything."

Not for: style/convention review (use the `code-review` skill), or reviewing a
diff that has no spec (just say so).

## The core technique: verify by grep, not by reading

The single most important lesson. A spec makes many claims ("all 9 dispatch
shapes port with iteration-aware keys", "GC trims the blob once per tick",
"the tick aborts on version conflict"). The naive approach is to re-read each
piece of code mentioned in each claim. That is slow and misses things.

**Instead: turn each claim into a grep and let the search tell you the truth.**

The session's breakthrough finding came from exactly this. The spec said
"All 9 shapes port with one change: idempotency keys become iteration-aware."
Instead of reading all 9 dispatch methods, run:

```
grep -n "idem_key =" runtime.py
```

Output showed 3 hits — but only 2 carried `iter_suf`. The foreach-subworkflow
shape (`:sw:{idx}`) was missing the suffix; the single-subworkflow shape had
no idem key at all. That's a silent loop-break bug found in one grep vs.
reading 800 lines of dispatch code. Six of the seven findings came from
exactly this pattern: translate a spec assertion into a grep, look for what's
MISSING from the results.

### Claim → probe mapping (cheat sheet)

| Spec claim shape | Grep / probe |
|---|---|
| "All N shapes / methods do X" | `grep -n "<marker>" <file>` — count the hits, check each carries X |
| "Helper Y is called every tick" | `grep -n "Y\|def Y" <file>` — confirm a call site exists |
| "Field Z is added to the schema" | `grep -n "Z" <file>` in the schema/migration section |
| "Behavior B is preserved from legacy" | `grep -n "<legacy-marker>" <file>` — confirm still present |
| "Abort on conflict / fail-fast on X" | grep the conflict path, check whether it returns/raises vs continues |

If the grep returns nothing where the spec said something would be, that's a
finding (bucket a). If the grep returns something where the spec said nothing,
that's a finding (bucket b).

## Process

### 1. Read the spec IN FULL first

Read the entire design doc before touching the diff. Do not skim. A 900-line
spec held in one context catches cross-references ("§GC says trim; §Reset also
caps at 10 — are these the same mechanism?") that section-by-section reading
misses. Use `read_file` with offset to page through if truncated.

### 2. Get the diff shape, then read it in segments

```
git diff main...HEAD --stat          # shape: which files, how big
git diff main...HEAD -- <file>       # one file at a time
```

The diff is usually too large for one tool call. Read `model.py` + migration
first (schema/data), then `runtime.py` in segments. The `--stat` tells you
where the bulk is.

### 3. For each spec section, form a verification probe

Walk the spec section by section. For each requirement or invariant, ask:
"what in the code would I see if this were implemented? what would I see if it
weren't?" Turn that into a grep or a targeted read. This is faster than
re-reading code you've already seen.

### 4. Classify every finding into exactly one of three buckets

The reporting structure that makes the review actionable. Every finding is one of:

**(a) Missing or partial** — the spec asked for it; the code doesn't have it, or
has a partial version. Cite the spec line. Example: "Spec §GC L834: `_trim_blob`
called once per tick. No `_trim_blob` exists; `cleanup()` still only DELETEs
`node_states`."

**(b) Scope creep** — the code has behavior the spec never asked for. This is
often a latent bug (un-specced behavior is un-reviewed behavior). Example:
"Entry-node self-gating skip marks a dep-less node `skipped` permanently when
its condition is false — no spec rule supports this."

**(c) Implemented but wrong** — looks present but doesn't match the spec's
details. This is the most dangerous bucket (passes a glance, fails a read).
Example: "foreach-subworkflow uses `wf:{inst}:{node}:sw:{idx}` with NO iter
suffix (spec L547 requires `:iter<N>:` before `:sw:`). Loops silently break on
reset because dedup adopts the iter-0 child."

### 5. Quote spec line numbers for every finding

Makes each finding falsifiable and re-checkable by the author. "Spec L57 says X;
runtime.py:2623 does Y" lets the author verify in seconds. A finding without a
spec citation is an opinion.

### 6. This is a READ-ONLY review — state it explicitly

A spec-vs-implementation review produces findings, not edits. Say so in the
report ("No files modified — read-only review") so the author knows the next
step is theirs, and so you don't drift into fixing things mid-review.

## Why this beats "read everything carefully"

A 5900-line diff read linearly will surface maybe 2-3 obvious issues and miss
the cross-cutting ones (the same field missing from 4 of 9 call sites). The
grep-probe approach is O(claims) not O(diff-size): you issue ~10-20 targeted
searches instead of re-reading 5900 lines, and the searches are exhaustive in a
way that reading isn't. The bug where 2 of 3 `idem_key` sites lacked a suffix
is invisible to a reader who isn't counting; it's obvious to a grep that lists
all 3 sites side by side.

## Output format that worked

A short header naming the diff and spec sizes (orients the reader), then the
three buckets as `(a) / (b) / (c)` subsections, each finding with: what the spec
says (with line ref), what the code does (with file:line), and the consequence.
Close with a one-paragraph summary naming which spec sections are faithful and
which shipped gaps. Keep it under ~400 words; the author has the code and the
spec — your value is the mapping between them, not prose.

## Pitfalls

- **Don't re-read code to verify a claim you can grep.** Grep is exhaustive;
  reading is attention-limited. Reserve reading for understanding a single
  complex mechanism, not for checking N sites for the same property.
- **Don't conflate "I didn't find it" with "it's missing."** A grep that returns
  nothing might mean the code uses a different name. Before reporting (a),
  confirm the mechanism truly isn't there (try variant names, check the call
  site of a related function).
- **Don't report style issues here.** That's the `code-review` skill's job.
  Mixing "missing GC trim" with "this variable name is vague" dilutes the
  signal. Keep this review purely about spec↔code correspondence.
- **Don't fix things mid-review.** If you start editing, you lose the
  read-only stance and the author loses a clean before/after. Report findings;
  let the author fix.
- **Beware "looks implemented" traps.** The `(c)` bucket is where the worst
  bugs hide. A function exists, it's called, it runs — but it doesn't do what
  the spec's detail requires. Always check the details (the suffix ordering,
  the conflict-abort vs continue, the cap enforcement), not just the presence.
