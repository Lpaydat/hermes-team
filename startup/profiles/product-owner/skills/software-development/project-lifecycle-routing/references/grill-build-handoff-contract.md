# Grill → Build Handoff Contract

The builder pipeline (Stage 3) runs as two-card parallel pairs per idea: a grill card and a build card. The PO inherits the output at promotion. This reference documents what each stage produces, what the next stage reads, and where the validation gaps are.

## The two-card split

```
GRILL CARD (Card A, no parent):
  reads dossier → grills with PO → outputs context/*.md → validates → completes
  Loads: self-grill + grill-rpc-ops
  Output: ~/projects/<slug>/context/*.md + .context/grill/decisions.md + .context/dossier.md
  Does NOT build prototype

BUILD CARD (Card B, child of grill card, auto-promotes when grill completes):
  reads context/*.md → loads venture-prototype skill
  → POC gate → picks type → builds with loop_engine → README → handoff
  Output: ~/projects/<slug>/prototype/ + ~/projects/<slug>/README.md
  Does NOT re-grill
```

Each idea runs as an independent pair. No cross-idea chaining.

## 1. What grill produces

### Primary output: `~/projects/<slug>/context/` (validated)

```
~/projects/<slug>/context/
├── _state.md              ← branch table (| N | name | status | decisions |)
├── <branch-slug>.md       ← one file per branch:
│   ├── ## Decisions       ← locked decisions ("Lock D<n>" lines)
│   └── ## Questions asked ← Q&A log
└── ...
```

### Secondary output: `~/projects/<slug>/.context/` (NOT validated)

```
~/projects/<slug>/.context/
├── grill/decisions.md     ← flat summary of all locked decisions
└── dossier.md             ← copy of dossier from ~/vault/ventures/ideas/<slug>.md
```

### Validation gate: `validate-grill-output.sh`

Runs before grill card completion. 6 checks:

| # | Check | Fails if |
|---|-------|----------|
| 1 | `context/` dir exists | missing |
| 2 | `_state.md` has ≥1 branch entry | no branches |
| 3 | Each branch file exists + has `## Decisions` + `## Questions asked` | missing file or section |
| 4 | ≥1 locked decision (`Lock D` lines) across all files | no decisions |
| 5 | No orphaned files in `/tmp/grill-<slug>/context/` | not persisted |
| 6 | Real PO session (≥5 `<Q>` tags in PO state.db) | self-play |

**GAP:** Checks 1-5 only cover `context/` (no dot). The `.context/` secondary outputs are NOT checked.

## 2. What build references from grill

| Grill artifact | Path | Purpose in build |
|----------------|------|------------------|
| Per-branch decisions | `context/*.md` | The spec. Each `Lock D` tells builder what to build and what NOT to build. |
| Decisions summary | `.context/grill/decisions.md` | Flat list for README "Grill Decisions" table + verify script |
| Dossier copy | `.context/dossier.md` | Full context for README "What It Is" / "The Problem" |

The build card has the grill card as parent — auto-promotes to `ready` only when grill completes.

## 3. What build produces

| Artifact | Path | Notes |
|----------|------|-------|
| Prototype | `~/projects/<slug>/prototype/` | Type-matched: HTML / API / CLI / MCP / concierge. One command to run, simulated data. |
| README | `~/projects/<slug>/README.md` | 9 sections (see venture-prototype template). "How to Review" must be click-by-click. |
| Portfolio entry | `~/vault/ventures/portfolio.md` | Appended to "Awaiting Review" row |
| Kanban comment | on build card | Prototype path, README path, aha moment, 2-3 decisions to challenge |
| POC result | `~/projects/<slug>/prototype/poc-result.md` | Only if riskiest assumption is technical. Verdict pass/fail with evidence. |
| Verify script | `/tmp/verify-<slug>.py` | Written before building. ≥20 checks. Runtime execution (category 5) mandatory. |

## 4. Validation gates summary

| Stage | Gate | What it checks |
|-------|------|----------------|
| Grill | `validate-grill-output.sh` exit 0 | File structure, decisions, anti-self-play |
| Build | `/tmp/verify-<slug>.py` exit 0 | Prototype matches decisions, README complete, runtime executes |
| Both | loop_engine verifier gates | Independent agent checks work against `context/` spec |

Enforcement is **file-based** (script exit codes), not metadata-based. The `kanban_complete` metadata is descriptive.

## 5. Contract gaps

1. **No explicit `kanban_complete` metadata schema.** Neither self-grill nor venture-prototype prescribes the metadata dict. Recommended fields:

   **Grill completion:** `{slug, branches, locked_decisions, questions_asked, validation_passed, context_dir}`

   **Build completion:** `{slug, prototype_type, prototype_path, readme_path, verify_checks_passed, verify_checks_total, verify_runtime_checked, loop_engine_used, poc_result, portfolio_updated, handoff_comment_posted, decisions_to_challenge}`

2. **`.context/` (dotted) is unvalidated.** A grill passes validation without producing the flat summary the build card is told to read. The build should fall back to deriving it from `context/*.md` rather than blocking.

3. **README decision count can mismatch.** The builder estimates the count instead of counting with `grep -rh '^Lock D' ~/projects/<slug>/context/*.md | wc -l`. The verify script should assert the counts match.

## PO touchpoints

The PO inherits this output at promotion (`project-promotion` skill, step 2: copy `context/*.md` → `.context/grill/`). Before promotion, verify the artifact inventory — especially the unvalidated `.context/` files. Do NOT block promotion on missing `.context/` convenience files; derive them from the validated `context/` primary output.
