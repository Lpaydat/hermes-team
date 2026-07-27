---
name: project-kickoff
description: "The PO's playbook for taking a new project from idea discussion through spec to routed architect work. Use when the user brings a new project idea, wants to migrate an existing system, or says 'let's build X'. Covers the full sequence: discuss → spec → architect gate → tickets, including the technique of pulling old domain models from source before spec-writing for migrations."
---

# Project Kickoff

You own the flow from "the user has an idea" to "work is routed to specialists." This skill covers the full sequence and the techniques that make each step solid.

## When to load this — LOAD IMMEDIATELY, not after discussion

- User brings a new project idea ("I want to build X")
- User wants to migrate an existing system ("migrate from X to Y")
- User says "let's start a new project" or "set this up"
- User says "let's discuss" + any build/migrate verb ("I want to migrate and add new features")
- You've just finished a grilling/architecture discussion and need to formalize it

**Critical failure mode (real session, 2026-07-26):** The user said "I want to migrate and add new features" and "let's discuss first." The PO discussed architecture for 8 turns, felt confident, then loaded `to-spec` directly and wrote a 19KB spec — WITHOUT loading this skill and WITHOUT grilling. The user caught it ("I notice that you don't grill me"). The retrofit grill surfaced 19 critical decisions the spec was missing (disaster recovery, debt sync conflicts, money operation validation, session management, price rounding, concurrent order editing, FIFO allocation). The lesson: **the moment the user says anything about building, migrating, or changing architecture, load this skill BEFORE responding.** Not after discussion. Not when you reach for to-spec. Immediately.

**The to-spec tension:** The shared `to-spec` skill says "no interview, just synthesis" — it actively discourages grilling. If you load `to-spec` directly for a new project, its instruction overrides your grill gate because it's the skill in play. The fix: for new projects/migrations, always go through this skill's pipeline (Discuss → Grill → Spec), never jump to `to-spec` directly. The `to-spec` "no interview" instruction is correct for SYNTHESIS of an already-grilled conversation — it's wrong as an entry point for un-grilled ideas.

## The pipeline

```
DISCUSS → GRILL → SPEC → ARCHITECT GATE → TICKETS → DISPATCH
         (grilling)  (to-spec)  (design card)   (to-tickets)  (dev-dispatch)
```

### Step 1: Discuss

Ask the user about the three questions that change architecture:
1. **Hardware** — what devices, what peripherals (printers, scanners), what connection types
2. **Distribution** — internal tool vs product, single-tenant vs multi-tenant
3. **Scale** — how many users/devices, expected growth

Be direct. State recommendations as decisions, not menus. This user HATES unnecessary complexity — when one path is obvious, say so and move on. Don't present options when the answer is clear.

**Completion criterion:** you can state the problem, the constraints, and the target architecture in 2-3 sentences.

### Step 2: Grill (NON-NEGOTIABLE — do not skip to spec)

**This is where the pipeline most commonly breaks.** You discuss architecture with the user, they give sensible answers, you feel confident, and you move to spec WITHOUT grilling. Discussion feels like enough — it isn't. Specs written from unchallenged discussion contain holes that surface during implementation — when they're 10x more expensive to fix.

Discussion is NOT grilling. Discussion is "here are options, what do you think?" Grilling is adversarial: you find the concrete scenario where the user's answer breaks, show them the breakage, and keep pushing until the decision holds under stress. The difference is:
- Discussion: "PWA or native?" → "PWA" → move on
- Grilling: "You said PWA, but here's a scenario where a PWA can't access the receipt printer. What's your plan?" → keep pushing until resolved

Load the `grilling` skill and work through every architecture decision made in Step 1. For each decision, ask: "what happens in the worst case?" and don't accept the first answer if a stress scenario can break it.

**Stress-test every decision against these categories** (see `references/grill-stress-categories.md` for the full checklist with examples):
- Single points of failure (what if X dies?)
- Data loss (what if two devices write simultaneously?)
- Money safety (can a sync conflict corrupt a balance? Is rounding correct?)
- Compliance (tax receipts, VAT, legal record-keeping)
- Offline/degraded operation (how long can devices work without the server?)
- Physical workflow edge cases (scanner types, printer range, shared devices, barcode UX)
- **Inventory and stock reality** (does the store actually track stock counts? Does the old model have a quantity field?)
- **Debt and credit workflows** (partial payment, FIFO allocation, late-syncing debt)
- **Pricing model reality** (single price? dual pricing like wholesale/retail? bulk discounts? The old model's single `price_per_unit` field may hide a multi-price reality — ask the owner, don't assume)

