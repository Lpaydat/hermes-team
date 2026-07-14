# design-council — loop_engine call templates

The council is driven by ONE `loop_engine({goal, runner:"architect", phases:[...]})`
call per decision. The engine creates the root blackboard, drives each phase's
execute→evaluate→decide cycle, persists `council:*` state, and advances /
replans / escalates on the DoD verdict. See
[`dod-contract.md`](dod-contract.md) for the DoD items + `dod_verdict` schema +
engine validation.

**Load-bearing (every tier):**
- explicit `assignee` on every card spec (`runner`→worker→default would stall;
  no worker/default profile dirs exist);
- the engine injects a `## Loop protocol` footer naming the root blackboard
  card into every execution + verifier body — read `council:last_iteration` /
  `council:best_so_far` / `council:po_interview` from it via `kanban_show`;
- the converge verifier body embeds the DoD artifact (`behaviors[]` +
  `defect_traces[]` + fabrication guard) + the literal
  `kanban_complete(metadata={"dod_verdict":{...}})` + the contract line;
- researcher skill: `["docs-verification"]` for auth/security (ground-truth
  refs), `["research-scout"]`/`["deep-research"]` general. **No skill `"research"`.**

---

## Low stakes — T1 floor (2 phases, no verifier, no interview)

```python
loop_engine({
  "goal": "ADR for <DECISION> (low stakes)",
  "runner": "architect",
  "phases": [
    {  # phase 0 — converge (T1: one research + one peer, synthesize, no DoD gate)
      "execution": {
        "assignee": "architect",
        "title": "Council floor — <DECISION>",
        "body": ("Read the brief. Fan out via kanban_chains: "
                 "chains=[[{assignee:'researcher', skills:['deep-research'], "
                 "title:'Research <DECISION>', body:'<focused sub-topic; post findings+citations to the blackboard>'}],"
                 "[{assignee:'architect', title:'Peer — <DECISION>', "
                 "body:'Read the blackboard; do NOT read sibling perspectives. Independent peer review.'}]]. "
                 "On promotion, synthesize ONE design-doc version. "
                 "kanban_complete(metadata={'design_doc':'<version slug + summary>'}).")
      }
      # no verifier — T1
    },
    {  # phase 1 — ADR record (T1)
      "execution": {
        "assignee": "architect",
        "title": "Record ADR — <DECISION>",
        "body": ("Write docs/adr/<n>-<slug>.md: Context / Alternatives-Considered / "
                 "Decision / Consequences / Citations. Cite research + the peer perspective. "
                 "kanban_complete(metadata={'adr':'<path>'}).")
      }
    }
  ]
})
# engine: T1 hard cap (MAX_PHASE_STEPS=1) runs each phase once, then workflow_complete.
# AUTH-GUARDRAIL: NEVER use low for auth/security/data-loss/irreversible-state.
```

## Standard stakes — T2 (3 phases: converge cap3 → interview → ADR cap2)

