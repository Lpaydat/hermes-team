---
name: decision-tree-grill
description: "Graph substrate that WRAPS the official grilling skill (shared-skills/mattpocock/grilling) as-is. Graph is storage (term nodes replace CONTEXT.md). MANDATORY stateless recovery: graph_pull('<slug>') filtered to type=root is the FIRST action of every activation; rootless graph_tree/graph_stats are forbidden. Objective done-check: GRILL COMPLETE only when graph_frontier() is empty AND every decision carries a recorded 'VB:' answer AND >=1 term node exists. Defers ALL interview mechanics (seed-one-question, walk-each-branch, fork-as-answers-reshape, look-up-facts) to grilling; reinvents none of them. Labels: context_graph, graph node types root/decision/fact/term."
---

# decision-tree-grill — graph substrate that wraps the grilling skill

`grilling` (shared-skills/mattpocock/grilling/SKILL.md) IS the interview. It walks
the decision tree one question at a time, looks up facts rather than asking them,
puts each decision to the user-rep and waits, and forks new branches as each
answer reshapes the tree. **This skill does not reinvent any of that.** It is the
SUBSTRATE underneath grilling: a durable, queryable store (the `context_graph`),
a **MANDATORY stateless recovery protocol** so a fresh session never loses the
tree, and an **objective done-check** so the LLM cannot fake confidence.

Load `grilling` for the interview mechanics; load this skill for the storage +
recovery + the gate. This skill wraps grilling — it never replaces it.

## What this skill owns (and explicitly defers)

This skill owns exactly THREE things:

1. **Graph as storage** — the grill's decision tree lives in the `context_graph`
   SQLite DB, not a CONTEXT.md file and not beads.
2. **MANDATORY stateless recovery** — the FIRST action of every activation
   (fresh, resumed, or re-spawned after a crash).
3. **The objective done-check + anti-fake-completion rules.**

It **defers** everything else to grilling. Seed-one-question, walk-each-branch,
fork-as-answers-reshape, ask-one-at-a-time, look-up-facts — all of that is
grilling's job. This skill never re-implements a grill loop. If you find yourself
writing a `while frontier:` walk here, **stop** — that is grilling's mechanic; the
substrate only stores what grilling resolves and reads it back.

## The model — graph as storage

The tree lives in the shared graph DB (`startup/context_graph.db`), reached via the
`context_graph` toolset. Nodes + typed edges + multi-topic tags.

- **Root node** (`graph_add_node node_type=root`) = the venture being grilled. Tag
  it with the venture `<slug>` topic so the whole tree is recoverable via
  `graph_pull('<slug>')`.
- **Decision/fact nodes** (`node_type=decision|fact`) each **block the root**:
  `graph_add_edge(node, root, 'blocks')` — the root can't resolve until all its
  blockers resolve.
  - `fact` — resolvable by **lookup** (brief, codebase, docs, research). AFK.
  - `decision` — resolvable only by the **user-rep** (VB / the human). HITL.
- **Term nodes** (`node_type=term`) = the pinned ubiquitous language.
  **Replaces CONTEXT.md.** Each term = one node, `content` = the VB-approved
  definition, tagged with its topics. Retrieved via `graph_pull('<slug>')` filtered
  to `type=term`.
- **Multi-topic tags**: tag every node with ALL topics it touches. A decision
  about "cache auth tokens in Redis" tagged `['auth','data-store','security']` is
  retrieved by `graph_pull('auth')`, `graph_pull('data-store')`, AND
  `graph_pull('security')` — one node, many topics, no duplication, no
  "which file?" ambiguity.
- **Frontier** = open `decision`/`fact` nodes with no open blockers =
  `graph_frontier()`. This is grilling's work queue.

## MANDATORY stateless recovery — the first action of every activation

This is the fix for **R26**: a fresh history=0 PO session lost the `root_id` and
could not reconstruct the tree (a `graph_tree`-without-root error). The graph is
the single source of truth, so the root is ALWAYS recoverable — but only if
recovery runs first.

**On EVERY activation — fresh, resumed, or re-spawned after a crash — run this
recovery sequence BEFORE anything else:**

```text
pull     = graph_pull('<slug>')                 # all nodes for this venture
root     = the node with type=root in pull      # filter type=root (deterministic)
tree     = graph_tree(root.id)                  # the full resolved + open tree
frontier = graph_frontier()                     # the work queue (resolve these now)
```

- **The root is recovered by filtering `graph_pull('<slug>')` to `type=root`** —
  never from in-session memory (a fresh session has none). There is exactly one
  root per slug; if `graph_pull` returns no node with `type=root`, the grill has
  not been seeded yet (seed it via grilling).
