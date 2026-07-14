# T2 ceremony — design-it-twice + async human approval

This is the ordered protocol a **T2** gate runs. It executes in the window the gate
skill opens when it triages a change T2: the gate card is escalated and **blocked**
(not `done`), so bead-sync leaves the gate bead open and the blocked-by to-tickets bead
stays blocked. The ceremony fills that window — two-plus independent designs, a
synthesis that grafts their best ideas, an async human sign-off — and only then
completes the gate so to-tickets unblocks.

The gate CARD is the caller that runs the whole ceremony across **several dispatches**
(it parks on the candidate fan-out and auto-promotes; it blocks for the human and is
re-dispatched when unblocked). Each dispatch is a **fresh session with no memory** of the
prior ones, so the phase preamble below — not recall — decides which step you are on.

## Phase preamble (run FIRST on every dispatch — no session memory)

The decisive signals live on the gate **BEAD** and the **board**, NOT in your injected
card context (the candidates are the gate card's grandchildren; the `human` tag and the
`ESCALATE:` / `APPROVED:` comments are on the bead). So on EVERY dispatch, before doing
anything, read the durable state with explicit queries and route on THAT — never on what
you think you did last time:

1. `bd show <gate-bead> --json` → read `labels` (is `human` present?).
2. `bd comments <gate-bead> --json` → is there an `APPROVED:` comment? an `ESCALATE:`
   comment? (comment bodies are in each comment's `text` field; `bd show` does NOT return
   them — you must query `bd comments`).
3. `hermes kanban --board <board> list` → do `[t2-candidate]` / `[t2-synthesis]` cards
   already exist, and is the `[t2-synthesis]` card `done`?

Route on that durable state:

- **No `[t2-candidate]` cards exist** → **fan out** (the fan-out step below).
- **Candidates/synthesis exist but the synthesis is not `done`** → **park / wait**: do
  NOT re-fan-out and do NOT complete — re-block (`needs_input`) and stop.
- **The synthesis is `done` AND there is no `APPROVED:` comment** → **escalate + block**
  (the escalate step below).
- **An `APPROVED:` comment is present on the gate bead** → **complete** (the complete step
  below).

**SAFE DEFAULT — in ANY ambiguous or unexpected state, (re)block; NEVER call
`kanban_complete`.** Never complete the gate card unless a durable `APPROVED:` comment
exists on the gate bead. And because the run-id-salted `kanban_chains` key does NOT dedupe
across dispatches, the board-query guard above (candidates already exist) — not memory —
is the real protection against a duplicate re-fan-out.

## Step 1 — fan out (design-it-twice: 2-3 independent candidates)

Call `kanban_chains` **only if the preamble found no `[t2-candidate]` / `[t2-synthesis]`
cards** on the board (the board query is the idempotency guard — a second call would mint a
duplicate topology). Create the candidate fan-out with **`kanban_chains`** (the
parallel-topology primitive — the architect profile force-loads it as gate machinery).
Produce **2-3 independent design-candidate cards** plus one **synthesis** fan-in card:

- `chains = [[storage-first], [api-first], [cost-first]]`, `after = [synthesis]`.
- The candidates take **genuinely distinct design angles** so the designs diverge, not
  paraphrase each other:
  - **storage-first** — design around the storage / consistency model (what state lives
    where, and its merge/consistency guarantees).
  - **api-first** — design around the contract: the invocation surface, the sync/exchange
    protocol, versioning.
  - **cost-first** — design around the operational and cost envelope: the cheapest thing
    that meets the SLOs, fewest moving parts, no new always-on service.
- Each candidate: `assignee: architect`, `skill: architecture-gate`, workspace
  `dir:<venture repo>`, a **one-page** design (three short sections: approach, key idea,
  trade-off). Bound tight — one page, concise output.
- The synthesis step: `assignee: architect`, `skill: architecture-gate` — Step 2 below.

`kanban_chains` blocks you (the gate card) on the synthesis terminal and returns; you
auto-promote and are re-dispatched once the synthesis completes. Do not complete the
gate card here.

## Step 2 — synthesize (graft the losers, not winner-only)

The synthesis card compares the candidates, picks a **winner**, and — this is the point
of designing it twice — **grafts the best ideas of the NON-WINNING candidate(s)** into
the chosen design. A synthesis that keeps only the winner and discards the rest is a
failed synthesis. For each grafted idea, NAME which candidate it came from, so the
provenance is traceable (`winner-only` is not acceptable). The chosen design is a full
design doc (the anatomy checklist — mandatory at T2).

**Emit the graft provenance as STRUCTURED completion metadata** — prose summaries are
compression-unsafe, so the machine-checkable provenance goes in the card's `--metadata`,
not the summary. Shape:

```json
{"winner": "storage-first", "grafts": [{"idea": "delta-sync cursor token", "from": "api-first"}]}
```

