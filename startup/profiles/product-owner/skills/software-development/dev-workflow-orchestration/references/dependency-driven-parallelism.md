# Dependency-Driven Parallelism

Design for running multiple beads/slices through the dev pipeline simultaneously, using bead dependencies as the primary scheduler instead of hard profile serialization.

## The problem with `max_in_progress_per_profile: 1`

A cap of 1 creates a **fully serial pipeline** — even completely independent beads (no dependency edges between them) must wait in line. This wastes wall-clock time when the PRD decomposes into independent slices that could run concurrently.

The cap was set to 1 during initial battle testing (Tests 1–21) to prove the pipeline works at all. Now that it's proven, the cap should be raised to unlock parallelism — but in a controlled way.

## The three-layer scheduler model

```
Layer 1: DEPENDENCY GRAPH (correctness)
  Beads define what CAN run. `bd ready` = "deps satisfied".
  Kanban parent→child defines the within-bead pipeline (TL→DEV→VER).
  
Layer 2: CONCURRENCY CAP (resource safety)  
  max_in_progress_per_profile: N (e.g., 3)
  Controls how many run NOW. Excess waits in 'ready'.
  
Layer 3: WORKTREE ISOLATION (no conflicts)
  Each card gets <repo>/.worktrees/<task-id>/
  Independent branches. No shared mutable state during work.
```

Dependencies control **ordering** (what can start). The cap controls **resource safety** (how many at once). Worktrees provide **isolation** (no file conflicts during work). These are three orthogonal concerns — mixing them into one knob (`max_in_progress: 1`) was the original mistake.

## How parallel pipelines look

```
PRD decomposed into 5 beads:
  bead-1 (auth)     — no deps
  bead-2 (api)      — deps: bead-1
  bead-3 (cli)      — deps: bead-2
  bead-4 (logging)  — no deps
  bead-5 (config)   — no deps

bd ready → [bead-1, bead-4, bead-5]    ← 3 independent beads ready

Time →
t0:  TL[bead-1]  TL[bead-4]  TL[bead-5]     ← 3 tech-lead cards dispatched (cap=3)
t1:  DEV[1]      DEV[4]      DEV[5]          ← tech-lead finishes, dev starts
     TL[bead-2]  (waits — bead-2 deps on 1)
t2:  VER[1]      VER[4]      VER[5]          ← verifier reviews
     DEV[2]      (waits — bead-2 deps on 1)
t3:  ✓ bead-1 closed → bead-2 ready → TL[bead-2] dispatched
     ✓ bead-4 closed → (nothing depends on it)
     ✓ bead-5 closed → (nothing depends on it)
t4:  DEV[2]  → VER[2] → ✓ bead-2 closed → bead-3 ready → TL[3] → DEV[3] → VER[3] → done
```

## Recommended cap values (starting points)

| Profile | Cap | Reasoning |
|---------|-----|-----------|
| tech-lead | 3 | Planning is cheap (API-wise). Multiple contracts in parallel is fine for a strong model. |
| developer | 2–3 | Each runs a pi/zz harness = real API load. Start conservative, tune based on 429 frequency. |
| verifier | 2–3 | Review is read-heavy. Lower API load than developer. |

These are STARTING POINTS. Monitor 429 frequency after raising. If 429s spike, increase `rate_limit_delay` proportionally or reduce the cap. The existing 429 resilience layers (api_max_retries: 10, rate_limit_delay: 30s, board scanner auto-unblock) provide a safety net.

## Critical invariant: merges stay serialized

Multiple verifiers can review in parallel, but **merges queue**. The merge-slot lock (in verifier SOUL) is the mechanism. Only one verifier merges to main at a time. Others wait for the slot, then rebase onto the updated main, re-run tests on the rebased candidate, then merge.

```
VER[bead-4] PASS → acquires merge slot → rebases → tests → merges → releases slot
VER[bead-5] PASS → waits for slot → rebases onto new main → tests → merges → releases slot
```

If the rebase produces a conflict (two slices touched the same file), see the conflict protocol below.

## Conflict handling protocol

When verifier rebases and hits conflicts:

```
Verifier detects conflict during rebase
  → Does NOT resolve it (verifier never writes code)
  → Blocks review card with conflict details:
    "Merge conflict on auth.py:45-52. Developer must resolve."
  → Creates fix card for developer:
    "Resolve merge conflict. Files: auth.py, config.py.
     Rebase onto main@<sha>."
  → Developer resolves → verifier re-reviews
```

