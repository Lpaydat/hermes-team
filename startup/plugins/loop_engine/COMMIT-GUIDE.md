# COMMIT-GUIDE — loop_engine v2 atomic commit

How to stage the **v2 converge-loop** work as one atomic commit, without
smoke-board DBs or cron runtime state riding in via `git add -A`.

> Authority: bead `hermes-teams-hhi` (T7). Scope = this plugin + its tests + the
> profile/config + skill doc-fixes that constitute the v2 feature. Everything
> else is either runtime state or unrelated drift.

---

## INCLUDE — belongs in the v2 commit

Stage these explicitly (`git add <path>`), never blind `git add -A`:

### 1. loop_engine plugin (the feature)
```
startup/plugins/loop_engine/                 # plugin.yaml, __init__.py, tools.py, schemas.py
startup/plugins/loop_engine/SPEC.md          # design authority (v2 enhancement)
startup/plugins/loop_engine/README.md        # consumer how-to + v1→v2 migration
startup/plugins/loop_engine/test_loop_engine*.py        # all v2 test_battery/citation/discover/dod_linter/
                                                         # evidence/metric_type/root_id/strict_fact_basis +
                                                         # schema_v2_fields + install_smoke + e2e + base
startup/plugins/loop_engine/test_debug_loop_skill_v2_contract.py
```

### 2. Top-level + profile config
```
startup/config.yaml                          # plugin enablement
startup/profiles/*/config.yaml               # debugger, developer, ops, product-owner,
                                             # qa, researcher, scout, tech-lead,
                                             # venture-builder, verifier
```

### 3. Skill doc-fixes (markdown shipped with v2)
```
startup/profiles/debugger/skills/software-development/debug-loop/SKILL.md
startup/profiles/qa/skills/coordination/team-delegation/SKILL.md
startup/profiles/qa/skills/coordination/team-observability/SKILL.md
startup/profiles/qa/skills/software-development/live-testing/SKILL.md
startup/profiles/qa/skills/software-development/live-testing/references/kanban-orchestration-patterns.md
startup/profiles/qa/skills/software-development/qa-protocol/references/*.md
startup/profiles/product-owner/skills/software-development/project-discovery/references/visual-and-notification-routing.md
startup/profiles/product-owner/skills/software-development/task-hygiene-validator/references/*.md
startup/profiles/tech-lead/skills/software-development/loops-engineering/references/*.md
```

---

## EXCLUDE — do NOT stage with the v2 commit

These are runtime state / scratch / out-of-scope. They will ride into `git add -A`
unless you stage selectively.

### Board DBs (smoke / test runs mutate them)
```
startup/kanban/boards/test88-design-v2/kanban.db     # gitignored (line 131) BUT still tracked
startup/kanban/boards/*/kanban.db                    # any other mutated board DB
```
**`test88-design-v2/kanban.db` is still tracked** — gitignoring does not untrack it.
Untrack it at commit time (with user approval):
```
git rm --cached startup/kanban/boards/test88-design-v2/kanban.db
```

### Cron runtime state (completed counters, next_run_at)
```
startup/profiles/ops/cron/jobs.json
startup/profiles/product-owner/cron/jobs.json
startup/profiles/scout/cron/jobs.json
startup/profiles/tech-lead/cron/jobs.json
startup/profiles/venture-builder/cron/jobs.json
```
These are tracked as config by design, but their working-tree edits are runtime
drift — leave them unstaged for the v2 commit (or `git checkout -- <path>` to
discard the runtime counters if a clean tree is wanted).

### Scratch / out-of-scope
```
.claude/dispatch-session.md               # session scratch
startup/tests/                            # parallel-dispatch test, not loop_engine v2 — stage separately
__pycache__/                              # bytecode (already gitignored)
```

---

## Ready-to-use staging sequence

```bash
# 0. stay on the branch
git checkout test/design-v2

# 1. INCLUDE — the v2 feature (explicit paths, no -A)
git add startup/plugins/loop_engine/
git add startup/config.yaml
git add startup/profiles/*/config.yaml
git add startup/profiles/debugger/skills/software-development/debug-loop/SKILL.md
git add startup/profiles/qa/skills/coordination/team-delegation/SKILL.md
git add startup/profiles/qa/skills/coordination/team-observability/SKILL.md
git add startup/profiles/qa/skills/software-development/live-testing/SKILL.md
git add startup/profiles/qa/skills/software-development/live-testing/references/kanban-orchestration-patterns.md
git add startup/profiles/qa/skills/software-development/qa-protocol/references/
git add startup/profiles/product-owner/skills/software-development/project-discovery/references/visual-and-notification-routing.md
git add startup/profiles/product-owner/skills/software-development/task-hygiene-validator/references/
git add startup/profiles/tech-lead/skills/software-development/loops-engineering/references/
git add .gitignore                                  # the hygiene fix itself (this bead)

# 2. EXCLUDE — verify none of these are staged
git status --short
#   expect NO 'A ' / 'M ' lines for:
#     startup/kanban/boards/test88-design-v2/kanban.db
#     startup/profiles/*/cron/jobs.json
#     .claude/dispatch-session.md
```

### Untracking the smoke board DB (separate step, needs approval)
```bash
# only after the v2 commit, with explicit user authority:
git rm --cached startup/kanban/boards/test88-design-v2/kanban.db
git commit -m "chore: untrack test88 smoke board DB (gitignored, runtime state)"
```
