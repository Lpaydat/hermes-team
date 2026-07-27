# Pipeline v3 Corrections (2026-07-23)

## Correction: grill is NOT optional

The `grill-rpc-ops/references/2026-07-22-build-queue-pipeline.md` reference file contains an outdated statement: "Grill is optional (runs as interactive session to stress-test briefs)."

**This was corrected by the user on 2026-07-23.** The grill is REQUIRED for every prototype build. The user said: "why grill optional? make it as required step." The self-grill skill already documents this correction in its "Pitfall: never make the grill optional" section, but the grill-rpc-ops reference file still carries the old text.

The build-queue-pipeline reference is in a pinned skill (grill-rpc-ops) and cannot be patched autonomously. When the skill is unpinned, update the "New model (current)" section to read: "Grill is REQUIRED (runs as interactive self-grill before every build)."

## Correction: sequential chain uses `--parent` on `kanban create`, not `kanban_link`

The reference says to use `kanban_link(parent=A, child=B)` to chain cards. The actual implementation in queue-builds.sh uses `hermes kanban create --parent <prev_id>` which creates the parent-child relationship at creation time. Both approaches work — `--parent` on create is simpler and is what the production script uses.

## Correction: builds assigned to `builder`, not `tech-lead`

The reference says "Create N kanban tasks (assigned to tech-lead)." The actual implementation assigns to `builder` — prototypes are built by the builder, not tech-lead. Tech-lead is production only, dispatched by PO after promotion.