Well-decomposed slices (tracer-bullet vertical slices touching different modules) rarely conflict. When they do, the developer resolves — never the verifier.

## The `bd ready` re-trigger problem (VERIFIED Jul 2026)

`bd ready` does NOT know about kanban cards. A bead stays `open` (ready) until someone runs `bd close <id>`, which only happens when the verifier merges (the completion boundary).

**Tested:**
```
bd ready → [A, B, C]          ← 3 independent beads
PO creates 3 kanban cards
Tech-lead starts bead-A (doesn't close it yet)
Next cron tick: bd ready STILL shows [A, B, C]  ← all still "ready" in beads!
```

**Two layers of protection:**
1. `--idempotency-key "bead-<id>"` — `kanban create` with a duplicate key returns the existing card instead of creating one. This IS the dedup mechanism.
2. The OLD `auto-dispatch.sh` has an early-exit gate (`if TOTAL > 0; then exit 0`) that blocks ALL dispatch when ANY card exists — this MUST be removed for parallel. The idempotency key handles dedup; the script doesn't need to enforce a cap.

## Auto-dispatch script changes

The current `auto-dispatch.sh` has two problems for parallel:
1. It creates only 1 card per tick (`break` after first card)
2. It exits early if ANY tech-lead card exists (blocks parallel dispatch)

**Updated logic:**
```bash
# OLD (serial): exit if ANY tech-lead card exists; create only ONE card
if [ "$((READY_COUNT + RUNNING_COUNT))" -gt 0 ]; then exit 0; fi
# ... create one card, then break

# NEW (parallel): dispatch ALL ready beads; idempotency handles dedup
for bead in $(bd ready --json); do
  hermes kanban create ... --idempotency-key "bead-$bead_id" --workspace worktree
done
```

The dispatcher respects `max_in_progress_per_profile` from config — that's the real cap. The script doesn't need to enforce it.

## Workspace isolation: worktree vs dir (VERIFIED Jul 2026)

| Workspace type | When to use | Isolation |
|----------------|-------------|-----------|
| `dir:<path>` | Serial execution (1 chain at a time) | Shared directory — all slices touch same files |
| `worktree` | Parallel execution (multiple chains) | Git worktree per card — isolated branch + filesystem |

**For parallel:** each tech-lead card gets `--workspace worktree`. Hermes creates `<repo>/.worktrees/<task-id>/` with a deterministic branch (`<project-slug>/<task-id>`). Child cards (developer, verifier) inherit the worktree path via `workspace_path` in the fix-card body.

**Previous tests all used `dir`** — safe for serial, broken for parallel (two sessions writing to the same files).

## Merge serialization: bd merge-slot (VERIFIED commands Jul 2026)

`bd merge-slot` is a real, working feature (verified from `bd merge-slot --help`):

```bash
bd merge-slot create              # one-time setup per project
bd merge-slot acquire --holder verifier --wait   # queue if held (--wait blocks, plain acquire fails immediately)
bd merge-slot check               # is it available?
git rebase origin/main            # rebase onto latest main
# conflicts? → release slot, FAIL → fix card to developer
re-run FULL test suite on rebased candidate      # non-negotiable (DoltHub rule)
git merge --squash && git push
bd merge-slot release --holder verifier          # ALWAYS release — success or failure
```

Pass `--holder verifier` explicitly — the default holder comes from `$BEADS_ACTOR`/git identity, which is the same OS user for every profile on this machine.

**This was designed but NEVER tested (serial tests).** All 21 battle tests ran serially; main never moved during a slice. Parallel dispatch itself was PROVEN in Test 22 (Jul 2026) — see "Test 22 proof" below.

## Merge-slot bead must be filtered from dispatch (DISCOVERED Test 22, Jul 2026)

`bd merge-slot create` creates an open bead with label `gt:slot` that `bd ready` shows as ready work. Without filtering, `auto-dispatch.sh` creates a kanban card for the merge-slot — a coordination primitive, not actual work. **Fix**: the dispatch script's Python parser skips any bead with `gt:slot` in its labels:

```python
labels = item.get('labels', [])
if 'gt:slot' in labels:
    continue
```

## Worktree workspace requires explicit path (DISCOVERED Test 22, Jul 2026)

