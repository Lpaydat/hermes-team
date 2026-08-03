# Design Gap Analysis: tech-lead-execute — verify FAIL→close merges

## Symptom (from live test)

| # | Observation | Why it happened |
|---|-------------|-----------------|
| 1 | verify FAIL flows unconditionally to close | Edge `verify→close` has **no `condition`** (template line 76). It fires on every terminal verdict. |
| 2 | Fix cards (`t_8e6b5119`) completed AFTER close merged | The verifier created them via `kanban_create` inside its node body. Per gauntlet lesson #3/#11, **cards created inside a node body are invisible to the workflow graph** — the engine does not wait for them. verify completed the instant the verifier finished *creating* the cards, not when the cards finished. |
| 3 | Instance completes with an unfixed Critical finding | Direct consequence of #1 + #2: close ran with `verdict=FAIL`, stamped `verdict=merged`, and the instance reached its exit node. |

## Root cause

Two independent defects, either of which alone would be sufficient:

1. **Missing edge condition.** `{"from": "verify", "to": "close"}` has no guard. The engine's dispatch rule (`_node_is_dispatchable`, runtime.py:240-300) treats an unconditional incoming edge as AND-semantics: source `done` → target dispatchable. No verdict check.

2. **Fix work lives outside the graph.** The verify body_template says *"FAIL: create fix cards for developers, complete with verdict=FAIL"*. Those cards are `kanban_create`d (or equivalent) — not graph nodes, not `kanban_chains`. The engine cannot structurally block on them (lesson #3). So even if the edge *were* conditioned on PASS, the fix work would still be untracked by the instance.

The combination means: the graph has no concept of "fixes are pending," and it has no gate preventing close on FAIL.

## Answering the four questions

### (1) Should verify→close only fire on PASS?

**Yes, but alone it's insufficient.** Adding `{"from":"verify","to":"close","condition":"${nodes.verify.output.verdict} == 'PASS'"}` prevents the false merge. But on FAIL the workflow would then **deadlock** — close never dispatches, no other edge consumes FAIL, and the instance hangs (the dead-branch skipper can't skip an exit node whose sole source is terminal-but-not-firing without leaving the graph with no live nodes... actually it *can* skip it, but then the instance completes as skipped/failed with no fix work having happened). A condition on close is necessary but must be paired with a FAIL destination.

### (2) Should verify FAIL create a back-edge to a fix node?

**Avoid a back-edge.** The proven pattern (see `dev-review-loop.json`) is a **DAG with conditional forward edges**, not a cycle. Gauntlet lesson #4: dead-branch propagation can't traverse cycles, and lesson #5: unconditional back-edges block initial dispatch. The correct shape is:

```
verify --PASS--> close
verify --FAIL--> fix --> re-verify --PASS--> close
                              \--FAIL(iter<cap)--> fix   (this IS a back-edge, must be conditional + capped)
                              \--iter>=cap--> close (escalate)
```

The re-verify→fix back-edge is acceptable *if* it carries an iteration cap (`max_iterations` or a `${...iteration...}` condition) — the validator (model.py:307-335) enforces this at load time.

### (3) Is the unconditional verify→close correct because the verifier creates fix cards independently?

**No.** This is the core misconception. "Independent fix cards" is exactly the pattern gauntlet lessons #3 and #11 flag as broken: `kanban_create` inside a node body is a **no-op for graph tracking**. The parent node completes when the agent finishes *issuing* the cards, not when the cards finish. There is no mechanism — structural or conditional — that makes close wait for those cards. The current design silently drops the fix-and-reverify obligation on the floor.

### (4) The right design — three concrete options

---

#### Option A — Conditional DAG (mirror dev-review-loop)  ⭐ recommended

Keep the graph explicit and engine-enforced. Add a `fix` node and a `re-verify` node. No reliance on out-of-graph cards.