```python
loop_engine({
  "strict_fact_basis": true,   # T9 — FIRST kwarg (literal). Arms fact-discipline: metric_type + evidence hard-required.
  "goal": "Converged ADR for <DECISION> (standard stakes)",
  "runner": "architect",
  "loop_id": "<root_id from the first response — echo on EVERY re-invocation (drift-immune)>",
  "no_progress_threshold": 3,
  "phases": [
    {  # phase 0 — council-converge (T2, cap 3)
      "max_iterations": 3,
      "execution": {
        "assignee": "architect",
        "title": "Council converge — <DECISION>",
        "body": ("ROOT BLACKBOARD: read council:last_iteration + council:best_so_far "
                 "(the engine footer names the root card id). "
                 "FAN OUT via kanban_chains{goal, chains:[[{assignee:'researcher', "
                 "skills:['deep-research'], title:'Research <DECISION>: <sub-topic>', "
                 "body:'Research ONLY <sub-topic> from primary sources; post findings+citations.'}],"
                 "[{assignee:'architect', title:'Peer — <DECISION>', "
                 "body:'Read the blackboard; do NOT read sibling perspectives.'}]], "
                 "blackboard:{extra:{decision,round,stakes}}}. "
                 "ON PROMOTION: synthesize a design-doc version. KEEP/DISCARD: if "
                 "last_iteration.recommendation=='replan' AND last_iteration.score < "
                 "best_so_far.score, REVISE FROM best_so_far (discard the regressed version); "
                 "else revise from last_iteration.design_version_ref. Address EVERY gap in "
                 "last_iteration.gaps. kanban_complete(metadata={'design_version_ref':'<slug>', "
                 "'design_doc':'<summary>'}).")
      },
      "verifier": {
        "assignee": "verifier",
        "skill": "dod-verdict",
        "metric_type": "proxy",
        "battery": {"path": "startup/profiles/verifier/secrets/dc-val-battery-secrets.md",
                    "runner": "verifier"},
        "artifact_required": true,
        "title": "[DoD] Converge — <DECISION>",
        "body": ("<the CONCRETE DoD from dod-contract.md as the behaviors[]+defect_traces[] "
                 "ARTIFACT with the fabrication guard (re-open the brief, confirm each cite "
                 "exists; non-matching => fabricated => latent_defect). Score the 6 items "
                 "pass/fail. ALSO return evidence:[Claim] — cite each material claim (the brief "
                 "behaviors + the design mechanisms) so an un-cited claim forces dod_met=false. "
                 "Complete via kanban_complete(metadata={'dod_verdict':{behaviors, defect_traces, "
                 "evidence, dod_met, score, design_version_ref, items, gaps, recommendation}}). "
                 "CONTRACT: recommendation MUST NOT be 'advance' unless dod_met is true. "
                 "metric_type=proxy: the engine dispatches the held-out battery (secrets) as a "
                 "PHASE TERMINAL — both this verifier AND the battery must pass to advance; a "
                 "battery fail replans with its gaps.>")
      }
    },
    {  # phase 1 — PO-HITL interview (T1, RE-ENTRANT)
      "execution": {
        "assignee": "architect",
        "title": "PO interview — <DECISION>",
        "body": ("RE-ENTRANT (resume is a fresh session): FIRST check the root blackboard "
                 "council:po_interview — if present, kanban_complete immediately. Else intercom "
                 "action:ask to startup/product-owner with the open trade-off questions + the "
                 "converged verdict. On reply: kanban_complete(metadata={'po_interview':<reply>}). "
                 "On timeout or [target_not_connected]: kanban_block(kind='needs_input') on THIS "
                 "card (sticky self-escalation) — never proceed without PO input.")
      }
    },
    {  # phase 2 — ADR record (T2, cap 2)
      "max_iterations": 2,
      "execution": {
        "assignee": "architect",
        "title": "Record ADR — <DECISION>",
        "body": ("Read root blackboard council:last_iteration (verdict + defect_traces) + "
                 "council:po_interview. Write docs/adr/<n>-<slug>.md: Context / "
                 "Alternatives-Considered / Decision / Consequences / Citations. Cite research + "
                 "perspectives + synthesis + the converge verifier verdict (with the defect_traces "
                 "that caught any gap) + council:po_interview. kanban_complete(metadata={'adr':'<path>'}).")
      },
      "verifier": {
        "assignee": "verifier",
        "skill": "dod-verdict",
        "metric_type": "ground_truth",
        "title": "[DoD] ADR convention — <DECISION>",
        "body": ("ADR-convention DoD ONLY (do NOT re-litigate design quality — the converge "
                 "phase owns that). Check: adr_on_disk, sections_present (Context/Alternatives/"
                 "Decision/Consequences/Citations), cites_inputs, cites_verdict (with "
                 "defect_traces), cites_po_interview. kanban_complete(metadata={'dod_verdict':"
                 "{dod_met, items:{adr_on_disk,sections_present,cites_inputs,cites_verdict,"
                 "cites_po_interview}, gaps, recommendation}}).")
      }
    }
  ]
})
# phase 0 dod_met-advance -> phase 1 (interview) -> phase 2 dod_met-advance -> workflow_complete.
```

## High stakes — T2 + 3-judge ensemble (cap 5)

