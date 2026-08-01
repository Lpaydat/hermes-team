# Approach B — Distributed Per-Agent Workflows (card_completed trigger chains)

**Verdict:** Architecturally the most natural fit for the engine as written, but it inherits a
real, code-level bug in the self-trigger guard that must be fixed before it is trustworthy.
The `qa-loop.json` template already proves the pattern end-to-end.

---

## How it works (grounded in the code)

Each agent profile owns one or more small workflow templates (1–3 nodes). There is **no
master graph**. The pipeline emerges from trigger composition:

```
bead_ready → PO's dev-dispatch.json
   └─ node creates a tech-lead kanban card (idempotency_key "wf:<inst>:<node>")
       └─ card completes (status=done, metadata.role=tech-lead)
           └─ tech-lead's workflow.json fires (trigger: card_completed, assignee=tech-lead)
               └─ node creates dev card + verifier card (or chained cards)
                   └─ verifier card completes (metadata.verdict=PASS)
                       └─ qa-loop.json fires (this is the EXISTING template — already proven)
```

### The mechanics, line by line

1. **Trigger scan is poll-based, not event-driven.** `_check_triggers()` (runtime.py:1757)
   runs every tick. For each workflow that declares `trigger.source == "card_completed"`,
   it calls `find_recent_completions(board, since)` (kanban_adapter.py:173) with a 1-hour
   lookback (`TRIGGER_LOOKBACK_SECS = 3600`, runtime.py:40). So handoffs are **not
   instant** — they fire on the next tick after a card flips to `done`, worst case ~60s.

2. **Trigger context carries the triggering card's identity.** `_start_from_trigger()`
   (runtime.py:1977) builds:
   ```python
   trigger_context = {
       "card_id": trigger_card.id,   # ← downstream workflow knows WHO triggered it
       "board": board,
       "assignee": trigger_card.assignee,
       **meta,                        # all metadata flattened in (e.g. verdict, merged_commit_sha)
   }
   ```
   This is surfaced as `${trigger.card_id}`, `${trigger.verdict}`, etc. in the downstream
   template. **This is the mechanism for passing context across workflows** — there is no
   shared parent state; the metadata blob on the completing card IS the handoff payload.

3. **Self-trigger prevention is the load-bearing guard** (runtime.py:1783–1800). When a
   card's `idempotency_key` starts with `"wf:"` (i.e. the engine created it), the code
   parses the key to extract the parent workflow id and blocks re-triggering:
   ```python
   if card.idempotency_key and card.idempotency_key.startswith("wf:"):
       idem_parts = card.idempotency_key.split(":")
       instance_part = idem_parts[1]  # e.g. "wf_1690_tech-lead-build_a1b2c3d4"
       if f"_{wf.id}_" in instance_part:
           continue  # same-workflow self-trigger: always block
   ```
   See **Critical Bug** below — this parsing is fragile.

4. **Deduplication is persistent.** Each successful trigger records a key
   `f"trig:{wf.id}:{card.id}"` in the `trigger_keys` table (runtime.py:1802–1829). This
   survives restarts and prevents the same card from firing a workflow twice. GC'd after
   7 days (runtime.py:475).

---

## Strengths

1. **`qa-loop.json` already proves the pattern is production-viable.** It is a 1-node
   workflow triggered by `card_completed` with `assignee=verifier, status=done,
   metadata.verdict=PASS`. It reads `${trigger.card_id}` and `${trigger.merged_commit_sha}`
   from the verifier's completion metadata. This is *exactly* the cross-workflow handoff
   Approach B relies on. If the engine can do PO→QA via trigger, it can do PO→TL→Dev→Verif
   the same way.

2. **Each workflow is independently deployable, testable, and owned.** A 1–3 node template
   can be validated in isolation (`hermes workflow validate`, dry-runs). The tech-lead team
   owns `tech-lead-build.json`; the PO owns `dev-dispatch.json`. No merge conflicts on a
   monolithic master template. This matches how the profiles are already organized (each
   profile has its own `scripts/` and `skills/`).

3. **The trigger context makes handoffs explicit and auditable.** `${trigger.card_id}`
   gives you a causal chain. Combined with `parent_instance_id` and the `engine_events`
   table (runtime.py:178–206, logged with `instance_id`/`card_id`), you can reconstruct
   the full lineage: `bead → dev-dispatch card → tech-lead card → dev card → verifier
   card → qa card`. The handoff *is* the kanban card — it has a body, assignee, status,
   and metadata, all queryable.

4. **Natural parallelism without orchestration code.** If tech-lead's workflow creates
   dev + verifier cards as separate nodes (or uses `foreach`), they dispatch
   independently. No barrier logic, no fan-out coordination in a parent graph. The engine
   already handles parallel node dispatch within a tick (PHASE 2, runtime.py:791).

