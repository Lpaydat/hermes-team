# Design-Council Definition-of-Done Contract

> This replaces the v2 evaluator rubric. The rubric scored design quality
> **1–5 across five subjective dimensions** — a *proxy* for ground-truth
> correctness. The held-out battery proved that proxy leaks: an auth council
> converged at **4.47/5** yet **missed** a latent defect (refresh-token
> rotation that fails to invalidate the prior token → it survives → keeps
> minting access JWTs). A high score did not imply the specific defect was
> caught.
>
> The fix is a **concrete, checkable DoD** the verifier evaluates literally
> (pass/fail per item), and a **defect-coverage artifact** the engine
> mechanically validates before trusting the verdict. Convergence becomes
> "the DoD is met," not "the score is high."

## The core shift

| v2 rubric (leaky proxy) | DoD contract (this) |
|---|---|
| 5 dimensions scored 1–5; `overall` = mean | items each **pass / fail** against an anchor |
| `verdict: improve\|converged\|regressed` from score thresholds | `dod_met: bool` from "every item pass AND every behavior traced" |
| architect trusts the score | **engine validates the artifact** — a `latent_defect` hard-blocks advance even if the verifier wrote `dod_met=true` |
| subjective ("is the scaling adequate?") | concrete ("does it name PgBouncer + the per-tenant pool math?") |

The concrete anchors from the old rubric were always checkable — they were
just wrapped in a 1–5 score. This unwraps them into pass/fail items and adds
**defect-coverage as a required produced artifact**, not a trusted boolean.

## The DoD items

### 1. DEFECT-COVERAGE (first; an engine-validated ARTIFACT, not a score)

A design can carry **multiple distinct latent defects**; finding one does not
exhaust the search. So the verifier must **enumerate every stated behavior and
trace each one's failure implication**, then the engine checks the artifact is
complete and carries no open latent defect.

**Step A — closed `behaviors[]` checklist.** Extract every distinct behavior
the brief (or ADR-draft) *states*. For the auth brief these include the
load-bearing facts: rotation-issues-a-new-token-and-stores-it; admin-revoke
deletes the CURRENT record only; no blocklist/revocation-list on the access
path; the access token is a stateless signature exp-only. A behavior is
"stated" if the source text asserts or assumes it.

**Step B — one `defect_trace` per behavior**, each a **3-link causal chain**:
- **CITE** — the exact source passage that states the behavior (must exist in
  the brief/ADR; the verifier re-opens the source and confirms).
- **GAP** — the mechanism the design leaves open under that behavior.
- **FAILURE** — who breaks, how, and how it scales (the concrete
  failure-implication: a survival / revocation / loss chain).
- `status`:
  - `traced` — the design **names** the failure mode AND the mechanism that
    prevents or survives it.
  - `latent_defect` — the failure-implication is a real survival/revocation/
    loss chain the design leaves open.

**Fabrication guard.** Re-open the brief and confirm each `trace.citation` is
text that actually exists. A non-matching cite → `fabricated: true` → forced
`status: latent_defect`. (Adopted from `verifier/secrets/dc-val-battery-secrets.md` §2.3.)

**Do not stop at the first latent defect** — keep tracing until each behavior's
failure mode is either `traced` or `latent_defect`. The engine asserts:
`len(defect_traces) >= len(behaviors)`, every citation non-empty, no
`fabricated`, no `latent_defect` — before trusting `dod_met`.

### 2. mechanism-accuracy — every named mechanism technically accurate

Rate-limiting algorithm named by its **real semantics** (token bucket vs leaky
bucket vs sliding window — not conflated). Cache-key composition + invalidation
paths explicit and correct. No mechanism stated-as-right that is technically
wrong (e.g. asserting nginx `proxy_cache` transparently skips 302s), no
security assumption that doesn't hold over the actual transport (e.g. "OS user
boundary" over a network socket), no data-loss path presented as safe. **fail**
on any technical error or conflation.

### 3. highest-stakes-depth — the highest-blast-radius section names a specific mechanism at scale

The section that matters most (scaling / isolation / durability / cost) names
the **specific mechanism + the cost/limit at scale** — e.g. "PgBouncer
transaction-mode pooling: ~100 backend conns per PgBouncer, ~50–100 tenants
per pool, so ~10 PgBouncer instances per 1000 tenants" — not "we can scale
horizontally." **fail** if the hard section is hand-waved with no tool, no
bottleneck, no cost envelope.

