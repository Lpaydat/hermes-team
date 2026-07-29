# Dual-System Industry Comparison — How Production Trackers Handle Plan-vs-Execute

External benchmark for the beads+kanban split, answering: **is the split a
recognized pattern or a novel invention, and what do failure modes look like
elsewhere?** Produced 2026-07-29 from primary-source research (GitHub Projects
docs, Linear Method page, beads ARCHITECTURE.md, Hermes kanban docs, incident
notes). Complements `pipeline-complexity-analysis.md`, which is the *internal*
part-counting audit. This file is the *external* "is the pattern sound"
benchmark.

## The core finding

The plan-vs-execute split is a **recognized and universal conceptual pattern** —
every system separates planning from execution concerns. But virtually every
successful production system implements it as **one data store with layered
views/hierarchy**, NOT two separate databases. Hermes's beads (Dolt) + kanban
(SQLite) is a **novel variant**: a true dual-database architecture.

The question is not "is the split a good idea" — it is. The question is whether
the split should live in one store or two. **Industry consensus: one store,
many views.** Hermes deliberately chose two.

## How each system does it

### GitHub — Issues (data) + Projects (views): ONE STORE
- Issues and PRs are the atomic data; Projects are *views* over them.
- Bidirectional sync is automatic and instant because there's only one store.
- GitHub explicitly **redesigned Projects v1→v2 (2022)** to eliminate separate
  card objects that caused drift. Cards now reference issues directly. This is
  the most relevant lesson: they tried two objects, hit drift, merged to one.

### Jira — Epics → Stories → Subtasks: ONE STORE, HIERARCHY
- All are issue types in the same DB. The hierarchy is link relationships
  enforced by foreign keys within a single store.
- Boards (Scrum/Kanban) are views over issues, filtered by project/query.
- An epic's status is *derived* from its children — no separate status to sync.

### Linear — Direction → Building: ONE STORE, SINGLE MODEL
- ONE issue model: Initiatives → Projects → Issues → Sub-issues, all in one
  store, one GraphQL API.
- Linear's product pitch is speed through a unified model. They **explicitly
  rejected** Jira's type-proliferation. Their practice "Write issues not user
  stories" is a rejection of heavyweight planning artifacts.
- Cycles (sprints) are time-boxed views, not a separate data structure.

### GitLab — Issues + Boards + Epics: ONE STORE
- Epics + Issues + Milestones in one PostgreSQL DB.
- Boards are pure views — moving a card changes the issue's label, instantly
  visible everywhere.

### Military OODA — Observe → Orient → Decide → Act: SEPARATE PHASES, ONE RECORD
- The phases (plan vs. act) are separate, but the *record* is unified: one
  OPORD (operations order) document contains the plan, the tasks, and the
  timeline.
- SITREPs (situation reports) update the shared picture — this is closer to a
  single-store model with views than a dual-store model.
- **Key lesson:** separate the phases, not the record. Execution status flows
  back through updates to the same shared understanding.

## Why Hermes likely diverged (legitimate engineering reasons)

1. **Different write patterns** — beads is write-rarely (plan changes are
   deliberate, reviewed); kanban is high-frequency (heartbeats every few min,
   status transitions, comments). A Dolt DB optimized for git-sync and
   cell-level merge is a poor backend for a live task queue.
2. **Different distribution models** — beads is git-distributed for
   multi-machine collaboration; kanban is local to one dispatcher process.
   You can't easily put a live task queue in a git-synced Dolt DB without
   locking/contention.
3. **Different data models** — beads has rich issue semantics (deps, epics,
   acceptance criteria, proof, design docs). Kanban needs lean execution
   semantics (status, assignee, parent/child, workspace). Mixing them bloats
   both.
4. **Beads wisps already exist** — beads has ephemeral, local-only "wisp"
   issues that track execution steps and get squashed into digests. This is
   conceptually identical to kanban tasks, but beads solved it internally.
   This suggests the split may be historical (kanban predated beads
   integration) rather than a deliberate architecture.

## Failure modes of dual-store approaches

