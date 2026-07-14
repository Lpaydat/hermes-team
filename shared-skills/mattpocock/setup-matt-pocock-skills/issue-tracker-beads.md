# Issue tracker: Beads (bd)

Issues and PRDs for this repo live in the beads tracker (local Dolt DB). Use the `bd` CLI for all operations. Run `bd prime` once per session for full workflow context.

## Conventions

- **Create an issue**: `bd create --title="..." --description="..." --type=task|bug|feature|epic --priority=2`. Priority is 0-4 (0=critical), never "high"/"low".
- **Read an issue**: `bd show <id>` (includes dependencies, parent, labels); `bd comments <id>` for the comment thread.
- **List issues**: `bd list --status=open`, `bd search <query>`, `bd query` for the query language.
- **Comment on an issue**: `bd comment <id> "..."`
- **Apply / remove labels**: `bd label add <id> <label>` / `bd label remove <id> <label>` (or `-l` at create time; children inherit parent labels unless `--no-inherit-labels`).
- **Close**: `bd close <id> --reason="..."` (multiple ids allowed). Never `bd edit` — it opens $EDITOR and blocks agents.

Ids look like `<repo>-<hash>` (e.g. `hermes-teams-a23`). Children may use dotted suffixes (`a23.1`).

## Pull requests as a triage surface

**PRs as a request surface: no.** Beads is repo-local; there is no PR surface. `/triage` reads issues only.

## When a skill says "publish to the issue tracker"

Run `bd create`.

## When a skill says "fetch the relevant ticket"

Run `bd show <id>` and `bd comments <id>`.

## Wayfinding operations

Used by `/wayfinder`. The **map** is an epic bead with **child** beads as tickets — all native beads concepts, no body conventions needed.

- **Map**: an epic bead labelled `wayfinder:map`, holding the Destination / Notes / Decisions-so-far / Not-yet-specified / Out-of-scope body in its description. `bd create --title="<map name>" --type=epic --labels=wayfinder:map --description="<map body>"`.
- **Child ticket**: `bd create --title="<ticket name>" --parent=<map-id> --labels=wayfinder:<type> --no-inherit-labels --description="## Question ..."` with `<type>` one of `research`/`prototype`/`grilling`/`task`/`architecture`. `--no-inherit-labels` keeps the child from inheriting `wayfinder:map`. List children with `bd children <map-id>`.
- **Blocking**: native bead dependencies — `bd dep add <blocked-ticket> <blocker-ticket>` ("blocked depends on blocker"). `bd show <id>` renders both directions; `bd blocked` lists all gated tickets.
- **Frontier query**: `bd ready --parent=<map-id>` — open, unblocked descendants of the map, in priority order. First listed wins.
- **Claim**: `bd update <id> --claim` — sets assignee AND moves the ticket to `in_progress` in one atomic step, which removes it from `bd ready`. On beads the *status* is what gates the frontier (an open-but-assigned bead still shows in `ready` — verified), so always claim with `--claim`, not bare `--assignee`. `--claim` will not steal a ticket someone else already holds — it leaves the existing assignee in place, which is exactly how concurrent sessions skip claimed work. `bd ready --parent=<map-id> --claim` claims the first frontier ticket atomically.
- **Resolve**: `bd comment <id> "<answer>"` (the resolution comment), then `bd close <id>`. Append the context pointer to the map's Decisions-so-far by rewriting the map body: read it with `bd show <map-id>`, add the `- <ticket title> (<id>) — <gist>` line, write back with `bd update <map-id> --description="..."`.
- **Architecture tickets** (`wayfinder:architecture`): the engine routes them to the architect. The resolution is an ADR in the venture repo's `docs/adr/` per `docs/agents/adr-convention.md` (header `Introduced-by:` = the ticket id), the resolution comment cites it by number (`RESOLVED: <gist> — see ADR-NNN <path>`), and the map index line carries the ADR number.

**Deferred parents hide children**: children of a `deferred` bead are excluded from `bd ready`. Never defer a live map — the frontier would go dark.

**Hermes engine interaction**: when this repo is registered in `startup/active-projects.json`, the workflow engine auto-dispatches EVERY ready bead — including HITL wayfinder tickets (grilling/prototype), which must not run headless. Until wayfinder-aware dispatcher routing lands (hermes-teams-c6d.4), chart and work maps only while the repo is unregistered, or under direct supervision.