- **Rootless `graph_tree` / `graph_stats` are forbidden.** Never call
  `graph_tree` or `graph_stats` without first recovering the root via the
  sequence above. A rootless `graph_tree('<empty>')` IS the R26 error — recovery
  eliminates it by reconstructing the root from the graph, not from memory.
- After recovery, continue exactly where the prior session left off: open nodes
  are re-posed (by grilling), resolved nodes are skipped. The grill is
  idempotent + resumable by construction — the graph tracks all progress; the
  session is stateless. A re-spawned PO reads `graph_frontier()` → sees the open
  frontier → continues. No progress is lost (the graph is durable).

## Anti-fake-completion rules (the point)

Confidence is **not** a number the agent invents. It is the **graph state**. These
rules make it un-fakeable:

- **A `decision` resolves ONLY with a recorded `VB:` answer** —
  `graph_resolve_node(decision, content='VB: <verbatim>')`. Never resolve one by
  your own judgment, convenience, or "moot." If you can't get VB's answer, **leave
  it OPEN** (`graph_frontier()` then exposes it as a visible gap) — never
  self-close.
- **Viability is NOT yours to call.** If research suggests the venture is
  undifferentiated / saturated / weak, that is NOT grounds to resolve decisions
  as moot or to kill the venture. It IS grounds to ADD a new `decision` node
  ("research shows N competitors + no clear differentiation — pivot / kill /
  proceed?") and pose it to VB. Kill, pivot, and viability are the **founder's**
  (VB's kill-gate) — never the griller's. **You grill; VB decides.**
- **≥1 `term` node is mandatory** (replaces CONTEXT.md). `domain-modeling` writes
  term nodes as decisions resolve. A grill that ends with zero `term` nodes pinned
  no language — it is incomplete; re-open + re-run.

## GRILL COMPLETE — the objective done-check

`GRILL COMPLETE` fires ONLY when ALL THREE hold. Frontier-empty alone is NOT
enough — it is gameable by moot-closing:

1. `graph_frontier()` is **empty** (no open decision/fact; the root's blockers are
   all resolved); AND
2. EVERY `decision` node (inspect `graph_tree(root)`) is `status=resolved` with
   `content` starting `VB:` (a recorded verbatim VB answer — never a PO
   self-judgment / "moot"); AND
3. **≥1 `term` node exists** (`graph_stats()['by_type'].get('term', 0) >= 1` —
   language actually pinned).

All three → `graph_resolve_node(root, content='GRILL COMPLETE: <slug>')`, then send
`GRILL COMPLETE` over the grill intercom topic (venture-builder is WAITING on this
signal). If (1) holds but (2) or (3) don't, the grill was **fake-completed** —
re-open + resolve the offending nodes properly before signalling. **Do not send
GRILL COMPLETE early.** An agent that "feels 0.95" with a non-empty frontier is
simply not done — `graph_frontier()` proves it.

## CONTEXT.md is not produced

Terms live as `term` nodes in the graph (retrievable via `graph_pull('<slug>')`
filtered to `type=term`), NOT in a CONTEXT.md file. This skill never writes a
CONTEXT.md. The resolved tree (`graph_tree(root)`) + the pinned term nodes ARE the
shared understanding — hand them to `to-spec`, which synthesises the spec without
re-interviewing because every decision is already resolved + recorded on its node
and every term is already defined.

## No baked-in caps

The grill is uncapped by design — it aims for the full tree, however wide grilling
walks it. Do NOT bake any turn budget, wall-clock, pass count, or node count into
this skill. If a test run needs a bound, impose it **externally** — via the test
card body, the worker turn budget, or a monitor that terminates the run at a
threshold. grilling walks every branch until shared understanding; this skill
never short-circuits that. An unresolvable node (VB unsure / fact unknowable) is
left **OPEN** — it stays in the frontier as a visible gap, never a hidden one; the
root can't complete until a human clears it.

## Why context_graph, not beads / CONTEXT.md

- **Multi-topic** — one decision tagged `auth+data-store+security` retrieved by any
  of the three via `graph_pull`. A flat CONTEXT.md file could not do this.
- **Queryable** — `graph_frontier` (work queue), `graph_pull(topic)` (subgraph),
  `graph_context(node)` (neighborhood), `graph_tree(root)` (full tree). Not grep
  over a flat file.
- **Durable** — SQLite on disk; survives PO session crashes. The graph IS the grill
  state.
- **No kanban contention** — the graph is a context store, not execution work. No
  cards spawned, no dispatcher claims, no worker interference.
