# Verify-method comparison — principle-based (behavior) vs static review

When a board runs **two verification tracks in parallel** — a static-code-review
track (read the code, find bugs by inspection) AND a principle-based
behavior-test track (write adversarial inputs and EXECUTE them) — the board
becomes a natural A/B bake-off between the two methods. The audit question
("did the principle-based verify catch something the static review missed?")
is itself a high-value finding that no single-track board can produce.

This reference captures the methodology and a worked example. Load it when:
- The user explicitly asks "did principle-based / behavior verify catch
  something static review missed?"
- A board has both `[probe] static review` AND `[verify-b] integration` (or
  `[probe] fresh-eyes`) cards on the same SUT.
- You are scoring a board where verify accuracy is the headline dimension.

## a. How to detect a dual-track board

Look for two distinct verify populations on the same code revision:

```sql
-- Static review track: cards whose summary mentions reading the code
SELECT task_id, summary FROM task_runs
WHERE summary LIKE '%static review%' OR summary LIKE '%static%' AND profile='verifier';

-- Principle-based / behavior track: the integration verify + fresh-eyes probes
SELECT task_id, summary FROM task_runs
WHERE (title LIKE '%[verify-b]%' OR summary LIKE '%behavior test%' OR summary LIKE '%fresh-eyes%')
  AND profile='verifier';
```

A dual-track board typically looks like: 3 loop_engine phases each with a
per-phase `[verify]` (behavior tests for that phase's ACs), then a separate
post-build `[verify-b]` integration verify (full adversarial suite), then a
parallel `[probe]` swarm dispatched off the integration verify (fresh-eyes AC
verification + static review + delta check). The **fresh-eyes** and **static
review** probes are the static track; the **[verify-b]** is the
principle-based behavior track.

## b. The head-to-head comparison table

Build this table from the run summaries + finding comments. For each bug found
on the board, mark which track found it:

| Bug | Static review track | Principle-based behavior track |
|-----|---------------------|--------------------------------|
| (enumerate every finding) | FOUND / MISSED | FOUND / MISSED |

The cell contents come from:
- **Static review:** query the `[probe] static review` card's findings (its
  `summary` in `task_runs`, or its comments).
- **Principle-based:** query the `[verify-b]` card's `task_comments` for the
  FAIL/finding text + the re-verify chain that followed.

Bugs that appear in ONLY ONE column are the method-comparison signal. The
pattern observed across boards so far:

| Bug class | Static review | Principle-based behavior |
|-----------|--------------|--------------------------|
| Readable logic bugs (wrong regex, missing escape, off-by-one in visible code) | **FOUND** (by inspection) | found or missed |
| I/O crash bugs (unhandled exception on hostile input: NUL byte, bad UTF-8, broken pipe, ENOSPC, closed fd) | **MISSED** | **FOUND** |
| Spec-gap issues (XSS via attribute breakout when spec only mandates `& <>` escape) | **FOUND** (reads the regex, sees the gap) | found + correctly classified as spec gap |
| Concurrency / production-mode bugs (Werkzeug vs WSGI, reloader double-exec) | missed | **FOUND** (executes under real conditions) |

**The robust finding: principle-based behavior verify catches I/O crash bugs
that static review cannot, because static review reads what the code *says* but
never discovers what it *does* under inputs the author never imagined.** Static
review wins on readable-logic bugs (it can see a missing quote-escape in a
regex that behavior tests may not think to probe).

## c. The multi-iteration re-verify chain as escalation evidence

When the principle-based verify FAILs, a fix→re-verify loop often reveals a
**systemic pattern**: each fix closes one I/O path while leaving the next one
unguarded (the "whack-a-mole" pattern). This is NOT a verifier failure — it is
the verifier doing its job across iterations. Score it as a verify-accuracy
POSITIVE (the verifier kept finding real bugs) paired with a fix-effectiveness
observation (point-fixes vs root-cause holistic fix).

