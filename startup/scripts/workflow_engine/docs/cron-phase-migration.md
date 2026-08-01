# Cron Phase Migration — Old `workflow-engine.py` → Engine Templates

Analysis of every function/phase in the old cron
(`~/.hermes-teams/startup/profiles/product-owner/scripts/workflow-engine.py`,
699 lines) mapped to the new declarative engine
(`scripts/workflow_engine/`, JSON templates).

**Goal:** decide what becomes a JSON template, what stays imperative, and in
what order to migrate. Each templatable phase below includes actual JSON that
would drop into `templates/`.

---

## TL;DR — Migration Map

| # | Old cron function | Lines | Trigger | Templatable? | Risk | Migrate order |
|---|---|---|---|---|---|---|
| 1 | `phase_bead_sync` | 81–128 | n/a — data sync | ❌ **No** — imperative data sync | n/a | **keep as code** |
| 2 | `phase_dispatch` + `dispatch_*` helpers | 134–330 | `bead_ready` | ⚠️ **Partial** — routing logic is complex | High | 4th |
| 3 | `phase_human_escalations` | 336–391 | `bead_ready` (+ label filter) | ✅ **Yes** | Low | 2nd |
| 4 | `scan_board` | 397–493 | `card` status scan / scheduled | ⚠️ **Partial** — needs `scheduled` trigger | Medium | 3rd |
| 5 | `phase_qa_trigger` | 499–639 | `card_completed` | ✅ **Yes** (already migrated) | Low | **1st — DONE** |

**Verdict:** 1 phase fully migrated (QA), 1 fully templatable (human
escalation), 2 partially templatable with engine extensions (dispatch,
scanner), 1 must stay imperative (bead-sync). Details below.

---

## Phase 1: `phase_bead_sync` — ❌ CANNOT be templated

### What it does (lines 81–128)

A **data sync** between two stores, not a workflow:

1. **`STATUS_MAP` (L81–87):** maps kanban card status → bd bead status
   (`ready`/`running` → `in_progress`, `blocked` → `blocked`, `done` →
   `closed`, `archived` → `open`).
2. **`read_kanban_card_status` (L89–100):** opens the board's `kanban.db`
   directly with `sqlite3`, looks up the card by `idempotency_key = bead-{id}`.
3. **`phase_bead_sync` (L102–128):** for every bead from `bd list --all`:
   - skips `gt:slot` beads (line 113)
   - reads the card status, maps it via `STATUS_MAP`
   - if current bead status ≠ target and not already `closed`, calls
     `bd update <id> -s <status>`
   - returns a list of change strings.

### Why it can't be templated

This is **state reconciliation between two data stores**, not a multi-step
agent pipeline. The engine's primitives are:
- *create a card* → *wait for an agent* → *read metadata* → *advance*.

Bead-sync does none of that. It is a poll-and-patch loop with no agent in the
loop, no card to wait on, no output schema to validate. Forcing it into a
template would mean a node with `profile: none` that runs shell commands —
which is just imperative code wearing a JSON costume.

**Risk if force-templated:** High. The engine has no concept of "run a sync
with no agent." You'd either add a `system` node type (scope creep) or fake it
with a throwaway profile card (fragile, 1-min latency per sync).

### Recommendation

**Keep as imperative code** — ideally extracted into a standalone
`bead_sync.py` script invoked by cron, separate from the engine tick. This
matches the engine's own design decision documented in `README.md` → *Design
Decisions → "Why kanban-only (no beads)?"*:

> Bead-sync was fragile (5+ patches). Two stores = two failure modes. Kanban
> is the execution surface — the engine reads/writes kanban directly.

### Dependencies

None. Runs independently of the engine. **Migrate (extract) first** so the
remaining cron code is purely about card creation, which the engine can take
over.

---

## Phase 2: `phase_dispatch` — ⚠️ Partially templatable (High risk)

### What it does (lines 134–330)

The most complex phase. Multi-route dispatch:

1. **`card_exists_for_bead` (L134–145):** dedup — has a non-archived card with
   `idempotency_key = bead-{id}` already been created?
2. **`has_active_po_dispatch_card` (L147–160):** dedup — is there already an
   open `[dispatch]` card assigned to `product-owner`?
