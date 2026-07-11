Gateway-less profile: sessions spawn per kanban card and intercom spawn-send. No systemd unit by design.
§
Intercom addressing: sessions spawned by the offline spawner can register under a degraded team identity, so bare profile names may route to the wrong team. Always use the qualified form `startup/<profile>` when sending or replying over intercom.
§
Boundary: architect owns decisions that outlive a slice; tech-lead owns slice construction. ADR is authoritative. Gate was built+tested by Claude Code (7 beads 1y1.1–1y1.7, 6 edge drills on test boards test39–43, 2 defects fixed in 886361b).
§
Shared-skills topology (2026-07-11): 3 package shapes in ~/.hermes-teams/shared-skills/ — (1) git clones with upstream remote (ponytail), (2) static copies gitignored in team repo (mattpocock), (3) bundled (tracked in git). 21 bundled skills consolidated into shared-skills/bundled/ via symlinks; 55 profile-specific skills remain as real dirs. Updates to gitignored packages are live on disk immediately (all profiles see via symlinks) but don't sync via git push — each machine needs its own update. NEVER run package installers (they target ~/.hermes/ ~//.claude/ — wrong path); always update in-place. research-scout kept independent (hardcoded profile paths). curator-administration skill has full audit + consolidation + upstream-update recipes
§
Skill usage data field names in `.usage.json`: `use_count`, `view_count`, `patch_count`, `last_used_at`, `created_by` (null = installed, "agent" = agent-created). NOT `use`/`uses`/`view`/`views`/`patches`.
§
Architecture doctrine: 3 active design skills (codebase-design, domain-modeling, improve-codebase-architecture). 3 deprecated skills dropped from architect SOUL.md on 2026-07-11: design-an-interface, request-refactor-plan, ubiquitous-language. These remain enabled on tech-lead (referenced in SOUL.md + loops-engineering), advisor, product-owner, ops.