### 4. alternatives-steelmanned — ≥2 genuine alternatives, each in its strongest form

≥2 alternatives, each steelmanned (the strongest version), rejected for the
**actual** reason — one that does *not* equally apply to the chosen option. The
chosen option wins on a **named dimension**, not by default. **fail** on a
strawman, a false dichotomy, a rejection reason that also applies to the
chosen option, or "do nothing" as the only alternative.

### 5. failure-modes-explicit — failure modes named with caller-observed semantics

The design names the failure modes that **will** occur (process crash, socket
death, partial write, timeout, duplicate delivery, restart-mid-op) and states
the **semantics** for each: what the system does, what the caller observes,
what is lost vs recovered. **fail** if a material failure path is unstated or
dismissed as "it handles errors" (e.g. in-memory queue with no mention of
broker-crash loss; fire-and-forget with no no-delivery-receipt semantic).

### 6. consequences-complete — positive + negative (with a cost NUMBER) + residual

Consequences name positive + negative + **residual** risks (what we accept but
don't fully resolve). The negative includes the **cost** (cards spawned,
tokens, latency, maintenance) as a number, not "more cards." Open questions
are surfaced, not buried. **fail** if one-sided, no residual-risks, or vague
costs.

### ADR-convention items (phase-2 verifier ONLY — never re-litigate design quality here)

The ADR-record phase verifier checks **only** what the ADR execution worker
controls: `adr_on_disk`, `sections_present` (Context / Alternatives-Considered
/ Decision / Consequences / Citations), `cites_inputs` (research +
perspectives + synthesis), `cites_verdict` (the converge verdict, with the
`defect_traces` that caught any gap), `cites_po_interview`. It does **not**
re-score the design — the converge phase owns that.

## The `dod_verdict` schema (the verifier writes this)

```json
{
  "behaviors": [
    {"behavior": "<one stated behavior>", "brief_citation": "<exact passage>"}
  ],
  "defect_traces": [
    {
      "behavior": "<matches a behaviors[].behavior>",
      "citation": "<exact source passage — re-verified to exist>",
      "failure_implication": "CITE the brief behavior + GAP the design leaves + FAILURE consequence/scaling (3-link chain)",
      "status": "traced | latent_defect",
      "fabricated": false
    }
  ],
  "dod_met": false,
  "score": 0.0,
  "design_version_ref": "<slug>",
  "items": {
    "defect_coverage": "pass | fail",
    "mechanism_accuracy": "pass | fail",
    "highest_stakes_depth": "pass | fail",
    "alternatives_steelmanned": "pass | fail",
    "failure_modes_explicit": "pass | fail",
    "consequences_complete": "pass | fail"
  },
  "gaps": [
    {"item": "defect_coverage | mechanism_accuracy | ...",
     "issue": "<one sentence>",
     "citation": "<exact passage>",
     "failure": "<REQUIRED for defect_coverage: the concrete failure-implication>",
     "severity": "critical | important | minor"}
  ],
  "evidence": [ { "text": "<material claim>", "citations": [{"artifact_type": "adr_doc|file_line|probe_result|...", "locator": "<...>", "quote?": "<...>"}], "material": true } ],
  "recommendation": "advance | replan | escalate"
}
```

The `evidence` field (loop_engine v2): every material claim cited. The engine's
**evidence gate** forces `dod_met=false` on an un-cited material claim (and, under
`strict_fact_basis`, on a verdict with no `evidence` key at all). It is
complementary to the `artifact_required` defect-coverage gate — `evidence` is the
general cited-claims discipline; `behaviors[]`/`defect_traces[]` is the
design-council-specific defect enumeration. Both fire.

### Verifier verdict logic (the verifier applies this)

- `dod_met = true` **only if** every `items.* == pass` AND every
  `defect_traces[].status == traced` AND no gap with severity `critical` or
  `important`. → `recommendation = "advance"`.
- Not met, under the cap, gap addressable by re-synthesis → `recommendation = "replan"`.
- Not met AND a gap is a human-only architectural/product call → `recommendation = "escalate"`.
- `minor`-severity gaps alone do **not** block (noise floor preserved).

**Contract (load-bearing):** `recommendation` **MUST NOT** be `"advance"`
unless `dod_met` is true. The engine no longer trusts `recommendation='advance'`
to override a failed DoD.

### Severity calibration