These are the documented and predictable problems. The first one already
happened in this system (see incident notes below).

### A. Referential integrity loss (drift)
A beads issue references a kanban task that was deleted, or a kanban task
references a beads issue that was renamed/closed. The link breaks silently.
**Documented instance (Jun 2026):** a `bd rename-prefix` operation broke the
binding between beads issue IDs and the agent's task tool — the Dolt DB had
`ai-nov-huq.15` but the CLI defaulted to database name `beads` and couldn't
find it, blocking the entire task lifecycle. A single rename broke the tracker.

### B. Dual maintenance (sync tax)
When a plan changes in beads, someone must manually update the kanban task(s).
When a kanban task completes, someone must mark the beads issue done. Single-
system approaches eliminate this entirely. In Hermes this burden falls on
agents and the workflow engine's bead-sync step.

### C. Conflicting source of truth
Beads says issue X is `open`; kanban says the implementing task is `done`.
Both can be "right" simultaneously. **Evidence:** incident notes show "issues'
status fields are not flipped to done because task done needs a per-issue
branch + working bd binding... status-flipping is bookkeeping."

### D. Visibility fragmentation
To see the full picture of a piece of work, you check two places: beads for
plan/dependencies/acceptance criteria, kanban for execution status/comments/
artifacts. Different systems give different answers to "what's the status of X?"

### E. Lifecycle coupling
Beads statuses (open → in_progress → closed) and kanban columns (triage → todo
→ ready → running → blocked → done → archived) don't map 1:1. One beads issue
may correspond to multiple kanban tasks (decomposition). The relationship is
many-to-many and without enforced linkage it degrades to "best effort."

### F. Doubled data-loss risk
Beads source of truth is a gitignored embedded Dolt DB. Kanban is a local
SQLite DB. If either is lost, half the project knowledge is gone.

## What Hermes can learn (ranked by leverage)

1. **From GitHub v1→v2: views, not copies (highest leverage).** Don't create a
   second store — create views. If kanban boards were a *view* over beads
   issues (filtering/grouping beads statuses into columns), you'd get the
   execution UX without dual-store drift. Beads already has ~90% of the data
   model: statuses map to columns, deps express hierarchy, comments exist,
   proof is supported.
2. **From Linear: one model, ruthless simplicity.** Linear rejected Jira's
   type-proliferation for a single unified issue model. Beads already has this
   (one issue type with parent-child links + epics). Adding kanban tasks
   reintroduces the complexity Linear explicitly rejected.
3. **From the military: one record, phase-based updates.** The OPORD contains
   plan + tasks + timeline in one artifact. Execution evidence (SITREPs/proof)
   lives ON the issue, not in a separate execution database. Beads already
   supports this: issues have description, design, acceptance_criteria, notes,
   and a proof concept.
4. **From beads wisps: ephemeral execution within one system.** Beads already
   solved ephemeral-execution tracking with wisps (local-only issues that
   squash into digests). Kanban tasks are the same thing in a different DB. If
   wisps exist, kanban tasks may be redundant wisps-in-a-different-DB.

## Strategic direction

The ideal end state (supported by every production tracker): **kanban as a view
over beads.** The hard part is the execution machinery (dispatcher, claiming,
workspaces, heartbeats, goal-mode) which is deeply coupled to the SQLite model.

Until unification, the minimum:
- Enforced automatic status sync (kanban completion → beads close)
- Explicit `beads_ref` linkage on kanban tasks (not just idempotency_key
  convention)
- Kanban tasks squashing back as beads proof on completion

## Verdict

The beads+kanban split is **architecturally defensible but operationally
fragile.** Every production system that faced this choice converged on single-
store-with-views. Hermes chose dual-store for legitimate reasons (different
write patterns, distribution models, data models) but likely also for
historical ones (kanban predated beads). The dual-store choice incurs a
permanent tax: sync maintenance, drift risk, and visibility fragmentation that
single-store systems don't pay. The path to unification is shorter than it
appears — beads has ~90% of the needed data model — but the execution-machinery
porting is non-trivial.
