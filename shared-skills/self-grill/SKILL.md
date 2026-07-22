---
name: self-grill
description: "Relentless design grill — PO grills you via file-based RPC until the design is resolved or dead. Discovery brief required before launch. Three-door pipeline model with full dossiers and independent fact-verification."
disable-model-invocation: true
---

# Self-grill

> **Support files:**
> - `scripts/graph_state.py`, `scripts/init_branches.sh`, `scripts/add_branch.sh`, `scripts/set_active.sh`, `scripts/answer.sh` — grill state management
> - Web evidence gathering patterns are inline below (see "Gathering real web evidence for dossiers" section) — cannot use separate `references/` files due to symlink quirk, see Known Issues.

Launch PO to grill you on an idea. Branches are created dynamically as the grill reveals what design categories matter for THIS specific idea — no hardcoded list. PO identifies what needs interrogation, you add branches, the grill progresses.

## Discovery phase (prerequisite — do NOT skip)

Before launching the grill, produce a **venture brief**. A raw idea fed to the PO wastes the first 3-5 grill turns just extracting "what problem are you solving?" and "what features do you even want?" — that's discovery work the builder should do *beforehand*. The brief gives the PO concrete claims to attack instead of vague territory to map.

The brief has three pillars:

1. **Problem / Opportunity** — Why does this need to exist? What pain or gap? Who has this problem (be specific — a nameable group, not "everyone")? What do they do today instead, and what sucks about that?
2. **Core Idea** — One-sentence pitch. The core mechanism or insight that makes your approach solve the problem better than what exists. Not features — the *insight*.
3. **Core Features** — The 3-7 irreducible capabilities that make the solution real. Each one traceable back to a pain point. If a feature doesn't map to a problem, it's scope creep, not a core feature.

**Critical framing:** The brief is a **strawman**, not settled scope. When launching the PO, state explicitly: "this list is incomplete by definition; one of your jobs is to find the gaps, not just audit what's here." The PO grills *both* the features on the list *and* the list's completeness. Without this mandate, the PO anchors on the list and becomes a reviewer instead of an interrogator.

The pillars are **iterative**, not sequential — you tighten them in loops until they're consistent with each other (a feature that doesn't solve the stated problem sends you back to pillar 1 or 2).

### Venture brief template

Copy this structure before each grill. Fill it from signal data, market observation, or personal experience:

```
## 1. Problem / Opportunity
- The pain or gap: <What problem exists today? Or what opportunity/gap have you spotted — new tech, market shift, underserved audience?>
- Who has this problem: <Be specific — a nameable group, not "everyone". E.g., "indie SaaS founders doing $5-20K MRR who can't afford a dedicated SDR.">
- What they do today instead: <Current alternatives, workarounds, competitors. What sucks about those?>
- Source of this signal: <Where did this opportunity come from? Demand-signal scan? Market observation? Personal experience?>

## 2. Core Idea
- One-sentence pitch: <What is this thing, fundamentally?>
- Core mechanism / insight: <Why does your approach solve the problem better than what exists? Not features — the insight that makes it work.>

## 3. Core Features (3-7 irreducible capabilities — each must trace back to a pain point in Section 1)
| # | Feature | Maps to pain point | Why it's core (not nice-to-have) |
|---|---------|-------------------|----------------------------------|
| 1 |         |                   |                                  |
| 2 |         |                   |                                  |
| 3 |         |                   |                                  |
```

### Pipeline context

The builder has existing demand-signal infrastructure that may already have data for the brief:

