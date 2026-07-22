---
name: grill-rpc-ops
description: "Operational playbook for self-grill and peer-grill RPC sessions. Covers PO launch, branch management, timeout patterns, model quirks, and known pitfalls."
---

# Grill RPC Operations — Operational Playbook

## Version History

| Version | When | What |
|---------|------|------|
| v0.2 | 2026-07-21 | `<Q>` tag extraction + CONTEXT.md |
| v0.3 | 2026-07-21 | Graph DB approach (E2E FAILED — glm-5.2 ignores tags) |
| v0.4 | 2026-07-21 | Hardcoded 8 branch files (E2E WORKING) |
| v0.5 | 2026-07-21 | grill-rpc skill, auto-lock, no-tag fallback |
| v0.7 | 2026-07-22 | Dynamic branching — branches grow per idea, not preset |
| v0.7.1 | 2026-07-22 | Branch name normalization (space→hyphen), dynamic state update |
| v0.8 | 2026-07-22 | Pipeline shifted kill-funnel → build-queue. Grill initially set optional. 3-pillar venture brief replaces 4-step discovery. Sequential kanban_link build chain. |
| v0.9 | 2026-07-23 | Three-door entry model (Problem/Opportunity/Copycat). Full 13-section dossiers replace thin one-liner entries. Scoring rubric with origin modifiers. idea-bank.md → lightweight index, ideas/<slug>.md → full dossiers. Pipeline prompt rewritten for 3-door + dossier model. |
| v1.0 | 2026-07-23 | Grill changed from optional BACK to REQUIRED (user correction). Builder answers PO as FOUNDER with conviction. Independent fact-verification phase (3.5) added before grilling. delegation.max_iterations raised 50→200→999. |
| v1.0.1 | 2026-07-23 | Confirmed iteration limit root cause: `IterationBudget` class in `agent/iteration_budget.py` (code default 50, configurable via `delegation.max_iterations`). Config caching is by-design engine behavior — restart required to apply. |

## Current Architecture (v0.7.1)

### Scripts (in `shared-skills/self-grill/scripts/`)

| Script | Purpose |
|--------|---------|
| `init_branches.sh` | Create empty `_state.md` — zero branches. Branches added dynamically. |
| `add_branch.sh` | Create a new branch file + add row to `_state.md`. Idempotent. |
| `set_active.sh` | Mark a branch active, others move to done. |
| `answer.sh` | Send answer to PO, extract question, auto-lock decisions, update state. |

### Grill Flow

```
Phase 1: Discovery (2-3 questions)
  → PO asks what THIS idea needs
  → Create branches from PO's answer

Phase 2: Grill branches (one at a time)
  → set_active.sh to switch between branches
  → add_branch.sh when new categories emerge

Phase 3: Done when no pending or active branches in _state.md
```

### PO Launch Recipe

```bash
STATE_DIR="/tmp/grill-<slug>"
mkdir -p "$STATE_DIR"

# Copy scripts
cp ~/.hermes-teams/shared-skills/self-grill/scripts/*.sh "$STATE_DIR/"
chmod +x "$STATE_DIR"/*.sh

# Init empty state
"$STATE_DIR/init_branches.sh" "$STATE_DIR" "<idea>"

# Launch PO
HERMES_GRILL_STATE_DIR="$STATE_DIR" \
hermes -p product-owner \
  --skills grill-rpc \
  -z "Grill the builder on: <idea>. You will see [GRILL STATE...] before each answer. Branches are dynamic — propose categories as needed." \
  --cli

# Capture session key
hermes -p product-owner sessions list | grep "cli" | head -1 | awk '{print $NF}' > "$STATE_DIR/SESSION.key"
```

### Answer Pattern

```bash
HERMES_GRILL_STATE_DIR="$STATE_DIR" \
"$STATE_DIR/answer.sh" --file /dev/stdin << 'ANSWER'
Lock D1: Title = Value

Your answer text here. PO won't see this outside the grill.
ANSWER
```