Read the chain in order: `[verify-b] FAIL → [fix-b] → [re-verify-b] FAIL →
[fix] → [re-verify-c] ESCALATE (iter cap) → [escalation] → [fix-c] holistic →
[re-verify] PASS`. The escalation card and the final tech-lead adjudication are
where the systemic root cause gets named. Quote the tech-lead's I/O-surface
matrix (the table of every I/O path + its guard status) as the convergence
evidence.

## d. Reproducing the method-comparison yourself

Do not trust either track's self-report. For every bug either track claims to
have found OR that you suspect was missed, **run the repro yourself** against
the final code. The strongest evidence in the report is a table like:

| Input | Expected | Actual on final code | Which track found it |
|-------|----------|----------------------|----------------------|
| `printf 'text\x00C0\x00more' \| md2html.py` | exit 0, no crash | exit 0, NUL stripped ✓ | principle-based (iter 1) |
| `[x](http://evil" onmouseover="alert(1))` | no attribute breakout | `<a href="http://evil" onmouseover=...` — breaks out ✗ | static review + principle-based (spec gap) |
| `md2html.py big.md \| head -1` | silent exit | exit 1, empty stderr ✓ | principle-based (iter 3) |

Bugs in the "which track found it" column that read "static MISSED /
principle-based FOUND" are the headline of the report.

## e. Worked example — livetest-unbias-1 (Markdown→HTML Converter)

Dual-track board. The loop_engine ran 3 phases (all PASS iter 1, 24/24 ACs).
Then a post-build integration verify (`t_488b863d`) FAILed 61/62, triggering a
6-iteration fix→re-verify chain. In parallel, a 3-way probe swarm
(`t_709ceff9` fresh-eyes, `t_d1794cb0` static review, `t_25c9eaef` delta check)
ran off the same SUT revision.

**Head-to-head result:**

| Bug | Static review (`t_d1794cb0`) | Fresh-eyes (`t_709ceff9`) | Principle-based behavior (`t_488b863d` + chain) |
|-----|------------------------------|---------------------------|--------------------------------------------------|
| NUL-sentinel IndexError crash | **MISSED** | **MISSED** | **FOUND** (Critical, iter 1) |
| UnicodeDecodeError raw traceback | **MISSED** | **MISSED** | **FOUND** (iter 2) |
| BrokenPipeError raw traceback | **MISSED** | **MISSED** | **FOUND** (iter 3) |
| OSError/ENOSPC raw traceback | **MISSED** | **MISSED** | **FOUND** (iter 4) |
| closed-stdout `>&-` AttributeError | **MISSED** | **MISSED** | **FOUND** (iter 5) |
| Link-URL XSS (attribute breakout) | **FOUND** (reads regex, sees `html_escape(quote=False)`) | **FOUND** | **FOUND** + correctly classified as spec gap |
| UTF-8 BOM not stripped | not reported | **FOUND** (Minor) | not reported |

**The signal: the static track found exactly the readable-logic bug (XSS via
unescaped quote in URL) and missed ALL FIVE I/O crash bugs.** The principle-based
behavior track caught every crash by executing hostile inputs
(`printf '\x00C0\x00'`, `>&-`, `| head`, `> /dev/full`, `0xff` byte) that a
code reader would never imagine. The board's verify accuracy scored 10/10
specifically because the principle-based track did what static review could not.

**Why the static track missed the NUL crash:** the bug lives in an internal
sentinel mechanism (`\x00C{n}\x00` placeholder for stashed code spans). Reading
the code, the regex looks correct. Only EXECUTING an input containing that byte
pattern triggers the `IndexError` on the restore lambda. Static review reads
what the code says; behavior verify discovers what it does.

**The escalation was honest.** Each re-verify FAILed on a NEW real bug (not a
re-finding), the loop hit its iter cap, escalated to a tech-lead holistic-fix
card that guarded all 4 I/O paths in one pass, and the final re-verify PASSed.
No false PASS at any iteration. This is verify accuracy working exactly as
designed — the 5 findings are all true positives, reproduced independently.
