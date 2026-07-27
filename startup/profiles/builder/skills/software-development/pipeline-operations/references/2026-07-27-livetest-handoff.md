# E2E Livetest Handoff — Builder Workflow Performance Test

> **Purpose:** This document is a handoff for a fresh builder session. The previous builder was refactored. We need to test whether the pipeline workflow still performs correctly. The init builder (you, reading this) should BARELY involve itself — the goal is to test the WORKFLOW, not your personal skill. Set it up, let it run, observe.

## What You're Testing

The full venture pipeline: scan ideas → score → grill (PO grills builder) → build prototype → verify → present. We just refactored the builder profile and want to know: does the workflow still produce 10/10 clean completions?

## Context From Previous Run

A previous livetest (2026-07-26) completed 10/10 pairs on board `e2e-livetest` (20 cards). 5 bugs were found and fixed:

1. **answer.sh _state.md count bug** — IFS parsing was 4-field, needed 5-field (leading pipe creates empty first field). FIXED.
2. **max_turns too low** — profile config had `max_turns: 200`, causing premature timeouts on deep grills. Fixed to 2000.
3. **Deepseek fallback** — hermes auto-discovered DEEPSEEK_API_KEY and fell back to deepseek. Commented out in .env + config.
4. **Empty base_url** — profile config had `base_url: ''` overriding main config's correct zai endpoint. Removed.
5. **Verify template** — had only static checks (AST, grep). Added Category 5: Runtime Execution (subprocess.run, exit code 0).

All fixes are committed: `478e587` on `feat/decision-tree-grill`.

## How to Run the Livetest

### Step 1: Create a fresh board

```bash
hermes kanban boards create e2e-livetest-2
```

### Step 2: Pick 10 unbuilt ideas

Read `~/vault/ventures/idea-bank.md`. Look at the "Unbuilt" section for ideas with status `unbuilt` or `deep_dived` (NOT `BUILT_AWAITING_REVIEW` or `IN_GRILL`). Pick 10 that haven't been built yet. Each idea needs a dossier at `~/vault/ventures/ideas/<slug>.md`.