answer.sh automatically:
1. Extracts `Lock D{n}: title = content` from builder's answer → writes to branch file
2. Injects `[GRILL STATE]` prefix (branch table + active branch Q&A)
3. Sends answer to PO via `hermes --resume`
4. Extracts question: `<Q>` tag first, fallback to last paragraph with `?`
5. Logs Q&A to branch file
6. Updates `_state.md` decision counts dynamically (reads all rows, not hardcoded)

### Branch Management

```bash
# Add a new branch
"$STATE_DIR/add_branch.sh" "$STATE_DIR" "security model"

# Set active
"$STATE_DIR/set_active.sh" "$STATE_DIR" "security model"

# Check remaining work
grep "pending\|active" "$STATE_DIR/context/_state.md"
```

## Known Pitfalls

### PO Timeout (CRITICAL)

glm-5.2 takes **60-200 seconds per turn**. Never use foreground `hermes --resume` with <300s timeout — gets interrupted (exit 130).

**Correct pattern:**
```bash
# Launch PO: background=true, notify_on_complete=true, timeout=900
# Resume: same pattern

# For process wait: use repeated polling, not one long wait
process(action="wait", session_id="...", timeout=60)  # Repeat as needed
```

The builder session can't `process wait` past 60s. The answer.sh wraps `hermes --resume` in `HERMES_GRILL_TIMEOUT` (default 600s) internally — answer.sh handles its own timeout.

### `<Q>` Tag Compliance

glm-5.2 uses `<Q>` tags ~50% of the time. The fallback (last paragraph with `?`) catches the rest. `<LOCK>` and `<DONE>` tags have 0% compliance — decisions are locked by the builder, not PO.

### Branch Name Normalization

`add_branch.sh` creates files with spaces→hyphens: "product form" → `product-form.md`. answer.sh normalizes the slug by converting spaces to hyphens and lowercasing. If a branch name has special characters, create the file manually.

### Vision Model

zai API has **NO vision models** — all glm variants reject image content types. To get vision, use a different provider:
- OpenRouter (Claude, GPT-4o, Gemini — all support vision)
- Google Gemini (free tier available)
- ZhipuAI direct API (GLM-4V — the original Chinese API)

Config key is `auxiliary.vision.{provider,model}`, NOT `model.vision`.

### Grill Is REQUIRED (build-queue model — updated 2026-07-23)

The pipeline uses a **build queue** (nothing is killed, everything is scored and built, the human decides promotion). The grill is **REQUIRED** — every idea gets grilled before it goes to the build queue. No exceptions.

**Key change (2026-07-23):** The user explicitly corrected "grill optional" → "make it as required step." The grill is mandatory in BOTH the automated pipeline (Phase 4) and the interactive loop. SOUL.md was updated to enforce this.

**What "required" means:** Before any build is queued, the dossier must pass through the grill. The builder answers PO as the FOUNDER — with conviction, using the dossier as evidence, defending the idea or honestly conceding. This is NOT optional, NOT skippable, and "mental grilling" is not a substitute.

**The pipeline flow:** Discovery (3-door scan) → Dossier (13 sections) → Fact-Verify (independent subagent) → **GRILL (required, builder as founder)** → Build Queue (sequential kanban) → Awaiting Review.

### SOUL.md ↔ Skill Code Sync (CRITICAL)

SOUL.md, the grill scripts, and the pipeline cron prompts must all describe the same system. If any one changes, the other two must be checked for stale references in the same session.