5. **Failure is localized.** If the dev↔verifier loop breaks, only those two small
   workflows are affected. You can delete/redeploy `verifier-review.json` without touching
   the PO dispatch logic. Compare to Approach A (monolith): a template bug poisons the
   entire 9-handoff chain.

---

## Weaknesses

1. **CRITICAL BUG: The self-trigger guard mis-parses instance IDs and can cause infinite
   trigger loops or false blocks.** (runtime.py:1788, 1793–1796). The code does:
   ```python
   if f"_{wf.id}_" in instance_part:   # substring match on "wf_<ts>_<wf.id>_<hex>"
   ```
   and then tries to extract the *parent* workflow id by splitting on `_` and looking for
   "a chunk that isn't wf, isn't empty, isn't all digits, and is longer than 3 chars":
   ```python
   for chunk in instance_part.split("_"):
       if chunk not in ("wf", "") and not chunk.isdigit() and len(chunk) > 3:
           parent_wf_id = chunk
           break
   ```
   **Problem:** Instance IDs are `f"wf_{int(time.time())}_{wf.id}_{uuid}"` (line 1956).
   If a timestamp chunk (e.g. `1690123456`) splits into a non-digit-looking segment, or
   if workflow ids contain underscores (e.g. `tech-lead-build` splits into `tech`, `lead`,
   `build` — each <3 chars or matches a real workflow id by accident), the parser picks
   the **wrong parent workflow id**. Consequences:
   - A cross-workflow trigger that *should* fire gets blocked (parent_wf.edges is truthy).
   - A self-trigger that *should* be blocked slips through (substring match fails because
     workflow ids with hyphens don't match the `_wf.id_` pattern with underscores).
   **This bug must be fixed** before Approach B is safe — the entire architecture depends
   on this guard correctly distinguishing "same workflow" from "different workflow".

2. **The dev↔verifier loop (multiple iterations) is awkward.** The README describes an
   inner FAIL loop: verifier FAILs → dev fixes → re-review, until PASS or iter≥3
   (README:209). In Approach B, this means **each iteration is a new workflow instance**:
   verifier's `card_completed` (verdict=FAIL) triggers `dev-fix.json`, which creates a new
   dev card; dev's completion triggers `verifier-review.json` again. That's a new instance
   per iteration. Problems:
   - **Iteration counting lives nowhere.** No single workflow tracks "we're on iteration 2
     of 3". You'd have to count prior trigger firings via `trigger_keys` or embed
     `iteration: N` in card metadata and increment it. The engine has no native loop
     construct across trigger boundaries.
   - **The iter≥3 escalation (README:196) requires cross-instance state.** The verifier
     workflow must look up "how many times has this bead been reviewed?" — but trigger
     context only gives it `${trigger.card_id}` and the triggering card's metadata. It
     cannot see sibling instances. You'd need a `command` node that queries the board for
     prior verifier cards on the same bead. This works but is bespoke glue per loop.

3. **Debugging a broken chain across 6+ independent workflows is hard.** The
   `engine_events` table helps (you can filter by `instance_id` or `workflow_id`), but
   there is no built-in "trace this bead through the pipeline" view. If a handoff doesn't
   fire, you must manually check: (a) did the upstream card actually reach `done`? (b) did
   its `idempotency_key` trip the self-trigger guard? (c) did `trigger_keys` dedup it? (d)
   did `_matches_trigger` pass (assignee/status/metadata fields all match)? Each is a
   separate SQLite query against two different DBs (workflow-state.db + board kanban.db).
   A monolithic graph (Approach A) gives you a single `instance_id` to trace.

4. **Trigger conditions are limited and brittle.** `_matches_trigger()` (runtime.py:1908)
   only supports: `assignee`, `status`, `metadata.<field>` (exact equality),
   `title_prefix`, and `title_not_prefix` (via hacky `startswith(key, "title_not_prefix")`).
   You **cannot** express: "trigger when card completes AND it was created by workflow X",
   or "trigger when metadata.role == tech-lead AND metadata.outcome == approved" (you *can*
   — but only as two separate `metadata.role` and `metadata.outcome` keys, both exact-match).
   Notably there is **no `metadata_verdict_in` or negation** — you cannot say "trigger on
   any verdict EXCEPT PASS". This forces narrow conditions that may over- or under-fire.

5. **The 1-hour lookback window is a silent data-loss risk.** `TRIGGER_LOOKBACK_SECS =
   3600` (runtime.py:40). If the engine is down for >1 hour (deploy, crash, host reboot),
   `find_recent_completions` misses cards that completed during the outage — **the trigger
   chain silently breaks**. There is no backfill. The `trigger_watermark` table exists but
   is **not used for card_completed triggers** (only the lookback constant is). For a
   distributed chain with 9 handoffs, any single missed trigger stalls the entire pipeline
   with no alarm.

---

## JSON Template Sketches — 3 linked workflows

These illustrate the pattern. Each is independently deployable.

### 1. `dev-dispatch.json` (PO owns this — triggered by bead_ready)

```json
{
  "id": "dev-dispatch",
  "name": "PO Bead Dispatch",
  "description": "bd ready → creates a tech-lead card. Replaces phase_dispatch in old cron.",
  "trigger": {
    "source": "bead_ready",
    "condition": { "type": "feature" }
  },
  "nodes": [
    {
      "id": "create_tech_lead_card",
      "profile": "tech-lead",
      "skill": "dev-dispatch",
      "title_template": "[dispatch] Bead ${trigger.bead_id}",
      "body_template": "## Dispatch bead to tech-lead\n\n**Bead ID:** ${trigger.bead_id}\n**Trigger source:** ${trigger.trigger_source}\n\nRun `dev-dispatch` skill: decompose this bead into dev + verifier cards via kanban_delegate.\n\n**Completion metadata contract (REQUIRED for downstream trigger):**\n- metadata={role: \"tech-lead\", bead_id: \"${trigger.bead_id}\", dev_card_id: \"...\", verifier_card_id: \"...\", status: \"delegated\"}",
      "output": {
        "schema": {
          "type": "object",
          "required": ["role", "bead_id"],
          "properties": {
            "role": { "type": "string", "enum": ["tech-lead"] },
            "bead_id": { "type": "string" }
          }
        }
      }
    }
  ]
}
```

### 2. `tech-lead-build.json` (Tech-lead owns this — triggered by card_completed)

```json
{
  "id": "tech-lead-build",
  "name": "Tech-Lead Build Delegation",
  "description": "Fires when a tech-lead dispatch card completes. Creates dev + verifier cards.",
  "trigger": {
    "source": "card_completed",
    "condition": {
      "assignee": "tech-lead",
      "status": "done",
      "metadata.role": "tech-lead",
      "title_prefix": "[dispatch]"
    }
  },
  "nodes": [
    {
      "id": "create_dev_card",
      "profile": "developer",
      "skill": "coding-harness",
      "title_template": "[dev] ${trigger.bead_id}",
      "body_template": "## Implement bead\n\n**Bead:** ${trigger.bead_id}\n**Dispatched by tech-lead card:** ${trigger.card_id}\n\nRead the tech-lead card's decisions, implement in isolated worktree, commit when gates green.\n\n**Completion metadata contract:**\nmetadata={role: \"developer\", bead_id: \"${trigger.bead_id}\", branch: \"...\", commit_sha: \"...\", verdict: \"ready_for_review\"}"
    },
    {
      "id": "create_verifier_card",
      "profile": "verifier",
      "skill": "adversarial-review",
      "title_template": "[verify] ${trigger.bead_id}",
      "body_template": "## Adversarial review\n\n**Bead:** ${trigger.bead_id}\n**Dev card:** ${trigger.card_id} (await its completion metadata for branch/commit)\n\n3-stage review. On FAIL, file findings + create dev-fix card. On PASS, merge + set metadata.verdict=PASS.\n\n**Completion metadata contract:**\nmetadata={role: \"verifier\", verdict: \"PASS|FAIL\", merged_commit_sha: \"...\", findings_count: N}",
      "depends_on": ["create_dev_card"]
    }
  ]
}
```

### 3. `qa-loop.json` (QA owns this — ALREADY EXISTS, shown for completeness)

This is the existing template (templates/qa-loop.json). It demonstrates the exact pattern:
triggered by `card_completed` with `assignee=verifier, metadata.verdict=PASS`. **No changes
needed** — it already fits the chain.

---

## Key takeaways

| Question | Answer from code |
|---|---|
| Does the trigger chain work across workflows? | **Yes** — `_check_triggers()` polls all boards every tick, fires any matching `card_completed` workflow. |
| Can it express all 9 handoffs? | **Most.** Linear handoffs (PO→TL→Dev→Verif→QA) work. The **dev↔verifier iteration loop** is hard — no native cross-instance counter. |
| Does downstream know which card triggered it? | **Yes** — `${trigger.card_id}` + all metadata flattened into `${trigger.*}`. |
| Does each loop iteration create a new instance? | **Yes** — FAIL→fix→re-review spawns new `dev-fix.json` + `verifier-review.json` instances each cycle. Iteration tracking is bespoke. |
| How to debug a broken 6-workflow chain? | `engine_events` table (filter by instance_id/card_id) + manual SQLite on both DBs. No unified trace view. |
| Does qa-loop.json already prove the pattern? | **Yes — conclusively.** It's a 1-node cross-workflow trigger that's in production. |
| Is the self-trigger guard safe? | **NO — it has a parsing bug** (runtime.py:1788–1796). Must be fixed before relying on Approach B. |