For the previous run, these 10 were used (DO NOT reuse — they're built):
- smb-cross-platform-data-sync
- ai-coding-flow-state-tool
- agency-reporting-data-aggregation
- how-are-you-hiring-engineers
- ai-always-adds-code-fixer
- ai-agent-management-burden
- ai-tool-spend-management-dashboard
- code-reading-first-ide
- ai-powered-internal-tool-builder
- the-log-is-the-agent

Pick 10 DIFFERENT unbuilt ideas from the idea bank. Good candidates (have dossiers, are unbuilt):
- dockerless-ci-verification-service (19/25)
- ai-rank-tracker (18/25)
- ai-pen-testing-service (18/25)
- security-review-readiness-for-ai-saas (17/25)
- subscription-cancellation-saas-rescue-assistant (15/25)
- pre-flight-repo-security-scan (15/25)
- collaborative-ai-prompt-spec-workspace (15/25)
- ai-architecture-specification-tool (15/25)
- seo-spam-free-search-engine (15/25)
- solo-founder-customer-onboarding-automator (16/25)

### Step 3: Create 20 cards (10 grill + 10 build pairs)

For each idea, create TWO cards:

**Grill card** (parent):
```
hermes kanban --board e2e-livetest-2 create \
  --title "Grill: <Idea Name>" \
  --assignee builder \
  --body "Score: <N>/25 | Slug: <slug>

A dossier exists at ~/vault/ventures/ideas/<slug>.md — read it first.

YOUR JOB — Grill ONLY. Do NOT build the prototype.

1. Read the dossier.
2. Grill with REAL PO using self-grill skill.
   - CRITICAL: env -u HERMES_KANBAN_TASK before launching PO
   - Persist grill output to ~/projects/<slug>/context/
   - Run validation: bash ~/.hermes-teams/shared-skills/self-grill/scripts/validate-grill-output.sh <slug>
3. Write decisions summary to ~/projects/<slug>/.context/grill/decisions.md
4. Copy dossier to ~/projects/<slug>/.context/dossier.md

Complete when grill validation passes.
NEVER put artifacts in ~/vault/ (Obsidian only)."
```

**Build card** (child):
```
hermes kanban --board e2e-livetest-2 create \
  --title "Build: <Idea Name>" \
  --assignee builder \
  --parents <grill-card-id> \
  --body "Slug: <slug>

The dossier and grill are DONE. Do NOT re-grill or re-research.
Read grill decisions at ~/projects/<slug>/context/

YOUR JOB — Build ONLY.

1. Write verify script at /tmp/verify-<slug>.py BEFORE building
   - MINIMUM 20 checks across 5 categories including RUNTIME EXECUTION
   - The verify script MUST execute the prototype as subprocess, check exit code 0.
   - Do NOT import uninstalled packages.
2. Build prototype in ~/projects/<slug>/prototype/
3. Write README.md (all 9 sections)
4. Update ~/vault/ventures/portfolio.md 'Awaiting Review' section.

NEVER put artifacts in ~/vault/ (Obsidian only)."
```

**IMPORTANT:** Create the build card with `--parents <grill-card-id>` so it auto-promotes from todo → ready when the grill completes. This creates the 2-card chain.

### Step 4: DO NOT manually create via CLI

Use the `kanban_create` tool instead of CLI commands — it works across all terminal backends and handles the parent-child linking properly:

```python
# Use kanban_create tool (not hermes kanban CLI)
kanban_create(
    title="Grill: Dockerless CI Verification Service",
    assignee="builder",
    board="e2e-livetest-2",
    body="Score: 19/25 | Slug: dockerless-ci-verification-service\n..."
)
# Then create build card with parents=[grill_task_id]
kanban_create(
    title="Build: Dockerless CI Verification Service",
    assignee="builder",
    board="e2e-livetest-2",
    parents=[grill_task_id],
    body="Slug: dockerless-ci-verification-service\n..."
)
```

### Step 5: Let it run. Do NOT interfere.

The dispatcher picks up cards when slots are free. With `max_in_progress_per_profile: 3`, up to 3 workers run concurrently. The pipeline is autonomous:

- Grill cards start → worker reads dossier → launches PO via self-grill RPC → grills across branches → validates → completes
- When grill completes → build card auto-promotes to ready → dispatcher picks it up → worker reads decisions → builds prototype → writes verify script → completes

**Your role is OBSERVER:** Monitor with `kanban_list` every 30-60 min. Do NOT manually build, answer questions, or intervene.

### Step 6: Monitor (passively)

Check progress without interfering:

```bash
# Count completed cards
hermes kanban --board e2e-livetest-2 list --status done | wc -l

# Check what's running
hermes kanban --board e2e-livetest-2 list --status running

# Check grill decision depth (for still-running grills)
grep -rh "Lock D" /tmp/grill-*/context/*.md 2>/dev/null | wc -l
```

**CRITICAL — Do NOT use sleep timers with notify_on_complete=true!**
In the previous run, 50+ stale sleep timers fired as notifications long after the batch completed. Instead:
- Use `process(action='poll')` manually
- Or use `watch_patterns` on a long-lived process
- Or just check `kanban_list` periodically without background timers

### Step 7: When all 20 cards are done — analyze and report

Independently verify all 10 prototypes:

```bash
# Check each prototype exists and runs
cd ~/projects/<slug>/prototype/
python3 <main>.py --help  # or open index.html
ls -la

# Check verify script exists
ls /tmp/verify-<slug>.py

# Count grill decisions per idea
grep -rh "Lock D" ~/projects/<slug>/context/*.md | wc -l
```

Report:
- How many pairs completed (target: 10/10)
- Grill depth per idea (decisions, branches)
- Build quality (verify pass/fail, runtime checks present)
- Any crashes, stalls, or issues
- Active time per idea (not wall-clock — actual compute time)

## Expected Behavior

- Grills take 2-3 hours active time per idea (30-100+ decisions depending on complexity)
- Builds take 7-15 minutes each
- 3 concurrent slots means 3 grills running at once
- Total batch: ~8-12 hours wall-clock (3 waves of ~3-4 grills each)
- Deep grills (100+ decisions) are NORMAL — do not cap them
- The grill system has NO decision cap — this is by design

## What NOT to Do

- Do NOT manually build prototypes — the workers do that
- Do NOT use sleep timers with notify_on_complete=true
- Do NOT interfere with running workers
- Do NOT reuse ideas from the previous livetest (listed above)
- Do NOT put artifacts in ~/vault/ (Obsidian only)
- Do NOT create the e2e-livetest-2 board before switching to it

## Skills to Load

The new builder session should load these skills before starting:
1. `skill_view(name='self-grill')` — the grill engine
2. `skill_view(name='grill-rpc-ops')` — how to launch PO sessions
3. `skill\_view(name='venture-prototype')` — how to build prototypes
4. `skill_view(name='pipeline-operations')` — how to run the pipeline
5. `skill_view(name='prototype-verification')` — how to verify prototypes

## Previous Livetest Results (for comparison)

| # | Idea | Decisions | Build Time | Status |
|---|------|-----------|------------|--------|
| 1 | SMB Cross-Platform Data Sync | 82 | ~7 min | DONE |
| 2 | AI Coding Flow-State Tool | 54 | ~7 min | DONE |
| 3 | Agency Reporting Data Aggregation | 50 | ~5 min | DONE |
| 8 | Code-Reading-First IDE | 116 | ~8 min | DONE |
| 10 | The Log is the Agent | 478 | ~9 min | DONE |

Median grill depth: ~55 decisions. Build time: 7-9 min median. All 10 completed successfully.

## Key Files

- Idea bank: `~/vault/ventures/idea-bank.md`
- Dossiers: `~/vault/ventures/ideas/<slug>.md`
- Portfolio: `~/vault/ventures/portfolio.md`
- Builder config: `~/.hermes-teams/startup/profiles/builder/config.yaml`
- Self-grill skill: `~/.hermes-teams/shared-skills/self-grill/`
- Pipeline ops skill: `~/.hermes-teams/startup/profiles/builder/skills/software-development/pipeline-operations/`
- Verify template: `~/.hermes-teams/startup/profiles/builder/skills/software-development/venture-prototype/references/verify-script-template.md`
- Previous livetest reference: this file