`--workspace worktree` alone fails — `workspace_path` stays null and claim fails with "no workspace_path, and board has no default_workdir." The correct format is:

```bash
--workspace "worktree:/absolute/path/to/repo" --branch "feature/<bead-id>"
```

This creates `<repo>/.worktrees/<task-id>/` with the specified branch. Verified: both worktrees get independent filesystem + branch, no shared mutable state.

## Test 22 proof — parallel execution + merge serialization PROVEN (Jul 2026)

**Setup**: 3 beads (2 independent + 1 dependent on bead B). `max_in_progress_per_profile: 2` on all profiles. `bd merge-slot create` run once for the project.

**Verified working — dispatch + pipeline:**
- Auto-dispatch v2 dispatched both independent beads simultaneously (one tick)
- Dispatcher ran 2 tech-lead sessions at the same time
- Each got isolated worktree (`.worktrees/t_9a85b525/` + `.worktrees/t_a744bf76/`)
- Tech-lead B completed planning → created developer + verifier child cards while tech-lead A was still planning
- Pipeline overlap: developer B finished while tech-lead A was still writing its contract
- Dependent bead C correctly NOT dispatched (dependency gate held)
- Idempotency keys prevented duplicate cards on cron re-fire
- `gt:slot` filter prevented merge-slot bead from being dispatched as work