**Completion criterion:** every architecture decision has been challenged with at least one concrete failure scenario and either held or changed. The grill transcript gets pasted into the architect's design card in Step 4.

**If you find yourself about to run `to-spec` without a grill transcript, STOP.** Run the grill first. This is the most common and most damaging shortcut in the pipeline — it happened in a real session, the user caught it, and it resulted in a spec missing 10+ critical edge cases (disaster recovery, debt sync conflicts, money operation validation, session management, price rounding). The retrofit grill took longer than doing it upfront would have.

### Step 3: Write the spec

Load `to-spec`. Verify a grill transcript exists first — `to-spec` must refuse to run without one. Write to `<project-dir>/.driver/spec.md` (for multi-doc projects) or `<project-dir>/PRD.md`.

**Priority pitfall:** `bd create --priority` rejects words like "high"/"medium"/"low". Use `P0`-`P4` (e.g. `--priority P1`). This hard-fails the command.

**For migrations — pull the old domain model FIRST.** Before writing a single line of spec, fetch the existing system's data models from source. This makes the spec 10x better — you can map every old field to its new equivalent and include a concrete migration map.

```bash
# Fetch model files from GitHub
gh api repos/<owner>/<repo>/contents/<path>/models/product.py --jq '.content' | base64 -d
gh api repos/<owner>/<repo>/contents/<path>/interfaces/product.ts --jq '.content' | base64 -d
```

Record the old → new field mapping as a table in the spec's Implementation Decisions section. This gives the architect and builder the full picture without them needing to read the old codebase.

**Completion criterion:** spec published as a beads epic with `ready-for-agent` label, spec.md in the repo.

### Step 4: Architect gate (BEFORE tickets)

If the project involves ANY technical decisions (stack, data model, sync strategy, deployment), insert a design step before cutting tickets. Do NOT run `to-tickets` directly — the tickets need ADRs to cite.