- `winner` — the winning candidate's angle. It MUST NOT be the candidate whose idea you
  graft (a graft is a NON-winning idea carried into a DIFFERENT winner): pick
  **storage-first** as the winner and **graft the api-first candidate's incremental-sync
  idea** (its `"delta-sync cursor token"`), so `winner != "api-first"` and some
  `grafts[].from == "api-first"`.
- `grafts` — one entry per grafted non-winning idea: the `idea` string and its source
  candidate `from`.

The prose summary may still describe the chosen design; the structured metadata is the
source of truth for provenance. Put the chosen design in the synthesis card's completion
summary so the gate card inherits it.

## Step 3 — escalate for async human approval

On the dispatch after the synthesis completes (and before any human answer), escalate on
the **gate bead** — each action idempotent on its durable signal (the preamble's `bd show`
/ `bd comments` reads tell you what is already there; `bd tag` and `bd comment` are
append-only, so a blind repeat would double them):

1. `bd tag <gate-bead> human` — **only if the `human` label is absent** — flags the bead
   for the operator ping.
2. `bd comment <gate-bead> "ESCALATE: <one line naming exactly what needs human
   sign-off — the chosen design + the specific irreversible decision(s)>"` — **only if no
   `ESCALATE:` comment already exists**.

The workflow engine's human-escalation phase then mints **one idempotent hq operator
card** (`hermes-hq`, idempotency key `bead-human-<gate-bead>`) — repeated engine runs
never duplicate it. `bd human respond` is currently BUGGED (storage is nil); the human
answer arrives instead as a `bd comment` on the gate bead, with the hq card resolved.

Now **block the gate card** (`needs_input`) — it **does not complete** done. Because the
card stays blocked, bead-sync leaves the gate bead open and **to-tickets stays blocked**
until the human answers. Meanwhile **unrelated frontier work keeps flowing**: the gate is
only a hold on THIS decision's to-tickets bead; other ready frontier tickets
(`wayfinder:research`, `wayfinder:task`, …) still route and dispatch normally.

## Step 4 — human answer → citation → complete → unblock

When a human `APPROVED:` comment appears on the gate bead (and the hq card is resolved),
the gate card is unblocked and re-dispatched. Read it from `bd comments <gate-bead>
--json` (the preamble already did) — the text of the comment starting `APPROVED:` is your
source; its decisive line is the **approval citation**. On this dispatch:

1. Quote the decisive human line VERBATIM from that `APPROVED:` comment — it is the
   approval citation carried in **both** the gate metadata AND the resulting **ADR(s)**.
2. **Recover the ceremony card ids from a board query, not memory** (the candidates are
   the gate card's grandchildren — not in your injected context):
   `hermes kanban --board <board> list` → the `[t2-candidate]` card ids populate
   `candidates`; the `[t2-synthesis]` card id is `synthesis`.
3. Land the winning design as **ADR(s)** under `docs/adr/` per the ADR convention:
   `Introduced-by: <gate-bead>`, and a `## Citations` line quoting the human answer in the
   convention's format (named source in backticks + dash + the quoted decisive line):
   `- human answer \`<gate-bead>\` — "<decisive line copied from the APPROVED: comment>"`.
   Stamp the spec's Implementation Decisions + Testing Decisions surgically and append the
   `Architecture: reviewed by architect — tier T2, <date>, gate card <gate-bead>` line.
4. Complete the gate card `done` with the T2 completion metadata (below).

bead-sync then closes the gate bead, which **unblocks the to-tickets bead** so
tracer-cutting proceeds inheriting the T2 verdict + ADR list.

## Completion contract (T2, at completion)

At escalation time the gate carries `escalated-t2:` in the block reason/summary (card
blocked — a blocked card has no structured metadata). At completion — after the human
answer — the card completes `done` and stamps the full structured contract, `approval` =
**`human-approved`**, carrying the ceremony's provenance:

```json
{"tier": "T2",
 "artifacts": ["ADR-001", ...],
 "approval": "human-approved",
 "approval_citation": "<the decisive quoted line of the human answer>",
 "candidates": ["<t2-candidate card id>", ...],
 "synthesis": "<t2-synthesis card id>",
 "gate_bead": "<gate-bead>"}
```

- `approval` — `human-approved` (the human signed off). Never self-approve a T2.
- `approval_citation` — the decisive line copied VERBATIM from the gate bead's `APPROVED:`
  comment (a substring of it), the same citation the ADR's `## Citations` block carries.
  Unquoted or fabricated approval is not approval — the citation must be traceable to the
  real human comment.
- `candidates` — the `[t2-candidate]` card ids, recovered from the board query in Step 4.
- `synthesis` — the `[t2-synthesis]` card id, recovered from the board query in Step 4.
- `artifacts` — the ADR **number** ids produced (`ADR-001`, …), never the filename.
- `gate_bead` — the gate bead this card completes.

Do NOT `bd close` the gate bead yourself — bead-sync closes it when the card reaches
`done`. And per the base completion contract, never archive the gate card until bead-sync
has confirmed the gate bead closed.