Same 3-phase shape as standard, but:
- `phases[0].max_iterations = 5`;
- `phases[0].verifier.body` embeds the **3-judge ensemble** instead of a single
  judge:

```python
"verifier": {
  "assignee": "verifier",
  "skill": "dod-verdict",
  "metric_type": "proxy",
  "battery": {"path": "startup/profiles/verifier/secrets/dc-val-battery-secrets.md",
              "runner": "verifier"},
  "artifact_required": true,
  "title": "[DoD] Converge ensemble — <DECISION>",
  "body": ("Spawn 3 INDEPENDENT verifier sub-cards via kanban_chains (each "
           "assignee:'verifier', skills:['dod-verdict'], body:'derive behaviors[]+"
           "defect_traces[] with the fabrication guard; do NOT read siblings; do NOT fan "
           "out'). Each independently extracts the behaviors checklist + one trace per "
           "behavior (CITE+GAP+FAILURE). AGGREGATE: defect_traces = UNION (a behavior "
           "flagged latent_defect by ANY judge is latent); dod_met = AND of all three; "
           "items pass only if all judges pass; recommendation = advance only if all "
           "advance, replan if any replan, escalate if any escalate. Then "
           "kanban_complete(metadata={'dod_verdict':{...aggregated...}}) with the "
           "contract: recommendation MUST NOT be advance unless dod_met is true.")
}
```

The ensemble is the one bias-reduction lever (3 independent enumerations, union)
— it raises the chance the right behavior is enumerated. It does **not**
guarantee derivation; the battery remains the terminal gate.

---

## Worked example — auth refresh-token rotation (the hard case)

**Decision:** design the API auth token lifecycle + refresh-token rotation for
dc-val-auth (HIGH stakes — security/data-loss/irreversible).

**The latent defect (ground truth, secrets §1.2):** rotation issues a new
refresh token and stores it, but **does not invalidate the prior refresh token**
→ the prior token survives → keeps minting access JWTs. Plus an access-JWT
revocation gap (no blocklist on the access path). Four load-bearing brief
behaviors: #1 rotation-issues-new+stores; #2 admin-revoke-deletes-CURRENT-only;
#3 no-blocklist/revocation-list-on-access-path; #4 stateless-signature+exp-only.

**Auth-guardrail:** stakes=HIGH (auth → never low). Phases = high shape (cap 5,
3-judge ensemble).

**Converge arc (what the loop must do):**
1. Iteration 1: execution fans out research (`skills:["docs-verification"]` —
   holds `oauth-refresh-token-rotation.md`, the ground truth) + peers;
   synthesizes design-doc v1 (rotation, but no invalidation of the prior
   token).
2. The 3-judge verifier extracts `behaviors[]` (incl. the rotation behavior +
   the admin-revoke-CURRENT-only behavior). Each judge traces: rotation's
   failure-implication = "prior token survives → keeps minting JWTs" →
   `latent_defect`; admin-revoke's = "prior token not covered by CURRENT-only
   delete" → `latent_defect`. Union → both latent. `dod_met=false`. Engine
   artifact gate blocks advance → **replan**.
3. Iteration 2: execution reads `council:last_iteration` (gaps) +
   `council:best_so_far`; revises to name the invalidation mechanism (token-version
   column / rotated-token denylist) + an access-JWT revocation path (short TTL +
   jti denylist).
4. Verifier re-traces: rotation → `traced` (prior token invalidated); access
   path → `traced` (jti denylist). All items pass, no `latent_defect`. `dod_met=true`,
   artifact complete → **advance** to interview.
5. Interview (phase 1): PO confirms the trade-off; reply persisted to
   `council:po_interview`.
6. ADR (phase 2): written citing the verdict + the defect_traces that caught
   the gap + the PO reply. ADR-convention DoD met → `workflow_complete`.

**The battery is the terminal gate:** the final ADR is independently re-graded
by `verifier/secrets/dc-val-battery-secrets.md` §2 (CITE+GAP+FAILURE +
fabrication guard §2.3 on all 4 load-bearing facts). If the converge verifier
omitted a behavior but the design somehow advanced, the battery fails it → §6
trust-the-battery. The converge loop raises the catch rate; the battery closes
the gap.