**Common drift sources:**
- Pipeline model changes (e.g., kill-funnel → build-queue → three-door dossiers) require updating: SOUL.md core principle, pipeline cron prompt (read via `cron jobs.json`), and the self-grill SKILL.md pipeline context section.
- Script logic changes (branch model, answer extraction) require updating: grill-rpc-ops SKILL.md architecture section, and any memory entries describing the system.
- The "NEVER write code without self-grill" rule was REMOVED in the build-queue shift, then RESTORED 2026-07-23 when user corrected "grill optional" → "required step." The grill mandate is back: every build goes through self-grill first, builder answers PO as founder with conviction.
- **As of v1.0 (2026-07-23):** Pipeline phases are now 7: INGEST → SCORE → BUILD DOSSIERS → FACT-VERIFY → GRILL → RANK AND PICK → QUEUE BUILDS → REVIEW QUEUE. Phase 3.5 (fact-verification by independent subagent) and Phase 4 (required grill) were added. The dossier phase replaces the old "brief" phase. Ideas are now full 13-section analyses, not one-liners. Builder answers PO as FOUNDER with conviction.

**Maintenance rule:** After any change to the grill/pipeline system, check SOUL.md, cron prompts, and memory entries for stale references and patch them in the same session.

### Pre-Build Discovery Phase — Venture Brief (3 Pillars)

The grill is reactive — it interrogates an idea you hand it. But it has no concept of whether the idea is the RIGHT idea. Before launching PO (or before building directly), produce a **venture brief** — three pillars:

1. **Problem / Opportunity** — What pain? Who has it (specific, nameable group)? What do they do today? What sucks about it?
2. **Core Idea** — One-sentence pitch. The core mechanism/insight that makes your approach better. Not features — the *insight*.
3. **Core Features** — 3-7 irreducible capabilities, each traceable to a pain point. If a feature doesn't map to a problem, it's scope creep.

**Critical framing:** The brief is a **strawman**, not settled scope. When launching the PO, state: "this list is incomplete by definition; one of your jobs is to find the gaps." The PO grills both the features AND the list's completeness.

The pillars are **iterative** — tighten in loops until consistent (a feature that doesn't solve the stated problem sends you back to pillar 1 or 2).

**Template:** See `templates/venture-brief.md` in the self-grill skill.

### Skill Registration Check

Shared skills live in `~/.hermes-teams/shared-skills/<name>/` but must be symlinked into `~/.hermes-teams/startup/profiles/builder/skills/<name>` to be loadable via skill_view. If a skill exists in shared-skills but skill_view returns "not found", the symlink is missing:

```bash
ln -s ~/.hermes-teams/shared-skills/<name> ~/.hermes-teams/startup/profiles/builder/skills/<name>
```

This affected self-grill during this session — the skill existed and had working scripts but couldn't be loaded because the symlink was never created.

## Decision Locking Format

In your answer text, include:
```
Lock D1: product form = CLI command
Lock D2: input = JSON config file
```

answer.sh extracts these lines via grep and inserts them under the `## Decisions` section of the active branch file.

## Done Criteria

```bash
# All branches done = grill complete
grep "| pending" "$STATE_DIR/context/_state.md" && echo "STILL GOING" || echo "DONE"
grep "| active" "$STATE_DIR/context/_state.md" && echo "STILL GOING" || echo "DONE"
```

## Reference Files

See `references/` for:
- `2026-07-21-branch-e2e-findings.md` — v0.4 E2E test results
- `2026-07-21-tag-compliance-failure.md` — glm-5.2 tag non-compliance data
- `2026-07-22-po-timeout-pattern.md` — PO timeout/background polling pattern
- `2026-07-22-vision-provider-findings.md` — zai vision model findings
- `2026-07-22-dynamic-branch-e2e.md` — v0.7.1 E2E test results
- `2026-07-22-anti-rationalization-gate.md` — SOUL patching for auto-grill enforcement
- `2026-07-22-build-queue-pipeline.md` — Pipeline architecture (kill-funnel → build-queue shift, artifact map, sequential build chain, known issues)
- `references/2026-07-23-three-door-dossier-pipeline.md` — Three-door model (Problem/Opportunity/Copycat), full dossiers replacing thin entries, scoring rubric with origin modifiers, updated pipeline phases, updated artifact map
- `references/2026-07-23-config-cache-and-delegation-limits.md` — Config changes don't apply mid-session (engine caches at startup). Delegation iteration limit workaround for research-heavy subagent tasks.