Create a design card for the architect (`assignee: architect`) with:
- **Spec link** — path to the spec
- **Context summary** — paste key decisions, constraints, quotes (the architect doesn't have your conversation)
- **Grill transcript** — paste the stress scenarios that were resolved during grilling (Step 2). The architect needs to know what was tested and what held.
- **Settled decisions** — explicitly list what was decided in discussion so the architect doesn't re-litigate
- **Open technical questions** — anything you couldn't answer during grilling
- **Stakes** — `low` / `standard` / `high` (high = revenue/safety/hard-to-reverse)

Wait for the architect to complete. Read the design output (design doc + ADR series). Surface any gate cards for the user to approve before synthesis.

**Critical failure mode — gate card auto-resolution (real session, 2026-07-26):** The architect surfaced 5 product-ambiguous decisions as a gate card assigned to `product-owner`. A background PO session auto-resolved ALL 5 in 3 minutes, claiming to have "independently verified" each against the design docs — while the user was asleep. The user had to catch this. The owner OVERRIDDEN 2 of the 5 auto-approved decisions when actually consulted (offline debt payments, dual pricing).

**Rule:** Gate cards are owner decisions, not PO decisions. When the architect assigns a gate card to `product-owner`, the PO's job is to SURFACE it to the human (comment, message, block) — NOT to resolve it. The PO profile running as a dispatched worker has no authority to make product decisions on the user's behalf. If you see a completed gate card that was resolved by a `product-owner` worker run (not the live human), treat its decisions as UNVERIFIED and re-present them to the user.

**How to check:** Gate cards assigned to `product-owner` that completed via a dispatched worker run (check `kanban_show` runs — if the run profile is `product-owner` and completed in minutes, it was auto-resolved). The live human session is YOUR current session — if you didn't resolve it interactively, it was auto-resolved.

**Completion criterion:** architect design card created and assigned, with enough context that the architect can work autonomously. Gate cards surfaced to the human, NOT auto-resolved.

### Step 5: Setup project infrastructure

Do this in parallel with or right after the spec:

```bash
# 1. Create the kanban board
hermes kanban boards create <slug>

# 2. Create the project directory + git + beads
mkdir -p ~/projects/<slug>
cd ~/projects/<slug>
git init
bd init

# 3. Create .driver/ steering files
mkdir -p .driver
# Write goal.md, spec.md, progress.md, gaps.md, decisions.md

# 4. Switch to the new board
hermes kanban boards switch <slug>

# 5. Register the project in active-projects.json (CRITICAL — don't forget)
# Add {name, path, board} to ~/.hermes-teams/startup/active-projects.json

# 6. Create GitHub repo and push (if the project should have a remote)
gh repo create <owner>/<slug> --private --description "<desc>" --clone=false
git remote add origin git@github.com:<owner>/<slug>.git
git add -A && git commit -m "feat: initial project scaffold"
git push -u origin master
gh repo edit <owner>/<slug> --default-branch master
```

**Pitfall (real session, 2026-07-27):** Forgetting to register the project in `active-projects.json`. The board was created, the architect card was created — but the workflow engine only scans boards listed in `active-projects.json`. Without registration, the dispatcher may not reliably pick up cards on the new board. Always add the entry after creating the board.

**CRITICAL — active-projects.json is a dispatch trigger, not just a scanner entry (real session, 2026-07-27):** The moment you register a project in `active-projects.json`, the workflow engine scanner begins checking its beads every tick. If ANY beads have the `ready-for-agent` label, the engine immediately creates dispatch cards — which the PO auto-works into tech-lead cards — which the builder picks up and starts writing code. This happens even if the design phase isn't complete, even if gate cards haven't been resolved by the human, even if the spec was just updated.

The correct sequencing is:
1. Create the board
2. Create beads — but **do NOT add `ready-for-agent` label until design is finalized and the user has approved**
3. Run architect design + resolve gate cards with the human
4. Apply owner decisions to design + ADRs
5. **Only now**: add `ready-for-agent` to beads AND register in `active-projects.json`

In a real session, registering the project while beads still had `ready-for-agent` (from an earlier spec iteration) caused the scanner to immediately dispatch builder work. The builder scaffolded React+Vite in the repo root instead of `frontend/` (the monorepo structure wasn't in the beads), and created 4 worktrees against a stale spec — before the owner had even reviewed the gate card decisions.

**If you need to register the project early** (e.g., so the architect card gets dispatched), either:
- Remove `ready-for-agent` from all beads until design is finalized, OR
- Create the beads AFTER design completion (defer Step 6 until Step 4 is done)

**Matrix chain routing failure (real session, 2026-07-27):** Even when the PO dispatch card is worked correctly, the dispatched PO run may use `kanban_chains` (the matrix topology: dev→verifier pairs) instead of `kanban_create` with `assignee: tech-lead`. This spawns `developer` cards directly — bypassing tech-lead routing entirely. The `developer` profile is a separate role that should NOT receive dispatched beads. If this happens, code will be written into the repo root (not the monorepo structure) and worktrees will accumulate. See `references/premature-dispatch-recovery.md` for the full cleanup procedure: kill processes → remove worktrees → reset repo → archive cards → strip `ready-for-agent` labels.

**Root cause of matrix chain routing (diagnosed 2026-07-27):** The workflow engine (`workflow-engine.py`) creates the PO dispatch card WITHOUT a `--skills dev-dispatch` flag — it only mentions the skill name in prose (`"Run dev-dispatch"`). Prose instructions to an LLM are suggestions, not enforcement. The PO reads "dispatch beads" and reaches for the most powerful tool available (`kanban_chains`) instead of loading a skill it was merely told about in text. This is a tool-level enforcement gap — the same principle the user taught about grill gates: prose is a suggestion, skill loading is enforcement. The fix is to add `--skills dev-dispatch` to the workflow engine's dispatch card creation. Until that patch lands, the PO dispatch path is unreliable.

**Pitfall:** Switch to the project's board BEFORE creating kanban tasks. `kanban_create` writes to the currently active board. If you're on `hermes-hq` when you create the architect card, it lands on the wrong board.

**Pitfall:** `bd init` doesn't take `--yes`. Just run `bd init` directly.

**For migrations — keep old repos as read-only reference:** Never modify the old repos directly. Create a new repo for the new system. The old repos stay frozen as the source of truth for the migration script and as reference for old UI patterns. If the old and new are completely different stacks, mixing them in the same repo is a mess.

**For monorepo projects:** If the project has both frontend and backend (common for full-stack apps), use a monorepo structure rather than separate repos. See `references/monorepo-setup.md` for the directory structure and .gitignore patterns.

**Pitfall (real session, 2026-07-27):** If you set up a monorepo structure (`frontend/`, `backend/`, `scripts/`) but the beads issues don't explicitly state the directory layout, the builder will scaffold code in the repo root instead of `frontend/`. The builder reads the bead body as the spec — if it says "React 19+Vite PWA scaffold" without "in `frontend/`", the code lands at root. Always include the monorepo directory path in EVERY bead description: "React 19+Vite PWA scaffold **in `frontend/`**" and "PocketBase schema + hooks **in `backend/`**".

### Step 6: File the spec as a beads epic

```bash
bd create \
  --title "<descriptive title>" \
  --type epic \
  --priority P1 \
  --label "ready-for-agent" \
  --body "$(cat .driver/spec.md)"
```

## Pitfalls

- **Not loading this skill at all.** The most common and most damaging failure. The user says "I want to build X" and the PO goes straight to discussion → to-spec without loading this skill. Without this skill's pipeline, there is no grill gate. This happened in a real session (2026-07-26) — the user caught the missing grill, and the retrofit cost more than doing it upfront. Load this skill the moment you see build/migrate/change intent.
- **Loading this skill but skipping to Step 3 (spec).** The pipeline is DISCUSS → GRILL → SPEC. Jumping from discuss to spec feels faster but produces a spec full of holes. The grill (Step 2) is the single most valuable step in this pipeline — it's where 19+ decisions get stress-tested in a real session.
- **Confusing discussion with grilling.** "Here are the options, which do you want?" is discussion. "You said X, but here's a scenario where X loses money — what's your plan?" is grilling. Only the second produces a spec that holds up.
- **Running to-tickets without the architect gate.** For any project with technical decisions, the tickets need ADRs to cite. Skipping the architect means the builder makes architecture decisions — that's not their job.
- **bd create --priority with words.** Use `P0`-`P4`, not "high"/"medium"/"low". Hard-fail, not silent default.
- **Wrong active board.** `kanban_create` targets the active board. Switch to the project board first, or the architect card lands on `hermes-hq`.
- **Writing the spec blind (for migrations).** Always pull the old domain model from source first. The spec must include a concrete old → new field mapping table.
- **Re-litigating settled decisions in the architect card.** The architect doesn't have your discussion transcript. Explicitly list what's already decided so they validate the architecture around it, not reopen it.
- **Using `kanban_chains` for bead dispatch.** The PO dispatch card says "Run dev-dispatch." When you work that card, use `kanban create --assignee tech-lead` — one call per bead. Do NOT use `kanban_chains` (the matrix topology). Using it spawns `developer` cards directly, bypassing tech-lead, and code lands in the repo root instead of the monorepo structure. This happened in a real session (2026-07-27) — the `dev-dispatch` skill is protected from curation so the enforcement lives here. The dispatch is a 5-line task; reaching for a more powerful tool overcomplicates it.
- **Auto-resolving gate cards as a dispatched PO worker.** When the architect assigns a gate card to `product-owner`, background PO sessions resolve them in minutes without consulting the human. The human catches it later and overrides. Gate cards are HUMAN decisions — your job as a dispatched PO worker is to surface them (block, comment), not resolve them.
- **Bypassing skills entirely in CLI conversation mode (real session, 2026-07-27).** The PO ran `to-spec` zero times and `to-tickets` zero times — wrote the spec by hand and created beads ad-hoc. The skills exist, SOUL.md references them by name, but skills are opt-in via `skill_view`, and in conversation flow the PO doesn't reach for them. This is the CLI-mode equivalent of the dispatched-worker `dev-dispatch` bypass (where the PO used `kanban_chains` instead of loading the skill). The root cause is the same: skills are suggestions unless something forces them to load. In CLI mode there IS no `--skills` flag — you must consciously load `skill_view to-spec` and `skill_view to-tickets` at the right points in the pipeline. If you find yourself writing a spec by hand or creating beads with `bd create` directly, STOP and ask: "should `to-spec` or `to-tickets` be doing this?" The skills enforce structure (user story format, tracer-bullet decomposition, blocking edges, user approval gate) that manual work skips.
- **SOUL.md contains a false enforcement claim (verified 2026-07-27).** SOUL.md line ~105 states: "The `to-spec` skill enforces this at the tool level: it must refuse to write a spec if no grilling has occurred in the current conversation." This is false. Grepping the actual `to-spec` SKILL.md for grill/enforce/refuse/gate keywords returns zero matches. The skill is a read-only symlink to the Matt Pocock shared-skills pack (chmod 444) — it cannot be patched to add enforcement, and it never had any. The false claim is worse than no claim: it creates a false sense of security, making the PO believe a safety net exists when it doesn't. The real enforcement mechanism is this skill's pipeline discipline (Steps 1-4) plus `disabled_toolsets` in config.yaml (see below). **Action needed (not a skill edit):** SOUL.md line ~105 should be corrected to state the truth — enforcement is a design goal, not a reality, and the PO must self-enforce by loading skills at the right pipeline steps.
- **Config-level enforcement is the only proven mechanism (confirmed by user, 2026-07-27).** The user's principle: "rather than blocking it by words to ban from some actions, if that actions can be ban in config, that's much better." The PO config.yaml already uses `disabled_toolsets` to physically remove browser/delegation/web/kanban_chains — and the config comment says: "Prompting proved unreliable; PO reasoned around it. Tool removal is the only reliable enforcement." For any role boundary you want to enforce, prefer adding the toolset to `disabled_toolsets` over writing "never do X" in SOUL.md. Prompting is a suggestion; tool removal is enforcement. See `references/skill-enforcement-layers.md` Layer 0 for the full design.
- **Duplicating spec content across `.driver/spec.md` and the beads epic body (real session, 2026-07-27).** The user questioned why `.driver/spec.md` exists separately when the beads epic IS the published spec. The `.driver/` directory was a self-invented steering structure; beads is the system's source of truth. The spec should live in the beads epic. If you also write `.driver/spec.md`, it will drift from the beads epic as updates happen. Prefer: spec in beads epic (source of truth), design doc + ADRs in `docs/` (readable artifacts), `.driver/` reduced to a pointer README or eliminated entirely. If the project needs a local spec copy for agent context, write it ONCE from `to-spec` and never update it separately — always update the beads epic first, then regenerate the local copy.
- **Dispatching the architect card BEFORE the grill is complete.** The pipeline is DISCUSS → GRILL → SPEC → ARCHITECT. If you create the architect card right after writing the FIRST spec (before or during the grill), the architect will run on the pre-grill version and produce a full design (design doc + ADR series, potentially thousands of tokens across a multi-agent council) that's based on the weaker, unchallenged spec. This happened in a real session (2026-07-26): the architect completed at 09:56, the grill ran 10:00-11:00, the spec was updated at 11:04 — the architect's entire 8-card council output had to be deleted and redone. Fix: the grill (Step 2) must COMPLETE and the spec (Step 3) must be FINALIZED before you create the architect card (Step 4). The architect card's body must reference the post-grill spec path explicitly. If you realize the spec was updated after dispatch, check whether the architect completed against the old version before reading its output.

## User preference: durable rules go in SOUL.md, not memory

When the user corrects a behavior or workflow that should persist across machines, update **SOUL.md** (the profile identity file), not memory. Memory is machine-local DB state — it's dynamic and hard to port when deploying to a new machine. SOUL.md lives in the profile directory and travels with it. Identity-level rules (like "always grill before spec") belong in SOUL.md's SPECIALTY section (which the Constitution allows you to edit). Session-level facts (who the user is, current environment state) belong in memory.

## References

- `references/soul-refactor-design.md` — structural analysis of all 16 profile SOUL.md files (identity vs instruction split), design for making SOUL.md identity-only with all instructions in skills. Includes per-profile refactor scope table and the "refactor before enforcement" sequencing decision.
- `references/migration-domain-model-extraction.md` — technique for pulling old domain models from GitHub and building the old → new field mapping table
- `references/grill-stress-categories.md` — 9-category checklist for the grill gate (single points of failure, data loss, money safety, compliance, offline, physical workflow, inventory, debt, pricing model) with concrete examples from a real POS migration grill
- `references/local-first-patterns.md` — 19 concrete architecture patterns for multi-device local-first apps (hybrid sync, opt-in realtime collaboration, append-only ledger, customer-level debt balance, soft lock for closing, VAT toggle trap, printer reconnection with cold-start limitation, backup/DR, optimistic concurrency control, three-state sync badges, money offline fallback, auto-lock with PIN, order item snapshot immutability, timestamp receipt ID, delta polling, rolling sync window, business day rollover, dual pricing wholesale/retail, debt allocation strategies FIFO+smallest-first)
- `references/monorepo-setup.md` — directory structure, .gitignore patterns, GitHub repo creation, and old-repo-as-reference workflow for full-stack monorepo projects
- `references/premature-dispatch-recovery.md` — full cleanup procedure when the workflow engine auto-dispatches builder work before design is complete (kill processes, remove worktrees, reset repo, archive cards, strip ready-for-agent labels)
- `references/skill-enforcement-layers.md` — enforcement design for making the PO follow the skill pipeline: Layer 0 config-level tool removal (PROVEN in production), Layers 1-4 stamps/engine-gate/plugin/audit (design only)
