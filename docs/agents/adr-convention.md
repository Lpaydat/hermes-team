# ADR Convention (append-only)

Team-level convention for Architecture Decision Records. Per-venture `docs/adr/`
directories follow this doc; gate skills and the tracker doc reference it.
Drill: `dev-workflow-battle-tests/test33-adr-supersession.py`.

## Location and naming

- Each venture keeps its ADRs in the venture repo under `docs/adr/`.
- One decision per file.
- Filename: `ADR-NNN-<slug>.md` — `NNN` zero-padded, monotonically increasing
  within the venture (`ADR-001-file-based-json-store.md`, `ADR-002-...`).
  Take the next free number; numbers are never reused.

## Template

Every ADR has a header block and these sections, in order:

```markdown
# ADR-NNN: <title>

- Status: Accepted
- Date: YYYY-MM-DD
- Deciders: <who>
- Introduced-by: <bead id of the architecture ticket that produced this ADR>
- Supersedes: ADR-NNN        <- only when replacing an earlier ADR

## Decision
## Context
## Alternatives Considered
## Consequences
## Citations
```

Every ADR is introduced by a bead (architecture ticket); its id goes in the
`Introduced-by:` header line. That bead is the tracker handle for the ADR —
supersession (below) runs on it.

### Citations — sources named, quotable

Same citation rule as the rest of the team (see `docs/agents/issue-tracker.md`
and the wayfinding skill): every input to the decision is cited with a **named
source** and a **short quotable line**. Valid sources: the idea-brief bead
(`hermes-teams-<id>`), a map ticket id, a prior ADR (`ADR-NNN`), or a human
answer (intercom exchange / escalation comment — quote the decisive line).

```markdown
## Citations
- brief bead `hermes-teams-abc` — "readings must survive a device restart"
- prior ADR `ADR-001` — "revisit when a second writer appears"
```

Uncited design intent does not enter an ADR.

## Status vocabulary and the append-only rule

Statuses: `Accepted` | `Superseded`.

**ADR files are append-only: once accepted, a file is never edited and never
deleted.** Consequence: `Superseded` is a *derived* status — the OLD file keeps
saying `Accepted` forever, because updating it would mean editing it.
Supersession is discoverable only through:

1. **Forward (new → old):** the NEW ADR's header line `Supersedes: ADR-NNN`.
2. **Reverse (old → new):** the tracker's native supersede relation between the
   beads that introduced each ADR:

   ```bash
   bd supersede <old-adr-bead> --with=<new-adr-bead>
   ```

   `bd show <old-adr-bead>` then names the replacing bead (in `--json`: a
   dependency with `dependency_type: "supersedes"`), and that bead's
   ADR is the successor. Note: `bd supersede` also auto-closes the old bead
   with a reference to the replacement — that is expected.

So: changing a decision = write a new ADR with the next number + a
`Supersedes:` header, create/point its architecture-ticket bead, and run
`bd supersede`. The old file stays byte-identical.

## Brownfield (retro-ADRs)

When a venture is adopted with existing code, ONE as-is inventory card
(architect skill `brownfield-intake`, drill:
`dev-workflow-battle-tests/test36-brownfield-intake.py`) produces retro-ADRs
that record the de-facto architecture as a citable baseline. Retro-ADRs
follow this convention (template, append-only, citations) with these deltas:

- **Status.** Retro-ADRs carry status
  `Accepted (status quo — accepted, not endorsed)` — accepted as the
  operative state, not endorsed as the right design. Misgivings go to
  Consequences and to debt beads in the venture's own tracker (bounded:
  3–5 retro-ADRs and 2–4 debt beads per intake — inventory, not audit).
- **Numbering — the ADR-000 series.** Retro-ADRs use a distinct series so the
  baseline is visually separate from decided-forward ADRs:
  `ADR-000.1-<slug>.md`, `ADR-000.2-<slug>.md`, … — sub-numbers monotonic,
  never reused, series closed after intake. Normal forward ADRs still start
  at `ADR-001`. A forward ADR that replaces baseline behaviour supersedes the
  retro-ADR the normal way (`Supersedes: ADR-000.N` + `bd supersede`).
- **Header.** `Introduced-by:` carries the inventory card/bead id.
- **Citations.** Retro-ADRs document decisions nobody wrote down, so **code
  citations are valid sources**: named source = the file with a line number
  (file:line), quotable line = the decisive line of code or comment. The
  quotable line is always wrapped in straight double quotes — even when it
  quotes code; backticks wrap the named source only. The venture spec is
  likewise a valid source. Example:

  ```markdown
  ## Citations
  - code `plantcare/override_store.py:41` — "merged = {**defaults, **overrides}"
  - spec `docs/specs/mvp-slice.md` — "bundled JSON dataset, no network call"
  ```

Later gates and forward ADRs cite retro-ADRs exactly like normal ADRs;
`ADR-000.2` is as citable as `ADR-002`. Append-only applies unchanged.
(Flow introduced by ticket hermes-teams-1y1.7.)

## Complete example

```markdown
# ADR-002: SQLite store replaces the file-based JSON store

- Status: Accepted
- Date: 2026-07-11
- Deciders: architect
- Introduced-by: hermes-teams-x2y
- Supersedes: ADR-001

## Decision

Move reading persistence to SQLite (`data/readings.db`); the JSONL file is
imported once and then frozen.

## Context

The reminder scheduler introduces a second writer; ADR-001 explicitly deferred
that case.

## Alternatives Considered

- File locking on JSONL: rejected — fragile across crashes.
- Postgres: rejected — operational overkill for one device.

## Consequences

- Migrations become a thing; add a schema_version table.
- ADR-001's zero-dependency property is given up knowingly.

## Citations

- prior ADR `ADR-001` — "revisit when a second writer appears"
- map ticket `hermes-teams-m4p` — "scheduler and ingest write concurrently"
```

After writing this file, its author ran
`bd supersede <ADR-001's bead> --with=hermes-teams-x2y`; `ADR-001-*.md` was not
touched and still reads `Status: Accepted`.
