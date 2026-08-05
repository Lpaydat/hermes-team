# Hermes Kanban → Beads: Full Migration Feasibility Analysis

Condensed from a deep-analysis session (2026-08-05) that read `kanban_db.py`
(10,275 lines) + live `.db` dumps, all 42 beads schema migrations from source,
and exercised the real `bd` CLI. Full 16KB writeup lives at
`~/workspace/.hermes-teams/kanban-vs-beads-migration-analysis.md`.

## Beads Canonical Schema (from 42 migrations)

Beads backend = **Dolt** (versioned MySQL-compatible). Embedded (`.beads/embeddeddolt/`)
or server mode. Single overloaded `issues` table discriminates regular issues,
events, wisps (ephemeral), agents, roles, messages, gates by `issue_type` + metadata.

**Tables:** `issues` (60+ cols), `dependencies` (typed: blocks/tracks/related/
parent-child/discovered-from), `labels`, `comments` (UUID pk), `events`
(dedicated audit table), `metadata`/`config` (KV), plus views `ready_issues` +
`blocked_issues` (recursive CTE over blocks+parent-child deps).

**Key `issues` columns:** id, title, description, status (7 built-in + custom),
priority (0-4), issue_type, assignee, estimated_minutes, metadata (JSON),
due_at, defer_until, external_ref, spec_id, ephemeral, wisp_type, no_history,
agent_state, rig, started_at, closed_at, actor, payload, await_type, await_id,
waiters (for gates).

## Gap Matrix — what beads CANNOT do that Hermes kanban can

### 🔴 Critical gaps (require building new machinery)

| # | Hermes feature | Beads status | Impact |
|---|---|---|---|
| 1 | `task_runs` — per-attempt retry tracking (outcome/error/summary/PID/heartbeat) | **Missing** | No retry counting, no crash/timeout classification, no per-run summaries for the next worker |
| 2 | Claim-TTL + heartbeat + stale-claim reclamation + crash detection | Only `bd update --claim` (no TTL/expiry/PID/heartbeat) | Entire "is this worker alive?" subsystem missing |
| 3 | Typed block kinds (dependency/needs_input/capability/transient) + loop-breaker | Flat `blocked` status, no loop detection | Cron-unblock storms have no circuit breaker |
| 4 | `task_attachments` + `kanban_attach`/`kanban_attach_url` | **No `bd attach` command** | Files need external store + metadata convention |
| 5 | `kanban_notify_subs` → gateway push (Telegram/Discord/etc.) | **Missing** | No notification layer |
| 6 | Workspace management (scratch/worktree/dir + dispatcher injection) | **Missing** | Beads is a tracker, not an execution environment |
| 7 | Worker-config injection (skills/model/provider/reasoning/goal_mode) | **Missing** | Can't tell a worker what model/skills to use |
| 8 | `max_runtime_seconds` / timeout enforcement | **Missing** | No runtime concept |

### 🟡 Moderate gaps (lossy workarounds)

- Status model mismatch: Hermes has 9 statuses (incl. ready/review/scheduled);
  beads has 7 built-in (open/in_progress/blocked/deferred/closed/pinned/hooked).
  Custom statuses exist but dispatcher's `recompute_ready` + claim gating is Hermes-specific.
- Board isolation differs: Hermes = per-board SQLite; beads = single Dolt DB / `rig` col / repos.
- No `idempotency_key` on create (would need metadata-key convention + pre-check).
- No `session_id` provenance (could use metadata).
- No `consecutive_failures` circuit breaker.
- No task-lifecycle hooks (`_fire_kanban_lifecycle_hook`).
- No `build_worker_context` assembly (prior-attempt/comment caps, relative-age rendering).

### 🟢 Where beads is STRICTLY BETTER

- **Version history / time-travel** (Dolt commits, `bd history`, `--as-of`, `bd diff`) — Hermes has none.
- **Typed, multi-relationship dependencies** (blocks/tracks/related/parent-child/discovered-from + cycle detection) — Hermes only has untyped parent/child.
- **Federation** (`bd federation`), **branches** (`bd branch`), **distributed sync** (Dolt remotes).

## Verdict

**Full migration NOT feasible without building ~8 new subsystems.** Beads covers
the coordination/data layer (tasks, comments, deps, audit via Dolt history) but
lacks the entire dispatch-orchestration layer. Beads could replace the
*coordination layer*; the *dispatch layer* (runs/claims/heartbeat/blocks/
attachments/workspace/worker-config/notifications/runtime) must be rebuilt on
top of it — either as a Hermes-side adapter storing run/claim/heartbeat state
elsewhere, or as new beads features.

## Technique — how to inspect beads schema

The beads binary embeds its schema migrations; `bd sql` only works in server mode,
not embedded. To inspect the canonical schema:

1. **Read the migration source** at `~/workspace/beads/internal/storage/schema/migrations/`
   (42 files, `0001_create_issues.up.sql` through `0042_add_on_update_cascade.up.sql`).
   Each `*.up.sql` is a MySQL `CREATE TABLE` / `ALTER TABLE` / `CREATE VIEW`.
   `schema.go` embeds them via `//go:embed migrations/*.up.sql`.
2. **Bootstrap a scratch DB** to exercise the CLI live: `mkdir /tmp/bd-scratch &&
   cd /tmp/bd-scratch && bd init`. Create test issues with deps/comments/state
   changes, then `bd export --all -o out.jsonl` to see the full data model in JSON.
3. **Note: the ngin `.beads/` DB** (`~/workspace/ngin/.beads/`) is remote-backed
   and schema-migration-locked (v42→v53 pending, refuses to auto-migrate to avoid
   forking the shared remote schema). Read-only commands work; writes are blocked.
   Do NOT run `bd migrate` on it unless you are the single designated migrator.