```jsonc
"nodes": [
  // ... plan, verify (unchanged bodies, but verify NO LONGER creates fix cards) ...
  {
    "id": "fix",
    "profile": "developer", "skill": "developer-loop",
    "body_template": "Verifier findings: ${nodes.verify.output.findings}. Fix all FAIL findings. Use kanban_chains if multiple files.",
    "depends_on": ["verify"]
  },
  {
    "id": "re-verify",
    "profile": "verifier", "skill": "adversarial-review",
    "body_template": "Re-verify the FIXED integrated feature. Set verdict PASS|FAIL|ESCALATE.",
    "depends_on": ["fix"]
  }
  // close unchanged
],
"edges": [
  {"from":"plan","to":"verify","condition":"${nodes.plan.output.plan_complete} exists"},
  {"from":"verify","to":"close","condition":"${nodes.verify.output.verdict} == 'PASS'"},
  {"from":"verify","to":"fix","condition":"${nodes.verify.output.verdict} == 'FAIL'"},
  {"from":"verify","to":"close","condition":"${nodes.verify.output.verdict} == 'ESCALATE'"},
  {"from":"fix","to":"re-verify"},
  {"from":"re-verify","to":"close","condition":"${nodes.re-verify.output.verdict} == 'PASS'"},
  {"from":"re-verify","to":"fix","condition":"${nodes.re-verify.output.verdict} == 'FAIL' AND ${nodes.re-verify.iteration} < 3", "max_iterations": 3},
  {"from":"re-verify","to":"close","condition":"${nodes.re-verify.output.verdict} == 'ESCALATE'"}
]
```

- **Pros:** Fully engine-enforced. Close physically cannot fire until a PASS or ESCALATE. Fix work is a graph node — engine waits for it. Mirrors the already-proven `dev-review-loop`. No out-of-graph card tracking needed.
- **Cons:** More nodes. The single `fix` node must internally fan out if verify finds findings across multiple tasks (it can call `kanban_chains` — and since `fix` is the caller, it structurally blocks until terminals done). Fixed iteration cap (3) — beyond that, ESCALATE.
- **Verify body change:** remove the "create fix cards" instruction; verify just stamps verdict + findings. The graph routes FAIL→fix.

---

#### Option B — Structural blocking inside verify (push the loop into kanban_chains)

Keep 3 graph nodes. Rewrite the verify body so that on FAIL it calls `kanban_chains` to create a `fix → re-verify-passthrough` chain whose terminal blocks verify until fixes are done **and re-verified PASS**. verify completes only when the chain's terminal is done.

- **Pros:** Minimal graph change (still plan→verify→close, edge stays unconditional). The loop complexity lives in the verify body where the agent can adapt finding count dynamically.
- **Cons:** Pushes correctness into body text — the thing gauntlet lesson #1 calls out as "IGNORED" by the agent. The verifier must call `kanban_chains` (not `kanban_create`), must wait, must re-read the terminal's verdict, and must then re-stamp its *own* verdict to PASS before completing. Fragile: if the agent skips any step, the invariant breaks silently. Also re-verify inside a kanban_chains sub-chain doesn't bump the *graph's* verify iteration counter, so the iteration cap must be enforced in body logic. **This is the pattern the gauntlet already proved fragile** (body text is not enforcement).

---

#### Option C — Honest terminal FAIL (no loop, no false merge)

Accept that a verify FAIL at this integration stage is a planning failure, not something to auto-fix in-graph. Make FAIL an honest terminal:

```jsonc
{"from":"verify","to":"close","condition":"${nodes.verify.output.verdict} == 'PASS' OR ${nodes.verify.output.verdict} == 'ESCALATE'"},
{"from":"verify","to":"fail-terminal","condition":"${nodes.verify.output.verdict} == 'FAIL'"}
```

Where `fail-terminal` is a tech-lead node that creates a replan/fix backlog card (via `kanban_chains`, so it's tracked), then completes the instance with `verdict=failed-needs-replan`. The instance completes honestly as "failed — needs replan" instead of falsely as "merged."

- **Pros:** Simplest. No cycle, no deadlock, no fragile body logic. Honest state — the board shows a real failure, not a fake merge. Close only ever sees PASS/ESCALATE.
- **Cons:** No automatic fix-and-retry at the integration layer. Every verify FAIL becomes a human-or-tech-lead replan event. Acceptable if integration-stage FAILs are rare; costly if they're common (you lose the dev-review-loop's iteration benefit).

---

## Recommendation

**Option A.** It's the only option that makes correctness a property of the *graph* (engine-enforced) rather than the *body text* (agent-discretionary, per gauntlet lesson #1). It directly reuses the pattern already validated in `dev-review-loop.json`. Options B and C are fallbacks if the added nodes prove too heavyweight.

Regardless of option chosen, **remove the "create fix cards for developers" instruction from the verify body** — out-of-graph card creation is the root cause of symptom #2 and must not be relied upon for any downstream gating.