3. **`WAYFINDER_ROUTES` / `WAYFINDER_SKIP` (L166–173):** label-based routing
   table. `wayfinder:research` → `scout`, `wayfinder:task` → `ops`,
   `wayfinder:architecture` → `architect`. Skip `grilling`/`prototype`/`map`/
   `venture:brief` (HITL-substitute work, never headless-dispatched).
4. **`dispatch_wayfinder_ticket` (L175–241):** creates a routed card for one
   wayfinder ticket. **Branches by assignee:**
   - `architect` → body instructs ADR creation (gate posture, record in
     `docs/adr/`, cite by number, append to map's Decisions index).
   - others (`scout`, `ops`) → simpler investigate-and-comment body.
5. **`dispatch_bug_to_debugger` (L243–269):** routes a `bug` bead straight to
   `debugger`, bypassing the PO dispatch → tech-lead path.
6. **`phase_dispatch` (L271–330):** the orchestrator:
   - runs `bd ready --json`
   - skips `gt:slot`, epics, `WAYFINDER_SKIP` labels
   - skips beads that already have a card
   - routes bugs → debugger, wayfinder tickets → routed profile
   - remaining "normal" beads → **one** PO dispatch card (if no active one
     exists), body lists ready beads, instructs `dev-dispatch`.

### What trigger would replace it

`bead_ready` — the engine already supports this trigger
([README → Triggers → bead_ready](../README.md#bead_ready)):

```json
{"source": "bead_ready", "condition": {"type": "feature"}}
```

The bead ID flows in as `${trigger.bead_id}`.

### Why it's only *partially* templatable

The **trigger + single-card dispatch** is trivially templatable. But the old
cron's dispatch does **conditional multi-route dispatch** that the engine's
current trigger conditions can't fully express:

- **Label-based routing to different profiles** (`wayfinder:research` → scout,
  `wayfinder:architecture` → architect) — needs per-label condition matching.
  The engine's `bead_ready` condition supports `type` and `label` but not
  "route to profile X if label Y, else profile Z."
- **Bug detection heuristic** (line 295–298): checks `issue_type == "bug"` OR
  (`issue_type == "task"` AND any label contains "bug"). No template condition
  can express "label contains substring."
- **Wayfinder architect special body** (lines 187–215): a 25-line templated
  body with ADR protocol, `docs/adr/` path, map-append instructions. This *can*
  be a `body_template` with `${trigger.bead_id}` etc., but it's assignee-specific
  — you'd need separate templates per route.
- **"One PO dispatch card for all normal beads"** (lines 307–329): the old cron
  batches *all* non-routed ready beads into a single card. The engine's
  `bead_ready` trigger fires **one instance per bead** — fundamentally different
  cardinality. To replicate batching you'd need a `foreach` node that collects
  ready beads, but `foreach` iterates a list from a prior node's output, not
  from a trigger.

### What the JSON templates would look like

The realistic migration splits dispatch into **multiple templates**, one per
route, each with a `bead_ready` trigger filtered by label/type. The "batch PO
dispatch card" behavior is dropped in favor of per-bead routing (which is
arguably better — finer-grained, no single bottleneck card).

#### Template A — `bug-router.json` (bug → debugger)

```json
{
  "id": "bug-router",
  "name": "Bug Router — ready bug bead → debugger card",
  "description": "Replaces dispatch_bug_to_debugger. A ready bead typed 'bug' (or task+bug label) routes straight to debugger, skipping PO dispatch.",
  "trigger": {
    "source": "bead_ready",
    "condition": {"type": "bug"}
  },
  "nodes": [
    {
      "id": "fix",
      "profile": "debugger",
      "skill": "loops-engineering",
      "body_template": "## Bug ${trigger.bead_id} — ${trigger.title}\n\n${trigger.description}\n\n## Resolve protocol (run bd from ${trigger.project_dir})\n\nRun your loops-engineering doctrine. Diagnose, fix, verify. Close the bead with `bd close ${trigger.bead_id}` when done.",
      "output": {
        "schema": {
          "type": "object",
          "required": ["verdict"],
          "properties": {
            "verdict": {"type": "string", "enum": ["PASS", "FAIL"]},
            "commit_sha": {"type": "string"}
          }
        }
      }
    }
  ]
}
```

> **Gap:** The old cron's bug heuristic also catches `issue_type == "task"` with
> a "bug"-containing label. The engine's `bead_ready` condition matches `type`
> (issue_type) or `label` (exact), not "label contains 'bug'." Either (a) bd
> must normalize bug-typed tasks to `issue_type: bug`, or (b) the engine needs a
> `label_regex` condition. **Until then this template only catches true
> `issue_type == "bug"` beads** — a regression for mis-typed bugs.

#### Template B — `wayfinder-research.json` (wayfinder:research → scout)

```json
{
  "id": "wayfinder-research",
  "name": "Wayfinder Research Ticket → scout",
  "description": "Replaces the scout route of dispatch_wayfinder_ticket. A ready bead labeled wayfinder:research routes to scout for AFK investigation.",
  "trigger": {
    "source": "bead_ready",
    "condition": {"label": "wayfinder:research"}
  },
  "nodes": [
    {
      "id": "investigate",
      "profile": "scout",
      "skill": "web-research",
      "body_template": "## Wayfinder ticket ${trigger.bead_id} — ${trigger.title}\n\nMap: `${trigger.parent}` (the venture's wayfinding map — its Notes name the idea brief and prior decisions; read it with `bd show ${trigger.parent}`).\n\n${trigger.description}\n\n## Resolve protocol (run bd from ${trigger.project_dir})\n\n1. Investigate (AFK). Long artifacts go to a file; link them, don't paste.\n2. Record the resolution on the ticket: `bd comment ${trigger.bead_id} \"<answer + citation of your sources>\"`\n3. Append the decision to the map's Decisions-so-far index: read `bd show ${trigger.parent}`, rewrite its description via `bd update ${trigger.parent} --description=...` with the added line `- ${trigger.title} (${trigger.bead_id}) — <one-line gist>`.\n4. Complete this card with the answer as summary. Do NOT `bd close` the ticket yourself — bead-sync closes it when this card is done.",
      "output": {
        "schema": {
          "type": "object",
          "required": ["verdict"],
          "properties": {"verdict": {"type": "string", "enum": ["RESOLVED", "BLOCKED"]}}
        }
      }
    }
  ]
}
```

#### Template C — `wayfinder-architecture.json` (wayfinder:architecture → architect)

Same structure as B but `profile: "architect"`, `skill: "architect-gate"`
(or the ADR convention), and the **ADR-specific body** (gate posture,
`docs/adr/ADR-NNN`, map-append with ADR number). Body template (abbreviated;
full text from old cron lines 191–214):

```json
{
  "id": "wayfinder-architecture",
  "name": "Wayfinder Architecture Ticket → architect (ADR)",
  "description": "Replaces the architect route of dispatch_wayfinder_ticket. Decisions land as append-only ADRs per docs/agents/adr-convention.md.",
  "trigger": {
    "source": "bead_ready",
    "condition": {"label": "wayfinder:architecture"}
  },
  "nodes": [
    {
      "id": "decide",
      "profile": "architect",
      "skill": "architect-gate",
      "body_template": "## Wayfinder ticket ${trigger.bead_id} — ${trigger.title}\n\nMap: `${trigger.parent}`\n\n${trigger.description}\n\n## Resolve protocol — architecture (run bd from ${trigger.project_dir})\n\n1. Answer in gate posture: weigh the alternatives before deciding; every input to the decision needs a named, quotable source.\n2. Record the decision as an ADR in this venture repo under ${trigger.project_dir}/docs/adr/ per the ADR convention: next free ADR-NNN, one decision per file, header line `Introduced-by: ${trigger.bead_id}`, sections Decision / Context / Alternatives Considered / Consequences / Citations.\n3. Record the resolution on the ticket citing the ADR by number.\n4. Append the decision to the map's Decisions-so-far index.\n5. Complete this card with the decision gist as summary and metadata {\"adr\": \"ADR-NNN\", \"posture\": \"gate\"}. Do NOT `bd close` the ticket yourself — bead-sync closes it when this card is done.",
      "output": {
        "schema": {
          "type": "object",
          "required": ["verdict", "adr"],
          "properties": {
            "verdict": {"type": "string", "enum": ["RESOLVED", "BLOCKED"]},
            "adr": {"type": "string", "pattern": "^ADR-\\d+$"}
          }
        }
      }
    }
  ]
}
```

#### Template D — `dev-dispatch.json` (normal beads → PO dispatch card)

This is the **hardest** to template faithfully. The old cron creates **one** PO
card batching all non-routed ready beads and blocks if any active dispatch card
exists. The engine fires **one instance per bead**. Two options:

**Option D1 — per-bead PO card (drop batching):**

```json
{
  "id": "dev-dispatch",
  "name": "Ready bead → PO dispatch (per-bead)",
  "description": "Replaces the normal-bead path of phase_dispatch. Each ready bead (not bug, not wayfinder-routed) gets its own PO dispatch card. NOTE: changes cardinality from one-batch-card to per-bead cards.",
  "trigger": {
    "source": "bead_ready"
  },
  "nodes": [
    {
      "id": "po_dispatch",
      "profile": "product-owner",
      "skill": "dev-dispatch",
      "body_template": "## Ready bead to dispatch\n\n- `${trigger.bead_id}` — ${trigger.title}\n\nRun `dev-dispatch` to create tech-lead cards for this bead.",
      "output": {
        "schema": {
          "type": "object",
          "required": ["verdict"],
          "properties": {"verdict": {"type": "string", "enum": ["DISPATCHED", "BLOCKED"]}}
        }
      }
    }
  ]
}
```

> **Gap:** This trigger has **no label/type exclusion** — it would also fire for
> bugs and wayfinder tickets (which have their own templates). The engine would
> create duplicate cards unless either (a) `bead_ready` conditions gain
> `label_not` / `type_not` filters, or (b) the templates are ordered with
> exclusion logic. **The engine today does not support negative trigger
> conditions.** This is the single biggest blocker for dispatch migration.

**Option D2 — keep the batch card in imperative code:**

Leave the "batch all normal beads into one PO card" behavior as a small
imperative shim (it's ~20 lines), and only template the routed paths (bugs,
wayfinder). This is lower-risk and preserves current behavior exactly.

### Profile / skill per node

| Node | Profile | Skill |
|---|---|---|
| bug fix | `debugger` | `loops-engineering` |
| wayfinder research | `scout` | `web-research` |
| wayfinder architecture | `architect` | `architect-gate` |
| wayfinder task (ops) | `ops` | (profile default) |
| normal dispatch | `product-owner` | `dev-dispatch` |

### Dependencies (migration order)

- **Depends on:** nothing (it's the entry point). But it's high-risk, so migrate
  **last** after the engine proves itself on simpler phases.
- **Blocks:** nothing directly, but the QA loop (already migrated) and scanner
  feed off cards that dispatch creates.
- **Engine extension needed:** negative trigger conditions
  (`label_not_in`, `type_not`) to avoid duplicate dispatch across overlapping
  `bead_ready` templates. **Without this, do not migrate the normal-bead path.**

### Risk level: **High**

- Changes dispatch cardinality (1 batch card → N per-bead cards) unless D2.
- Bug-type heuristic regression (substring label match not supported).
- No negative trigger conditions → risk of duplicate cards.
- Wayfinder skip-list (`grilling`/`prototype`/`map`/`venture:brief`) has no
  template equivalent — these must be excluded or they'll get headless-dispatched
  (the old cron explicitly warns this must NEVER happen).

---

## Phase 3: `phase_human_escalations` — ✅ Fully templatable (Low risk)

### What it does (lines 336–391)

1. **`hq_ping_exists` (L338–351):** dedup — has a non-archived card with
   `idempotency_key = bead-human-{id}` already been created on the `hermes-hq`
   board?
2. **`phase_human_escalations` (L353–391):** for every bead with label `human`
   (`bd list --all --label human`):
   - skip closed beads
   - skip beads that already have an hq ping
   - create a card on **`hermes-hq`** board (cross-board!), assignee `default`,
     priority 10, title `[ESCALATION] human answer needed: ...`, body includes
     the bead description and the `bd human respond` command.

### What trigger would replace it

`bead_ready` with a label filter — **but the old cron uses `bd list --all
--label human`**, not `bd ready`. The `human` label can be on beads in any
status (open/in_progress/blocked), not just `ready`.

> **Gap:** The engine's `bead_ready` trigger runs `bd ready --json`, which only
> returns ready beads. A `human`-labeled bead that's `in_progress` would not
> trigger. **To template this faithfully, the engine needs either a
> `bead_list` trigger (runs `bd list --all --label X`) or the human-flag must
> be set to `ready` when applied.** The latter is the simpler fix — whoever
> tags `human` should also flip status to `ready`.

### What the JSON template would look like

Assuming the `human` label implies ready status (or engine gains a
`bead_list` trigger):

```json
{
  "id": "human-escalation",
  "name": "Human Escalation — human-flagged bead → operator HQ card",
  "description": "Replaces phase_human_escalations. A bead tagged 'human' gets a visible escalation card on the hermes-hq board so the operator sees it without relying on the escalating agent to ping. Idempotent per bead.",
  "trigger": {
    "source": "bead_ready",
    "condition": {"label": "human"}
  },
  "nodes": [
    {
      "id": "hq_ping",
      "profile": "default",
      "body_template": "## Human-flagged bead: ${trigger.bead_id}\n\n${trigger.description}\n\nAnswer with: `bd human respond ${trigger.bead_id}` (comments + closes the bead) from ${trigger.project_dir}. Board: ${trigger.board}.",
      "card_mode": "template"
    }
  ]
}
```

> **Gap (cross-board):** The old cron creates this card on the **`hermes-hq`**
> board, not the project board. The engine's `bead_ready` trigger fires on a
> project board and the node card is created on **that same board**. There is
> no template field today to say "dispatch this node's card to a different
> board." **This needs an engine extension: a `target_board` node field**, or
> the trigger must run against `hermes-hq` specifically. Without it, the
> escalation card lands on the project board where the operator may not look.

### Profile / skill per node

| Node | Profile | Skill |
|---|---|---|
| hq_ping | `default` | (none — operator-facing) |

### Dependencies (migration order)

- **Depends on:** engine support for `target_board` (cross-board card creation)
  OR accepting escalation cards on the project board.
- **Blocks:** nothing.
- **Migrate 2nd** — simple, single-node, low blast radius. Good second proof of
  the engine after QA.

### Risk level: **Low** (with the `target_board` gap acknowledged)

Single node, no iteration, no conditional routing. Main risk is the
cross-board / trigger-source gap above.

---

## Phase 4: `scan_board` — ⚠️ Partially templatable (Medium risk)

### What it does (lines 397–493)

The **blocked-task escalation scanner**. For each project board:

1. **`scan_board` (L406–493):** queries `kanban.db` directly for all
   `status = 'blocked'` tasks.
2. For each blocked task:
   - skip `default`/empty assignee (L422–423)
   - skip if a `HUMAN_REQUIRED` comment exists (L426–429)
   - **Check if escalation was resolved** (L433–444): look for a `done` task
     titled `[ESCALATION] ...{task_id}...` whose run summary starts with
     `RESOLVED:`. If found → `kanban unblock <task_id>` (auto-unblock).
   - **Skip if active escalation exists** (L447–452): non-done/archived task
     with title matching `[ESCALATION] ...{task_id}...`.
   - **Create escalation** (L454–491): look up `ESCALATION_CHAIN` for the
     assignee's superior (`developer`→`tech-lead`, ..., `product-owner`→None).
     If no superior → post a `HUMAN_REQUIRED` comment. Else create an
     `[ESCALATION] Resolve block on {task_id}` card assigned to the superior,
     body includes the block reason from `task_events`.

### What trigger would replace it

This is the hardest fit. The old cron is a **scheduled poll** — it scans for
blocked tasks every minute. The natural engine trigger is **`card` status
change**, but:

- The engine has a `card_completed` trigger, **not a `card_blocked` trigger.**
- The scanner's logic is stateful: it checks for *prior* escalation cards,
  checks for *resolution*, and auto-unblocks. This is reconciliation logic, not
  "when X happens, start a workflow."

Two migration paths:

#### Path A — `card_blocked` trigger (needs engine extension)

Add a new trigger source `card_blocked` that fires when a card transitions to
`blocked` status. Template:

```json
{
  "id": "blocked-escalation",
  "name": "Blocked Task Escalation — blocked card → superior profile",
  "description": "Replaces scan_board. When a card goes blocked (and isn't already HUMAN_REQUIRED or escalated), create an escalation card for the assignee's superior. Auto-unblocks when the escalation resolves with RESOLVED:.",
  "trigger": {
    "source": "card_blocked",
    "condition": {
      "assignee_not": "default",
      "status": "blocked"
    }
  },
  "nodes": [
    {
      "id": "escalate",
      "profile": "tech-lead",
      "skill": "adversarial-review",
      "body_template": "## Blocked: ${trigger.card_id}\n\n**Assignee**: ${trigger.assignee}\n**Reason**: ${trigger.block_reason}\n\n1. `kanban_show(task_id=\"${trigger.card_id}\")`\n2. Resolve → comment on blocked task → complete with `RESOLVED: ...`\n3. Can't resolve → block this card (needs_input)",
      "output": {
        "schema": {
          "type": "object",
          "required": ["verdict"],
          "properties": {
            "verdict": {"type": "string", "enum": ["RESOLVED", "NEEDS_INPUT"]}
          }
        }
      }
    },
    {
      "id": "unblock",
      "type": "task",
      "profile": "system",
      "body_template": "Auto-unblock ${trigger.card_id} after escalation resolved.",
      "depends_on": ["escalate"],
      "condition": "${nodes.escalate.output.verdict} == 'RESOLVED'"
    }
  ]
}
```

> **Gaps (significant):**
> 1. **No `card_blocked` trigger exists.** Must be added to the engine.
> 2. **`profile: "system"`** — the `unblock` node is a no-op shell action (run
>    `kanban unblock`). The engine has no system/system-action node type. This
>    is the same problem as bead-sync: not agent work.
> 3. **`assignee_not` condition** — the trigger needs negative matching (skip
>    `default` assignee). Not currently supported.
> 4. **Escalation chain is dynamic** — `developer`→`tech-lead`,
>    `tech-lead`→`product-owner`. A single template hard-codes one target
>    profile. You'd need **one template per source-assignee** (5 templates) or
>    engine support for dynamic profile resolution from a lookup table.
> 5. **Dedup against prior escalations** — the old cron checks for existing
>    `[ESCALATION]` cards by title pattern. The engine's idempotency is
>    key-based (`wf:<instance>:<node>`), which would work *if* the trigger
>    dedup key incorporates the blocked card ID. Needs verification.
> 6. **Auto-unblock on resolution** — the old cron actively unblocks the
>    original task when it sees a `RESOLVED:` summary. The engine template
>    above tries to model this as a node, but it's really an imperative side
>    effect.

#### Path B — keep as scheduled imperative code

`scan_board` is genuinely **reconciliation logic** (find blocked → check if
resolved → unblock; find blocked → check if escalated → escalate). It's closer
to bead-sync than to a workflow. Keeping it as a small imperative script that
runs on cron is defensible and lower-risk.

### Profile / skill per node

| Node | Profile | Skill |
|---|---|---|
| escalate (from developer/debugger/verifier/qa) | `tech-lead` | `adversarial-review` |
| escalate (from tech-lead) | `product-owner` | `dev-dispatch` / default |
| escalate (from product-owner) | *(none — HUMAN_REQUIRED)* | n/a |

### Dependencies (migration order)

- **Depends on:** engine support for `card_blocked` trigger (new) **and**
  dynamic profile resolution **and** a system-action node type. All
  non-trivial engine extensions.
- **Blocks:** nothing.
- **Migrate 3rd** (after human-escalation proves cross-board / trigger patterns)
  — but only if the engine extensions land. Otherwise defer indefinitely.

### Risk level: **Medium-High**

The auto-unblock reconciliation and the dynamic escalation chain don't map
cleanly to declarative templates. High risk of subtle behavior change
(duplicate escalations, failure to auto-unblock, wrong superior targeted).

---

## Phase 5: `phase_qa_trigger` — ✅ Already migrated (Low risk)

### What it does (lines 499–639)

1. **Signal 1 — master advanced:** `git rev-parse HEAD`, compare to
   `qa-trigger-state.json`. If first run, seed state and exit. If no change,
   exit.
2. **Code-file filter:** `git diff --name-only` between last SHA and current;
   if no code extensions (`.py`, `.js`, etc.) changed, exit (PO specs/docs
   don't trigger QA).
3. **Signal 2 — verifier/debugger card completed recently:** query
   `kanban.db` for `assignee IN (verifier, debugger)` + `status = done` +
   `completed_at > now - 1h`. Filter out `[probe]` and `verify t_` titles.
4. **Dedup by SHA:** `idempotency_key = qa-merge-{sha}`.
5. **Create QA card:** assignee `qa`, body with HEAD SHA + source card + merge
   summary.

### Status: **MIGRATED**

Already replaced by `templates/qa-loop.json` (confirmed in `README.md` →
*Migration from Old Cron* and `MIGRATION.md`). The old cron's
`phase_qa_trigger` is commented out in `main()` (lines 681–687).

### How the template replaced it

The old cron's two-signal heuristic (git SHA changed **and** verifier card
completed) is collapsed into a single `card_completed` trigger:

```json
{
  "trigger": {
    "source": "card_completed",
    "condition": {
      "assignee": "verifier",
      "metadata.verdict": "PASS",
      "title_not_prefix": "[probe]"
    }
  }
}
```

The git-SHA check is **dropped** — the trigger fires directly on the verifier
card completion, which is a stricter and more precise signal than "master moved
+ a verifier card completed in the last hour." The `[probe]`/`verify t_`
exclusions are preserved via `title_not_prefix`.

**Reference template:** `templates/qa-loop.json` (already in repo).

### Profile / skill per node

| Node | Profile | Skill |
|---|---|---|
| qa_retest | `qa` | `live-testing` |

### Risk: **Low** (already in production)

---

## Engine Extension Requirements (summary)

The analysis reveals **gaps in the current engine** that block full migration.
Ordered by how many phases they unblock:

| Extension | Unblocks | Effort |
|---|---|---|
| **`target_board` node field** (create card on a different board than the trigger board) | Phase 3 (human-escalation cross-board) | Low |
| **Negative trigger conditions** (`label_not`, `type_not`, `assignee_not`) | Phase 2 (dispatch dedup), Phase 4 (scanner skip default) | Medium |
| **`card_blocked` trigger source** | Phase 4 (scanner) | Medium |
| **Dynamic profile resolution** (lookup table for escalation chain) | Phase 4 (scanner) | Medium |
| **`system` / side-effect node type** (run a command, no agent) | Phase 4 (auto-unblock), Phase 1 (bead-sync, if ever) | High — scope creep |
| **`bead_list` trigger** (vs `bead_ready`) or status-agnostic label trigger | Phase 3 (human-escalation, if human-label isn't ready-status) | Low-Medium |

**Recommendation:** Land `target_board` + negative conditions first (low cost,
unblock the two lowest-risk phases). Defer `card_blocked` + dynamic profiles +
system nodes until there's proven need — they push the engine toward becoming a
general automation framework rather than an agent-workflow orchestrator.

---

## Recommended Migration Order

```
1. [DONE]     QA trigger          → qa-loop.json              (card_completed)
2. [NEXT]     Human escalation    → human-escalation.json     (bead_ready + label)
              └ requires: target_board node field
3. [LATER]    Scanner             → KEEP AS CODE or card_blocked trigger
              └ requires: card_blocked trigger + dynamic profiles (defer)
4. [LAST]     Dispatch            → bug-router + wayfinder-* + dev-dispatch
              └ requires: negative trigger conditions (label_not / type_not)
              └ high risk: changes cardinality, bug heuristic, wayfinder skip-list
───
[KEEP]        Bead-sync           → extract to standalone bead_sync.py
              └ NOT a workflow; data reconciliation between two stores
```

**Migrate low-risk, high-clarity phases first.** Do not migrate a phase whose
engine gaps aren't closed — the old cron's idempotency and dedup logic is
battle-tested, and a half-templated replacement is worse than the imperative
original.
