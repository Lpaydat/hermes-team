Gateway-less profile: sessions spawn per kanban card and intercom spawn-send. No systemd unit by design.
§
Intercom addressing: sessions spawned by the offline spawner can register under a degraded team identity, so bare profile names may route to the wrong team. Always use the qualified form `startup/<profile>` when sending or replying over intercom.
§
Architecture gate built+tested by Claude Code (7 beads 1y1.1–1y1.7, 6 edge drills on test boards test32–43, 2 defects fixed in 886361b). Test boards still on disk. No production task has entered the gate yet. v2 redesign: architect is proactive design partner for new projects (design phase before tickets), reactive gate for incremental changes. See docs/workflow-redesign-v2.md.
§
Shared-skills topology: 3 package shapes in ~/.hermes-teams/shared-skills/ — git clones with upstream (ponytail: chmod u+w → git pull → chmod a-w .git), static copies gitignored in repo (mattpocock: sync stale skills via `gh api repos/mattpocock/skills/contents/...`), bundled (tracked in git). 21 bundled consolidated into shared-skills/bundled/ via symlinks. Updates to gitignored packages are live immediately but don't sync via git push. NEVER run installers (target ~/.hermes/~/.claude/). research-scout kept independent (hardcoded profile paths).
§
Skill usage data fields in `.usage.json`: `use_count`, `view_count`, `patch_count`. User prefers kanban_chains over delegate_task (subagents are fragile). docs/ gitignored — force-add or use startup/docs/.
§
Architecture doctrine: 3 active design skills (codebase-design, domain-modeling, improve-codebase-architecture). 3 deprecated skills dropped from architect SOUL.md on 2026-07-11: design-an-interface, request-refactor-plan, ubiquitous-language. These remain enabled on tech-lead (referenced in SOUL.md + loops-engineering), advisor, product-owner, ops.
§
GitHub: SSH auth works (Lpaydat); gh CLI re-authed 2026-07-11 (token in keyring, scopes: repo/read:org/gist/workflow). Repo: git@github.com:Lpaydat/hermes-team.git. Local main pushes to origin/main; pulls from origin/config (unusual tracking). docs/ is gitignored — use startup/docs/ with git add -f.