**Verified working — merge serialization (the big untested gap, now PROVEN):**
- Both verifiers reached PASS verdict at nearly the same time (~20:27)
- Verifier B acquired merge slot first → rebased → ran full suite (21/21) → merged (bc99b63) → released slot
- Verifier A was queued as waiter #1 (`bd merge-slot acquire --wait`)
- After B released, A acquired → rebased onto updated main → ran full suite (48/48 incl. B's tests) → merged (17c3d0f) → released
- **Zero conflicts** — well-decomposed independent slices touching different files
- **Post-merge test run on main**: 48/48 tests pass — both independently-developed modules work together
- Dependent bead C (Pattern Validator) auto-unblocked when B closed its bead (`bd close` → `bd ready` showed it → auto-dispatch created card immediately)

**Timeline**: ~20 min total for 2 independent slices through the full pipeline (dispatch → plan → build → verify → merge), running in parallel. Equivalent serial time would have been ~30-35 min.

## Conflict resolution routing

When a verifier rebases and hits a conflict (two parallel slices touched the same file):

```
Verifier detects conflict during rebase
  → releases merge slot
  → FAIL verdict (merge-readiness FAIL, not code-quality FAIL)
  → creates fix card for DEVELOPER:
      "Rebase onto main@<sha>. Resolve conflicts in: <files>.
       Use resolving-merge-conflicts skill."
  → Developer resolves → new review card → verifier re-verifies
```

**Who resolves conflicts:** the DEVELOPER (never the verifier). Conflict resolution is code-writing. The verifier detects and routes — it does not fix. The developer has the `resolving-merge-conflicts` skill (mattpocock, shared) available.

Well-decomposed slices (tracer-bullet vertical slices touching different modules) rarely conflict. Conflicts mainly happen when two slices modify the same shared file (e.g., `__init__.py`, `config.py`).

## Cap recommendation for first parallel test

**Use 2.** Here's why:
- Only need 2 independent beads (simpler PRD)
- Lower API load (fewer 429s to deal with)
- Still proves pipeline overlap + merge serialization
- If 2 works clean, bumping to 3 is trivial

## What this does NOT need

- No new profiles (no "tech-lead-2", "developer-3")
- No new boards
- No complex orchestration layer
- No change to the bead/kanban model
- Just: raise `max_in_progress_per_profile`, update auto-dispatch, document the conflict protocol

## Two state managers: bd vs kanban — no conflict (VERIFIED Test 22, Jul 2026)

User asked: "will having 2 state managers conflict?" Answer: **no — they track different things at different layers.** The boundary is clear:

```
Layer 1 (bd):     open ────────────────────────────→ closed
                  (work exists)                      (work merged to main)

Layer 2 (kanban): ready → running → done            (per-card lifecycle)
                  ready → running → done            (per-card lifecycle)
                  ready → running → done            (per-card lifecycle)
```

| | bd (beads) | Hermes kanban |
|---|---|---|
| **Tracks** | "Is this feature done?" | "Who is working on what right now?" |
| **Granularity** | Coarse (epic → bead → close) | Fine (card → ready/running/done) |
| **Lifetime** | Durable across sprints | Ephemeral, archived after done |
| **Who writes** | PO creates, verifier closes on merge | Everyone creates/completes cards |

**`bd close` is the bridge between systems.** When the verifier merges + runs `bd close`, it simultaneously:
- bd: `open → closed` (feature done)
- kanban: verifier card completes (execution done)
- This triggers `bd ready` to promote dependent beads → auto-dispatch creates next card

A bead can be `open` while multiple kanban cards for it are `done`. They never disagree on the same field — they answer different questions.

**Who touches bd:**
- PO: creates beads (`bd create`), creates merge-slot (`bd merge-slot create`), reads (`bd ready`, `bd show`)
- Verifier: acquires/releases merge-slot (`bd merge-slot acquire/release`), closes beads (`bd close <id>`)
- Tech-lead: reads bead for ACs (`bd show <id>`) and closes beads (`bd close <id>`) per skill instructions
- Developer: reads bead for ACs (`bd show <id>`) — read-only

**bd merge-slot is infrastructure, not a product decision.** The verifier manages it (acquire → rebase → test → merge → release → close bead). This keeps merge serialization tight — no round-trip to PO.

**Idempotency keys are stored in SQLite but NOT exposed in the JSON API.** Verified: `kanban create --idempotency-key "X"` stores the key in `tasks.idempotency_key` (with an index), but `kanban list --json` omits the field. The dedup works at CREATE time (returns existing card instead of creating duplicate) even though the key isn't visible in list/show responses. To verify at the DB level: `sqlite3 kanban.db "SELECT id, idempotency_key FROM tasks WHERE idempotency_key IS NOT NULL"`.

### Desync risks and mitigations

| Risk | What happens | Mitigation |
|---|---|---|
| Bead closed but code not merged | Feature shows "done" in bd but isn't on main | Verifier merge-protocol: merge FIRST, then `bd close` |
| Merged but bead not closed | Bead stays open, `bd ready` re-shows, auto-dispatch tries to re-dispatch | Idempotency key prevents duplicate card. Board scanner detects stale beads. |
| Two verifiers close same bead | Second `bd close` is a no-op | bd handles gracefully |
| Cron fires while bead open | Would create duplicate card | Idempotency key at create-time prevents it (verified: 17 cron ticks, 0 duplicates) |

## Parallel dev within a single bead: 1:1 dev→verifier per chain (DECIDED Jul 2026)

User asked: should each dev have a separate verifier, or fan-in N devs → 1 verifier?

**Decision: 1:1 per chain (N dev → N verifier).** Detailed trade-off analysis:

| Aspect | 1:1 (N dev → N ver) | N→1 (N dev → 1 ver) |
|---|---|---|
| Adversarial isolation | Each verifier sees ONE diff, clean context | Verifier sees all N diffs — weaker review |
| Parallelism | All verifiers run simultaneously (up to cap) | One verifier reviews all — serial bottleneck |
| Failure isolation | Buggy dev only blocks its own verifier | One bug blocks the entire batch |
| Cross-slice integration | Handled by bd dependencies (C can't start until B merged) | Would let all devs start simultaneously but against non-existent interfaces |
| Redesign needed | None — already built and proven | Major rewrite of adversarial-review, merge-protocol, verdict-routing |
| Industry standard | Each PR reviewed independently | Batch review is not standard |

**Integration dependencies handled by bd**: if bead C imports from bead B, C can't dispatch until B's verifier closes the bead (bd dependency chain). C's dev starts with B's merged code already on main. This is the correct integration gate.

**Where N→1 WOULD make sense**: a separate "integration verifier" that runs AFTER all slices merge — checking that the combined codebase works together. But that's a different role (integration testing), not the adversarial verifier.

### How the fix loop works with worktrees (VERIFIED Jul 2026)

When a verifier FAILs and creates a fix card, the developer needs to know which worktree/branch to work on. This is already solved — the data flows automatically:

1. **Developer completion metadata** carries: `worktree_path`, `branch_name`, `session_id` (harness session for warm resume)
2. **Verifier reads parent metadata** via `kanban_show` — knows exactly where the code is
3. **Fix card (on FAIL)** is created with explicit pointers:
   - `workspace_kind="dir"`, `workspace_path=<original dev worktree>` — same directory
   - Body includes: `Resume-Session: <harness_session_id>` (pi resumes warm), `Branch: <branch_name>`
4. **Worktree persists across all fix iterations** — only cleaned up after verifier merges

The developer never needs to figure out where to work — the fix card points at the exact directory and branch.

### delegate-wait.sh multi-verifier support (BUILT Jul 2026)

The script accepts multiple verifier IDs in one call for parallel dev:

```bash
# Single chain
delegate-wait.sh --link-only <tech-lead-id> <ver1>

# Parallel: 3 independent dev→verifier chains
delegate-wait.sh --link-only <tech-lead-id> <ver1> <ver2> <ver3>
```

This links tech-lead as child of ALL verifiers, then blocks once with `kind=dependency`.
`recompute_ready` checks ALL parents — promotes tech-lead only when every verifier is `done`.

Located at `~/.hermes-teams/startup/profiles/tech-lead/scripts/delegate-wait.sh`.

## Implementation status: LIVE and PROVEN (Jul 2026)

**Changes deployed:**
- `max_in_progress_per_profile: 2` on tech-lead, developer, verifier (was 1)
- `auto-dispatch.sh` v2: dispatches ALL ready beads, uses `worktree:<path>`, filters `gt:slot` beads
- Gateways restarted to pick up config changes
- Tested on project `test22-parallel` (3 beads: 2 independent + 1 dependent)

**What was proven end-to-end:**
- 2 independent slices through full pipeline in parallel (dispatch → plan → build → verify → merge)
- Merge-slot serialization: verifier B held slot, verifier A queued as waiter #1, merged sequentially
- Post-rebase execution: both verifiers re-ran full suite on rebased candidate before merge
- 48/48 tests pass on main after both merges — independently-developed modules integrate correctly
- Dependent bead auto-unblocked when parent bead closed

**What was NOT tested yet:**
- Merge conflict (slices touched different files — no conflict occurred)
- 429 rate-limit behavior under parallel load (no significant 429s observed)
- Cap > 2 (not bumped yet)
- Long-running parallel loops stability

## Hermes hooks: NO kanban lifecycle events (INVESTIGATED Jul 2026)

User asked: "does Hermes have hooks? What if a card-creation hook auto-claims the bd bead, and a card-completion hook auto-closes it?"

**Investigated the Hermes hooks system.** Three hook systems exist:

| System | Events | Runs in |
|--------|--------|---------|
| **Gateway hooks** | `gateway:startup`, `session:*`, `agent:*`, `command:*` | Gateway only |
| **Plugin hooks** | `pre_tool_call`, `post_tool_call`, `pre_llm_call`, `pre_verify`, `subagent_*`, session lifecycle | CLI + Gateway |
| **Shell hooks** | Same as plugin hooks, but shell scripts | CLI + Gateway |

`VALID_HOOKS` (defined in `hermes_cli/plugins.py:135`) has 18 events — ALL are about agent behavior (tool calls, LLM calls, session lifecycle, subagents). There is **NO** `kanban:create`, `kanban:claim`, `kanban:complete`, or `kanban:status_change` event. The hooks system cannot fire when a kanban card changes status.

**bd hooks** (`bd hooks`) install git hooks (pre-commit, post-merge, etc.) — these fire on git operations, not kanban state changes.

**Conclusion:** event-driven bd↔kanban sync via hooks is **not possible today**. The script + cron approach is the right alternative:
1. `auto-dispatch.sh` (cron, 1min): creates kanban cards for ready beads (already deployed)
2. `bead-sync.sh` (cron, 3min, NOT YET BUILT): closes bd beads when their kanban chain completes — the safety net for agents forgetting `bd close`

The `bead-sync.sh` script needs chain traversal: find the root tech-lead card (which has the `bead-<id>` idempotency key), check if ALL its descendant cards (dev → verifier chain) are done, and only then close the bead. This is because the tech-lead card completes before the verifier finishes — closing the bead on tech-lead completion would be premature.

**Recommended hybrid approach:**
- Verifier runs `bd close` on PASS (primary path — zero lag, already in skill instructions)
- `bead-sync.py` cron every 1min (safety net — catches agent misses) — BUILT, DEPLOYED, and tested
- `auto-dispatch.sh` optionally runs `bd update -s in_progress` at dispatch time (marks bead as "being worked on")

### bead-sync.py — BUILT, DEPLOYED, and RACE CONDITION DISCOVERED (Jul 2026)

The script was built BY the workflow itself (dev + verifier produced it with 25/25 ACs).
Deployed as 1-min cron (`script='bead-sync.py'`, `no_agent=True`).

**Status mapping:**

| Kanban card status | Bead target status | When |
|---|---|---|
| `ready` or `running` | `in_progress` | Card exists with `bead-<id>` key |
| `blocked` | `blocked` | Card status is `blocked` |
| `done` | `closed` | Card status is `done` |
| `archived` | `open` (ONLY if bead is not already `closed`) | Reset for re-dispatch |

**Closed beads are terminal** — the sync NEVER reopens a `closed` bead, even if the card is later archived. Archived cards after successful merge are cleanup, not failure. Without this guard, the sync reopens ALL completed beads when their cards are archived for board hygiene.

**✅ RACE CONDITION RESOLVED (Jul 2026):** The fix is `delegate-wait.sh` — tech-lead links itself as CHILD of the verifier card via `kanban_link(verifier_id, tech-lead_id)`, then blocks with `kanban_block(kind="dependency")`. Kanban's built-in `recompute_ready` auto-promotes tech-lead when the verifier completes. The root card stays in `todo` (not `done`) while waiting — bead-sync skips `todo` status (not in STATUS_MAP), so the bead stays `in_progress` until tech-lead is re-dispatched and calls `kanban_complete`. See [references/kanban-dependency-mechanics.md](kanban-dependency-mechanics.md) for the full source-code analysis.

**Closed beads are terminal (FIX APPLIED):** the sync NEVER reopens a `closed` bead, even if the card is later archived. Without this guard, the sync tries to reopen ALL completed beads when their cards are archived for board hygiene. Fix is in `bead_sync.py`: `if current == "closed": continue` before any status comparison.

**Tripwire false positive:** the tripwire flags `MANUAL_BD_CHANGE` when bead-sync updates bead status (no `run_id`, no worker completion nearby). This is expected — bead-sync is a cron script. The fix: whitelist bead-sync's bd updates in the tripwire.

**bd CLI commands (VERIFIED):**
- `bd update <id> -s in_progress` — NOT `--status`, NOT `set-state`. The `-s` short flag is the correct one.
- `bd update <id> -s closed` — same as `bd close <id>` but explicit
- `bd update <id> -s open` — can reopen if needed
- `bd update <id> -s blocked` — hides from `bd ready`

**Performance benchmarks:**
- Kanban SQLite direct read: **4ms** (could poll every second for free)
- `bd list --json`: **~250ms** per project (Dolt overhead)
- `bd ready --json`: **~150ms** per project
- `bd update -s <status>`: **~200ms** per bead (write)
- bd JSONL export (`.beads/issues.jsonl`): **40ms** to parse, BUT can be empty/stale — don't rely on it

**Why 30s not 5s for cron:** The kanban read is instant, but `bd update -s in_progress` takes ~200ms per bead. Worst case (10 new beads): 2s of bd writes. 30s gives headroom. Could go to 10s if needed.

**bd uses Dolt, not SQLite** — cannot read the bd DB directly with `sqlite3`. Must use `bd` CLI. The `.beads/embeddeddolt/` directory contains Dolt's internal format, not a SQLite database.

**The link between systems is the idempotency key** — no metadata field needed. The kanban card's `idempotency_key` column stores `bead-<bead-id>`. To find the kanban chain for a bead: find the root card by key, then walk `task_links` recursively.

**Chain traversal (SQLite):**
```sql
WITH RECURSIVE chain AS (
    SELECT id, status FROM tasks WHERE idempotency_key = 'bead-<bead-id>'
    UNION ALL
    SELECT t.id, t.status FROM tasks t
    JOIN task_links l ON l.child_id = t.id
    JOIN chain c ON c.id = l.parent_id
)
SELECT * FROM chain;
-- Close bead only if ALL rows have status='done'
```

## Relation to Claude Code's subagent model

Claude Code can spawn 100+ subagents, but they're **queued**, not all running simultaneously. It has a concurrency cap (`max_concurrent_children`) that controls how many execute at once. Dependencies control ordering; the cap controls resource safety. Hermes already has the same mechanism — `delegation.max_concurrent_children` for in-session delegation and `max_in_progress_per_profile` for board-level dispatch. The insight is that bead dependencies should be the PRIMARY scheduler, with the profile cap as a resource guardrail, not a serialization gate.

## Eating our own dog food — building bead-sync.py via the workflow (Jul 2026)

The bead-sync.py tool itself was built using the dev workflow it's designed to support. The PRD was published via `to-prd`, slices created via `to-issues`, and the pipeline dispatched through auto-dispatch. Several findings emerged:

### PRD bead must be closed after creating slices (DISCOVERED)

After `to-issues` creates slice beads from the PRD bead, the PRD bead stays `open` in bd. `bd ready` keeps showing it, and `auto-dispatch.sh` creates a tech-lead card for the PRD bead — which tech-lead then tries to "implement" as if it were a feature. **Fix**: `bd close <prd-bead-id>` immediately after creating slices. The PRD is consumed once slices exist.

This is the exact desync that `bead-sync.py` itself would prevent. Until the sync is deployed, always close PRD beads manually.

### bd `--deps` flag at create-time does NOT persist (DISCOVERED)

`bd create "title" --deps <parent-id>` accepts the flag without error but the dependency is not stored in the bead. `bd ready` ignores it and shows the bead as ready immediately. **Fix**: use `bd link <child-id> <parent-id>` AFTER creating both beads. `bd link` creates a "blocks" dependency (parent blocks child). Verify with `bd dep list <id>` — the dependency should appear. Only then does `bd ready` correctly hide dependent beads until their parent is closed.

### Hermes profile model ≠ harness model (CLARIFIED)

`config.yaml` `model.default` sets the Hermes AGENT model (the governance layer: tech-lead, developer, verifier). The harness model (what `pi`/`claude`/`zz` uses to write code) is chosen independently by the developer at invocation time. Switching the developer profile from `glm-4.5-air` to `glm-5.2` does NOT change what model the harness uses — the developer may still invoke `claude` (Claude Sonnet) or `pi` with any provider/model.

To control the harness model: specify it in the card body (`Harness: pi --provider zai --model glm-5.2`) or patch the `developer-loop` skill's default recipe. The profile model and harness model are two independent knobs.

For production use (building real tooling): switch developer profile to `glm-5.2` for stronger governance. For workflow testing (exercising failure-fix loops): keep `glm-4.5-air` to force bugs. The user's principle: "we test our building process on this one" — real code needs the strong model.

## PO manual intervention contamination — THE #1 TESTING PITFALL (Jul 2026)

During Test 22 and the bead-sync workflow build, the PO (product-owner agent) manually intervened **7 times** in a workflow that was supposed to be autonomous:

1. Ran `auto-dispatch.sh` manually instead of waiting for cron
2. Ran `bd close <PRD-bead>` to unblock slices (the bd close didn't persist — bead stayed open)
3. Archived a "stray" card that shouldn't have existed (instead of investigating WHY it existed)
4. Cleaned up a zombie worktree created by the archive
5. Archived a second card stuck in an infinite loop (caused by #3+#4)
6. Archived a stale battle test card
7. Ran auto-dispatch again

**Every intervention masked a real bug and created cascading failures.** The zombie loop (48 spawn failures) was a direct consequence of manually archiving a card without cleaning its worktree — the branch was still checked out, blocking all future worktree creation on that branch.

**The user's reaction: "you made me lost trust to the current system as I don't know which part is working which part is not because of your manually action."**

### The rule: NEVER touch the board/bd/scripts during an autonomous test

If a task fails, **LET IT FAIL**. Observe what the system does. If the board deadlocks, **LET IT DEADLOCK**. See if self-healing works. Every manual fix:
- Masks the bug (so it won't get fixed)
- Creates cascading failures (archive → worktree conflict → zombie loop)
- Invalidates the test (manual intervention means the test doesn't prove autonomy)

### What to do instead: file the bug, don't fix it

When you see a problem during observation:
1. Note the bug (what happened, what should have happened)
2. Let the system continue or fail — don't touch it
3. File the issue for the appropriate specialist
4. Fix the root cause AFTER the test completes, not during

### Cleanroom test infrastructure

To enforce non-intervention, a tripwire + audit system was built:
- `tripwire.py` (cron, 1min): monitors kanban DB for operations with `run_id IS NULL` (manual operations) + monitors bd bead status changes that don't correlate with worker activity (±5min window)
- `audit.sql`: post-test SQL query that returns `CLEAN` (zero violations) or `CONTAMINATED`
- `CLEANROOM-TEST-PLAN.md`: 14-test plan covering every edge case

**The tripwire detects:**
- Manual kanban operations: `archived`, `unblocked`, `completed`, `blocked` events with `run_id IS NULL`
- Manual card creation: tasks with `created_by='user'` and no `idempotency_key`
- Manual bd changes: bead status changed but no worker card completed within ±5 minutes

**The audit is the source of truth.** PO's claims about non-intervention are NOT trusted. The kanban DB tracks every event with a `run_id` — dispatcher operations have it, manual operations don't. This can't be faked.

## card_exists() in auto-dispatch.sh is DEAD CODE (DISCOVERED Jul 2026)

The `card_exists()` function in `auto-dispatch.sh` queries `hermes kanban list --json` and checks each task's `idempotency_key` field. But the **API does not return `idempotency_key`** — 0 out of 106 tasks had it in the JSON response.

```bash
# THIS NEVER WORKS — the API omits idempotency_key from list responses
card_exists() {
  existing=$(hermes kanban list --json | python3 -c "
    for t in json.load(sys.stdin):
      if t.get('idempotency_key') == '$key' ...  # always None!
  ")
}
```

The idempotency key IS stored in the SQLite database (`tasks.idempotency_key` with an index), and `kanban create --idempotency-key` prevents duplicates at creation time. But the `card_exists()` pre-check was always dead code — it never prevented anything.

**The real dedup** is at the SQLite level during `kanban create`. But when you archive a card, the DB-level dedup stops matching (archived cards are excluded from the dedup check), so `kanban create` happily creates a new card for the same bead.

**Fix:** Rewrite `card_exists()` to query SQLite directly:
```bash
card_exists() {
  local key="$1"
  local existing
  existing=$(sqlite3 "$KANBAN_DB" \
    "SELECT 1 FROM tasks WHERE idempotency_key='$key' AND status!='archived' LIMIT 1;" 2>/dev/null)
  [ "$existing" = "1" ]
}
```

## Board scanner can't distinguish transient vs permanent failures (DISCOVERED Jul 2026)

The board scanner treats ALL failures as transient — auto-unblock after 2min cooldown and retry. But a worktree branch conflict (`'feature/X' is already used by worktree at '...'`) is **permanent** — no amount of retrying fixes it. The scanner created an **infinite loop**: unblock → spawn_failed (worktree conflict) → gave_up → unblock → repeat **48 times**.

**Root cause:** The scanner classifies `spawn_failed` as `transient` unconditionally:
```python
if block_kind == "transient":
    # auto-unblock after 2min cooldown
    hermes kanban unblock {task_id}
```

But `spawn_failed` with a worktree conflict error should be classified as **permanent** — the error will never resolve without human cleanup of the stale worktree.

**Fix needed:** Add failure pattern classification:
- **Transient** (retry-worthy): 429 rate limit, connection timeout, process killed (OOM)
- **Permanent** (don't retry): worktree conflict, branch not found, missing binary, permission denied

Detection heuristic: if the same error message appears N times (e.g., ≥3) with identical content, escalate instead of retrying. The scanner already tracks `consecutive_failures` — use the count to distinguish:
```python
if consecutive_failures >= 3:
    # PERMANENT — escalate, don't retry
    block_kind = "needs_input"  # surfaces to human
else:
    block_kind = "transient"  # auto-retry
```

## bd close may not persist in Dolt (DISCOVERED Jul 2026)

Running `bd close <id>` printed success (`✓ Closed ...`) but the bead's status remained `open` on subsequent `bd show` and `bd ready` calls. The Dolt embedded database may have a commit delay or the close wrote to a different Dolt instance (if multiple project directories share `.beads/embeddeddolt/`).

**Impact:** The bead stayed open → `bd ready` kept showing it → auto-dispatch kept creating cards for it → tech-lead kept trying to "implement" a PRD bead → cascading failures.

**Workaround until bead-sync deployed:** Always verify `bd close` actually persisted:
```bash
bd close <id>
# Verify it stuck:
bd show <id> --json | python3 -c "import sys,json;d=json.load(sys.stdin);exit(0 if d.get('status')=='closed' else 1)"
```

If it didn't persist, try `bd update <id> -s closed` as an alternative.