- **3 cron jobs** — (1) Daily Discovery Scan (every 3h, guarded to run once/day, scans 3 doors: Problem/Opportunity/Copycat), (2) RequestHunt Weekly Deep Scan (Mon/Wed/Fri, multi-platform), (3) Pipeline + Build Cycle (4x/day, 3-day cooldown, processes signals through score→dossier→verify→grill→build queue, manages portfolio)
- **Signal data** — `~/vault/ventures/signals/` (daily-scan.md, killgate-*.md)
- **Idea bank** — `~/vault/ventures/idea-bank.md` (lightweight index linking to full dossiers)
- **Dossiers** — `~/vault/ventures/ideas/<slug>.md` (full 13-section venture analysis per idea)
- **Dossier template** — `~/vault/ventures/templates/idea-dossier-template.md`
- **Verification reports** — `~/vault/ventures/ideas/<slug>-verification.md`
- **Verification template** — `~/vault/ventures/templates/fact-verification-template.md`
- **Portfolio** — `~/vault/ventures/portfolio.md` (awaiting review, build queue, grill status, pipeline run history)
- **Specs** — `~/vault/ventures/specs/` (written specs for spec'd ventures)
- **Killed ideas** — `~/vault/ventures/killed-ideas.md` (historical log from old kill-funnel model. Kept for reference, no longer written to.)

Check these BEFORE drafting the brief — a signal for the idea may already have been scanned, scored, and turned into a dossier.

### Pipeline phase structure (build-queue model)

The Pipeline + Build Cycle cron job uses a BUILD QUEUE model with three entry doors. Ideas enter through Problem, Opportunity, or Copycat scanning, get scored, become full dossiers, get fact-verified by an independent verifier, get grilled, and flow into a sequential build queue:

```
ENTRY (3 parallel scan modes):
  Door A — Problem scan     → Reddit/HN complaints (pain-driven)
  Door B — Opportunity scan → tech launches, API releases, regulatory shifts (shift-driven)
  Door C — Copycat scan     → Product Hunt, revenue reports, app rankings (success-driven)

DOWNSTREAM (same for all three):
PHASE 1: INGEST SIGNALS  — capture raw signals tagged by door
PHASE 2: SCORE           — score /25 with evidence, origin modifiers (copycat +1 market-proven)
PHASE 3: BUILD DOSSIERS  — full venture analysis per idea using template
PHASE 3.5: FACT-VERIFY   — independent subagent checks every claim (URLs, stats, quotes)
                           PASS (>=90%) proceed | CONDITIONAL (70-89%) fix + proceed
                           FAIL (<70% or critical claim fabricated) fix or re-research
                           The model that wrote the dossier CANNOT verify it.
PHASE 4: GRILL           — REQUIRED: self-grill on each verified dossier, builder answers PO as founder
PHASE 5: RANK AND PICK   — sort by score, take top 10 unbuilt
PHASE 6: QUEUE BUILDS    — kanban tasks chained SEQUENTIALLY (one at a time)
PHASE 7: REVIEW QUEUE    — move completed builds to "Awaiting Review"
```

Key artifacts:
- **signals/daily-scan.md** — raw signals tagged by door (A/B/C)
- **ideas/`<slug>`.md** — full dossier per idea (13 sections from template)
- **ideas/`<slug>`-verification.md** — fact-verification report per dossier
- **templates/idea-dossier-template.md** — the dossier template
- **templates/fact-verification-template.md** — the verification report template
- **idea-bank.md** — lightweight index linking to dossiers
- **briefs/`<slug>`.md** — three-pillar venture brief (produced from dossier)
- **portfolio.md** — status tracker (Awaiting Review at top, build queue, grill status)

The grill is a REQUIRED step in both the automated pipeline and the interactive loop. No idea gets built without being grilled first. When answering PO, you answer as the FOUNDER — with conviction, using the dossier as evidence, defending the idea or honestly conceding when a branch reveals a real problem. You are not a neutral observer.

### Finding full cron prompts

The `cronjob action='list'` tool only shows truncated previews. To read the full prompts (including the pipeline instructions), read the jobs file directly:

```bash
cat ~/.hermes-teams/startup/profiles/builder/cron/jobs.json | python3 -m json.tool
```

## Fact-verification (Phase 3.5 — REQUIRED before grilling)

Every dossier must be fact-verified by an **independent** subagent before it proceeds to the grill. The model that wrote the dossier cannot verify it — that's echo, not verification.

### How to verify

Dispatch a `delegate_task` with `role='leaf'` using this prompt pattern:

```
Fact-verify the dossier at [path]. You did NOT write this dossier.
Every claim is false until you verify it independently.

Check:
1. SOURCE URLS — does each URL load and say what's claimed?
2. COMPETITOR DATA — revenue, pricing, employees — check original sources
3. MARKET STATISTICS — SBA numbers, engagement metrics, attribution
4. QUOTES — are they real and accurate (not paraphrased or invented)?
5. SCORING — does the evidence cited actually support the sub-scores?

Output VERIFIED / DISPUTED / UNVERIFIABLE for each claim with evidence.
Write report to [path]-verification.md.
Verdict: PASS (>=90% verified), CONDITIONAL (70-89%), FAIL (<70% or critical claim disproven).
Do NOT fabricate verification.
```

### Verification outcomes

- **PASS** → proceed to grill
- **CONDITIONAL** → fix disputed claims in the dossier, note unverifiable ones, then proceed
- **FAIL** → fix the dossier or re-research. If a critical claim is fabricated, kill the DOSSIER (not the idea — it can be re-researched)

The verification report template is at `~/vault/ventures/templates/fact-verification-template.md`.

### What the verifier catches (real examples from LeadPilot dossier, 2026-07-23)

The first verification run found 4 DISPUTED claims in a dossier that appeared well-researched:
1. **Podium pricing: $96/mo claimed → actual $399/mo.** Researcher confused a customer testimonial ("$96K additional monthly revenue") with a pricing tier. The dossier falsely stated this was "verified from pricing page."
2. **Podium valuation: $1.5B claimed → actual $3B** (Wikipedia, TechCrunch)
3. **Podium plan names: "Core, Grow" claimed → actual "Core, Pro, Signature"**
4. **Thryv entry price: $49/mo claimed → actual $244/mo** ($49 is a payroll add-on, not a plan)

The lesson: researchers can confuse adjacent numbers on a page (testimonial amounts vs pricing, add-on prices vs plan prices). The independent verifier catches these because it goes to the source with fresh eyes. 20/26 claims were VERIFIED, 3 UNVERIFIABLE — the process works.

## Dossier delegation pattern

When building dossiers at scale (multiple ideas), delegate the research to subagents rather than doing each one sequentially:

1. **Delegate** — `delegate_task` with the idea name, template path, output path, and existing signal data. Set `role='leaf'`.
2. **Subagent does web research** — finds real quotes, URLs, competitor pricing, market data using the web evidence gathering stack below.
3. **Extract from summary** — if the subagent hits the tool-call limit before writing the file (common with rich 13-section dossiers), the complete content is in the delegation summary file at `~/.hermes-teams/startup/profiles/builder/cache/delegation/subagent-summary-*.txt`.
4. **Write locally** — read the summary, extract the dossier content (starts at the `# <Idea Name> (Dossier)` heading, ends before the `Honest research limitations` footer), write to `~/vault/ventures/ideas/<slug>.md`.
5. **Verify** — dispatch an INDEPENDENT subagent for fact-verification (Phase 3.5 above) before grilling.

With `delegation.max_iterations: 999` (raised from 50→200→999 over 2026-07-23), subagents have enough tool calls to complete both research AND file write. **IMPORTANT:** config changes don't apply to the running engine session — only to the next startup. The extract-from-summary fallback is still useful as insurance for sessions that started under an older limit.

## Gathering real web evidence for dossiers

Sections 2 (Evidence & Signals) and 3 (Competitive Landscape) require **real quotes, URLs, and dates — never fabricated**. Major search engines and Reddit aggressively block datacenter/headless IPs. Use this verified fallback stack (tested 2026-07-23):

### Discover URLs → Brave Search via curl

```bash
curl -s -L -A "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36" \
  "https://search.brave.com/search?q=site:reddit.com+r/smallbusiness+lead+generation+pain"
```

Brave reliably returns real Reddit URLs with descriptive slugs. **Google, Bing, and DuckDuckGo all return captchas** from datacenter IPs — don't waste iterations on them (both browser and curl fail).

### Extract Reddit content → .rss endpoint via curl

```bash
curl -s -L -A "Mozilla/5.0" \
  "https://www.reddit.com/r/smallbusiness/comments/THREAD_ID/.rss"
```

- Returns full post + comments as Atom XML
- **Pace 22-25 seconds between requests** (`x-ratelimit-remaining: 0`, resets ~20s)
- Entry 0 = original post, Entry 1 = AutoModerator (skip), rest = comments
- Extract text from `<content type="html">` tags (HTML-entity-decoded)

### Extract HN content → Algolia API

```bash
curl -s "https://hn.algolia.com/api/v1/search?query=AI+home+service+business"
curl -s "https://hn.algolia.com/api/v1/items/48769010"
curl -s "https://hn.algolia.com/api/v1/search?query=AI+home+service&tags=story"
```

- No rate limits observed
- Full text returned: `comment_text` for comments, `story_text` for stories
- `points` and `num_comments` for engagement metrics

### Competitor data → Wikipedia + pricing pages via curl

```bash
curl -s -L "https://en.wikipedia.org/wiki/Podium_(company)"
curl -s -L "https://www.gohighlevel.com/pricing"
curl -s -L "https://www.thryv.com/pricing/"
```

Parse pricing pages for dollar amounts with regex: `\$[0-9][0-9,]*(?:\.[0-9]{2})?(?:\s*(?:/|per)\s*(?:mo|month))?`

**Pitfall — pricing page confusion:** Customer testimonials on pricing pages often contain dollar amounts (e.g., "$96K additional monthly revenue"). These are NOT prices — but a researcher skimming the page can confuse them with actual tier pricing. Always verify: does the dollar amount appear in a plan name/feature column, or in a testimonial quote? Cross-check against the plan name in the page's JSON data.

### Honesty Protocol

When you can't verify a stat live, flag it explicitly rather than fabricating: "widely attributed to X study; could not re-verify primary URL this session." Always better than a fake citation.

## How it works

```
1. Draft venture brief (discovery phase — 3 pillars) from the dossier
2. Set up empty grill state (no branches)
3. Launch PO with the brief, not a raw idea
4. PO asks questions → first few questions reveal what categories matter
5. Ask PO: "What 3-5 design categories does this idea need?"
6. Create branches from PO's answer
7. Grill through each branch (one at a time) — ANSWER AS FOUNDER with conviction
8. Add new branches if the grill surfaces new categories
9. Grill complete when all branches are done
```

**ANSWER AS FOUNDER means:**
- You have conviction. You want to build this. The dossier is your evidence.
- You don't hedge. If PO asks about competition, you cite the competitive landscape analysis.
- You don't fold. If PO pushes on a weakness, you either defend with evidence or acknowledge and fix it — but you don't abandon the idea.
- You are honest. If a grill branch reveals a fatal flaw, you say so — but "this is hard" is not a fatal flaw.

## Setup

```bash
STATE_DIR="/tmp/grill-<slug>"
mkdir -p "$STATE_DIR"
rm -f "$STATE_DIR/SESSION.key"

cp "$HOME/.hermes-teams/shared-skills/self-grill/scripts/answer.sh" "$STATE_DIR/answer.sh"
cp "$HOME/.hermes-teams/shared-skills/self-grill/scripts/init_branches.sh" "$STATE_DIR/init_branches.sh"
cp "$HOME/.hermes-teams/shared-skills/self-grill/scripts/add_branch.sh" "$STATE_DIR/add_branch.sh"
cp "$HOME/.hermes-teams/shared-skills/self-grill/scripts/set_active.sh" "$STATE_DIR/set_active.sh"
chmod +x "$STATE_DIR"/*.sh

# Initialize (no branches yet)
"$STATE_DIR/init_branches.sh" "$STATE_DIR" "<your idea>"
```

## The grill

### Launch PO

```bash
HERMES_GRILL_STATE_DIR="$STATE_DIR" \
hermes -p product-owner \
  --skills grill-rpc \
  -z "Grill the builder on this idea.

      You will see [GRILL STATE...] before each answer. It shows:
      - A branch table (which design categories are done/active/pending)
      - The active branch with locked decisions and questions already asked

      Branches are dynamic. Start by asking questions about the idea.
      After 2-3 questions, I'll ask you what design categories this idea needs.
      You can propose new branches at any time during the grill.

      RULES:
      - Do NOT re-ask anything in 'Questions already asked'
      - Wrap EVERY question in <Q> tags: <Q>Your question</Q>
      - Stay on the active branch. Don't jump ahead.
      - Push past easy answers. 20+ questions is normal.

      Idea: <your idea>" \
  --cli

# Capture session key
hermes -p product-owner sessions list | grep "cli" | head -1 | awk '{print $NF}'
echo "<session-id>" > "$STATE_DIR/SESSION.key"
```

### Phase 1: Discovery (first 2-3 questions)

Let PO ask questions naturally. Don't create branches yet. After 2-3 exchanges, ask PO:

```
Based on what you've learned, what 3-5 design categories does this idea need?
List them as category names (e.g. "product form", "data sources", "edge cases").
```

Create branches from PO's answer:

```bash
"$STATE_DIR/add_branch.sh" "$STATE_DIR" "product form"
"$STATE_DIR/add_branch.sh" "$STATE_DIR" "data sources"
"$STATE_DIR/set_active.sh" "$STATE_DIR" "product form"
```

### Phase 2: Grill through branches

```bash
HERMES_GRILL_STATE_DIR="$STATE_DIR" \
"$STATE_DIR/answer.sh" "<your answer>"
```

answer.sh does automatically:
1. Extract `Lock D{n}: title = content` from your answer → writes to branch file
2. Inject `[GRILL STATE]` prefix
3. Send answer to PO
4. Extract question (`<Q>` tag or last paragraph with `?`)
5. Log Q&A to branch file
6. Update _state.md decision counts

Use background mode with 300s+ timeout.

### Adding branches mid-grill

When the grill surfaces a new category:

```bash
"$STATE_DIR/add_branch.sh" "$STATE_DIR" "security"
```

### Locking decisions

In your answer, include:
```
Lock D1: Product form = CLI command
Lock D2: Input = JSON config
```

### Moving between branches

When the active branch is exhausted:

```bash
"$STATE_DIR/set_active.sh" "$STATE_DIR" "next branch name"
```

### Done criteria

```bash
# Check for pending or active branches
grep "| pending\|| active" "$STATE_DIR/context/_state.md"
# Empty = all done = grill complete
```

### Export

```bash
for f in "$STATE_DIR"/context/*.md; do
    [[ "$(basename "$f")" == "_state.md" ]] && continue
    echo "--- $(basename "$f")" ---
    cat "$f"
done > "$STATE_DIR/SUMMARY.md"
```

## Timeout guidance

PO takes 60-200s per turn. Never use foreground terminal with 120s timeout.

## Known issues

1. **Session key capture** — save to SESSION.key immediately after launching PO.
2. **Question fallback** — if `<Q>` and paragraph fallback both fail, read stderr.
3. **skill_manage symlink quirk** — this skill is registered via symlink from `shared-skills/self-grill`. `skill_manage(action='patch')` fails with "not found." BUT the `patch` tool works fine when targeting the filesystem path directly: `patch(path='~/.hermes-teams/shared-skills/self-grill/SKILL.md', ...)`. This is the preferred update method. As a last resort, `skill_manage(action='create')` with full content also works. Support files (`references/`, `templates/`) can be written directly to disk at `~/.hermes-teams/shared-skills/self-grill/references/` — just not via `skill_manage`.
4. **Config changes don't apply mid-session** — `delegation.max_iterations` (and any other config in `~/.hermes-teams/startup/config.yaml`) is cached by the engine at startup. Changing it on disk does NOT affect the running session or any subagents it dispatches. Subagents will use the OLD limit until the engine restarts (next `hermes` session). If subagents hit iteration limits despite config being raised, this is why. Workaround: extract content from the delegation summary file (see Dossier delegation pattern step 3) and write locally, or do the work in the main session which has a higher turn limit (500).
5. **Subagent tool-call limit (50 default)** — subagents launched via `delegate_task` have a per-session iteration limit (configured via `delegation.max_iterations`). Rich 13-section dossiers with web research can exhaust 50 iterations before writing the file. The content is always preserved in the delegation summary at `~/.hermes-teams/startup/profiles/builder/cache/delegation/subagent-summary-*.txt` — extract and write locally as a fallback.

## Overlap note

`grill-rpc-ops` covers PO launch, branch management, timeout patterns, and model quirks from an operational perspective. This skill covers the full grill workflow including discovery, dossier integration, pipeline context, and the founder-answerer role. The overlap is in RPC operational details — both skills should cross-reference each other.