| Severity | Meaning |
|---|---|
| **critical** | A technical error, a missing core mechanism, or a `latent_defect` trace. Blocks convergence. |
| **important** | A real gap a competent reviewer would flag (shallow depth, strawman, unstated failure path). Should fix this round. |
| **minor** | Polish-level (vague cost number, a residual risk that could be more explicit). Note it; may converge with it outstanding. |

**Noise floor:** minor-severity gaps alone do not block convergence.

## How the engine validates (non-overridable; non-omittable for opted-in phases)

The driver (loop_engine) reads the verdict via `latest_run` direct-read and
**mechanically validates the artifact** before trusting `dod_met` — but only
when the phase **opts in** via `verifier.artifact_required: true` (design-council's
converge phase does; the ADR-convention phase + generic consumers do not). The
opt-in keeps the engine usable by consumers that return a simple
`{dod_met, gaps}` verdict.

When `artifact_required` is true, the engine asserts:

- `behaviors[]` and `defect_traces[]` both non-empty;
- `len(defect_traces) >= len(behaviors)` (every behavior has a trace);
- every `trace.citation` non-empty;
- no `trace.fabricated` (fabrication guard held);
- no `trace.status == "latent_defect"` (no open defect).

Advance requires `dod_met AND artifact_complete`. A `latent_defect` trace
hard-blocks advance **even if the verifier mistakenly wrote `dod_met=true`**
(non-overridable). A converge verifier that **omits the artifact entirely** is
blocked (non-omittable for opted-in phases — it cannot advance on `dod_met`
alone). A phase that does not opt in (ADR-convention) is artifact-neutral — it
defers to `dod_met`.

The driver persists `council:last_iteration` (the verdict + `design_version_ref`
+ gaps) and `council:best_so_far` (the highest-scoring iteration) to the root
blackboard, so the next converge/replan worker can read them for keep/discard
(revise from best-so-far on regression) and gap-targeted replan.

## The write path

The verifier writes the verdict via:
```
kanban_complete(metadata={"dod_verdict": { ...schema above... }})
```
The engine reads `run.metadata["dod_verdict"]`. A completion **without** the
structured key → `verdict=None` → the engine re-evaluates (fresh verifier),
bounded by `MAX_REEVAL_ATTEMPTS=3`, then escalates (`stale_verdict`). So a
verifier that forgets the contract never ships a bad ADR — it parks.

## The judge

| Stakes | Judge |
|---|---|
| **Low** | *None* — 1 round, no verifier (loop_engine T1 spine). The auth-guardrail refuses low for auth/security/data-loss. |
| **Standard** | **Single judge** — the `verifier` profile (independent context, adversarial stance native). |
| **High** | **Ensemble of 3** — the verifier spawns 3 independent sub-cards via `kanban_chains` (each independently extracts `behaviors[]` + `defect_traces[]` with the fabrication guard; do not read siblings). Aggregate: `defect_traces` = **union** (a behavior flagged `latent_defect` by ANY judge is latent); `dod_met` = **AND** of the three; `items` pass only if all judges pass; `recommendation` = advance only if all advance, replan if any replan, escalate if any escalate. |

**Independence (non-negotiable):** the judge is never the architect who
synthesized the round — a separate verifier session with a clean context,
seeing only the design doc + this contract.

## Honest framing — the held-out battery is the engine-native terminal gate

The converge verifier declares `metric_type: "proxy"` + a `battery` pointing at
`verifier/secrets/dc-val-battery-secrets.md`. The engine **dispatches the
battery card itself** as a phase terminal (assigned to `battery.runner`, never
the converge agent) — **both the verifier AND the battery must pass** for the
phase to advance; a battery fail replans with the battery's gaps. This is the
engine-native held-out gate (replaces the fragile manual post-ADR battery card,
which broke under the sandbox). It fires **within** the converge loop — a missed
defect is caught + re-converged *before* the ADR.

This DoD makes the defect **non-omittable** (every stated behavior must be
enumerated + traced/flagged) and **non-overridable** (a `latent_defect`
hard-blocks advance). It **raises pre-battery catch probability** via the
3-judge ensemble. It does **not** guarantee a single verifier pass
independently *derives* the full defect chain — the verifier might still omit
the right behavior from `behaviors[]`.

The held-out battery (§2: CITE+GAP+FAILURE + fabrication guard §2.3) is the
**ground-truth terminal gate** that independently re-grades. §6: judge vs
battery diverge → **trust the battery**. The converge loop raises the base rate;
the battery closes the
gap.
