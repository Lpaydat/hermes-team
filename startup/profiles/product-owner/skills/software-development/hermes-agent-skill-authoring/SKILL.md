---
name: hermes-agent-skill-authoring
description: "Author in-repo SKILL.md: frontmatter, validator, structure, and writing-quality principles."
version: 1.1.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [skills, authoring, hermes-agent, conventions, skill-md]
    related_skills: [plan, requesting-code-review]
---

# Authoring Hermes-Agent Skills (in-repo)

## Overview

There are two places a SKILL.md can live:

1. **User-local:** `~/.hermes/skills/<maybe-category>/<name>/SKILL.md` — personal, not shared. Created via `skill_manage(action='create')`.
2. **In-repo (this skill is about this case):** `/home/bb/hermes-agent/skills/<category>/<name>/SKILL.md` — committed, shipped with the package. Use `write_file` + `git add`. `skill_manage(action='create')` does NOT target this tree.

## When to Use

- User asks you to add a skill "in this branch / repo / commit"
- You're committing a reusable workflow that should ship with hermes-agent
- You're editing an existing skill under `/home/bb/hermes-agent/skills/` (use `patch` for small edits, `write_file` for rewrites; `skill_manage` still works for patch on in-repo skills, but not for `create`)

## Required Frontmatter

Source of truth: `tools/skill_manager_tool.py::_validate_frontmatter`. Hard requirements:

- Starts with `---` as the first bytes (no leading blank line).
- Closes with `\n---\n` before the body.
- Parses as a YAML mapping.
- `name` field present.
- `description` field present, ≤ **1024 chars** (`MAX_DESCRIPTION_LENGTH`).
- Non-empty body after the closing `---`.

Peer-matched shape used by every skill under `skills/software-development/`:

```yaml
---
name: my-skill-name               # lowercase, hyphens, ≤64 chars (MAX_NAME_LENGTH)
description: Use when <trigger>. <one-line behavior>.
version: 1.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [short, descriptive, tags]
    related_skills: [other-skill, another-skill]
---
```

`version` / `author` / `license` / `metadata` are NOT enforced by the validator, but every peer has them — omit and your skill sticks out.

## Size Limits

- Description: ≤ 1024 chars (enforced).
- Full SKILL.md: ≤ 100,000 chars (enforced as `MAX_SKILL_CONTENT_CHARS`, ~36k tokens).
- Peer skills in `software-development/` sit at **8-14k chars**. Aim for that range. If you're pushing past 20k, split into `references/*.md` and reference them from SKILL.md.

## Writing Quality Principles

A skill exists to make the agent's process more predictable. Predictability does **not** mean identical output every run; it means the agent reliably follows the same useful discipline.

Use these quality checks when writing or editing any skill:

1. **Optimize for process predictability.** Ask: what behavior should change when this skill loads? If a line does not change behavior, cut it.
2. **Choose the right context load.** A model-invoked Hermes skill pays for its description every turn. Keep descriptions focused on trigger classes and the skill's distinctive behavior. Put details in the body or linked references.
3. **Use an information hierarchy.** Put always-needed steps in `SKILL.md`; put branch-specific or bulky reference material in `references/`, `templates/`, or `scripts/` and point to it only when needed.
4. **End steps with completion criteria.** Each ordered step should say how the agent knows it is done. Good criteria are checkable and, when it matters, exhaustive: "every modified file accounted for" beats "summarize changes."
5. **Co-locate rules with the concept they govern.** Avoid scattering one idea across the file. Keep definition, caveats, examples, and verification near each other.
6. **Use strong leading words.** Prefer compact concepts the model already knows — e.g. "tight loop," "tracer bullet," "root cause," "regression test" — over long repeated explanations. A good leading word saves tokens and anchors behavior.
7. **Prune duplication and no-ops.** Keep each meaning in one source of truth. Sentence by sentence, ask whether the sentence changes agent behavior versus the default. If not, delete it rather than polishing it.
8. **Watch for premature completion.** If agents tend to rush a step, first sharpen that step's completion criterion. Split the sequence only when later steps distract from doing the current step well.

Common quality failures:

- **Premature completion** — the skill lets the agent move on before the work is genuinely done.
- **Duplication** — the same rule appears in multiple places and drifts.
- **Sediment** — stale lines remain because adding felt safer than deleting.
- **Sprawl** — too much always-visible material; push branch-specific reference behind pointers.
- **No-op prose** — generic advice the agent would already follow without the skill.

## Peer-Matched Structure

Every in-repo skill follows roughly:

```
# <Title>

## Overview
One or two paragraphs: what and why.

## When to Use
- Bulleted triggers
- "Don't use for:" counter-triggers

## <Topic sections specific to the skill>
- Quick-reference tables are common
- Code blocks with exact commands
- Hermes-specific recipes (tests via scripts/run_tests.sh, ui-tui paths, etc.)

## Common Pitfalls
Numbered list of mistakes and their fixes.

## Verification Checklist
- [ ] Checkbox list of post-action verifications

## One-Shot Recipes (optional)
Named scenarios → concrete command sequences.
```

Not every section is mandatory, but `Overview` + `When to Use` + actionable body + pitfalls are the minimum for the skill to feel like a peer.

## Directory Placement

```
skills/<category>/<skill-name>/SKILL.md
```

Categories currently in repo (confirm with `ls skills/`): `autonomous-ai-agents`, `creative`, `data-science`, `devops`, `dogfood`, `email`, `gaming`, `github`, `leisure`, `mcp`, `media`, `mlops/*`, `note-taking`, `productivity`, `red-teaming`, `research`, `smart-home`, `social-media`, `software-development`.

Pick the closest existing category. Don't invent new top-level categories casually.

## Workflow

1. **Survey peers** in the target category:
   ```
   ls skills/<category>/
   ```
   Read 2-3 peer SKILL.md files to match tone and structure.
2. **Check validator constraints** in `tools/skill_manager_tool.py` if unsure.
3. **Draft** with `write_file` to `skills/<category>/<name>/SKILL.md`.
4. **Validate locally**:
   ```python
   import yaml, re, pathlib
   content = pathlib.Path("skills/<category>/<name>/SKILL.md").read_text()
   assert content.startswith("---")
   m = re.search(r'\n---\s*\n', content[3:])
   fm = yaml.safe_load(content[3:m.start()+3])
   assert "name" in fm and "description" in fm
   assert len(fm["description"]) <= 1024
   assert len(content) <= 100_000
   ```
5. **Git add + commit** on the active branch.
6. **Note:** the CURRENT session's skill loader is cached — `skill_view` / `skills_list` will not see the new skill until a new session. This is expected, not a bug.

## Cross-Referencing Other Skills

`metadata.hermes.related_skills` unions both trees (`skills/` in-repo and `~/.hermes/skills/`) at load time. You CAN reference a user-local skill from an in-repo skill, but it won't resolve for other users who clone the repo fresh. Prefer referencing only in-repo skills from in-repo skills. If a frequently-referenced skill lives only in `~/.hermes/skills/`, consider promoting it to the repo.

## Editing Existing In-Repo Skills

- **Small fix (typo, added pitfall, tightened trigger):** `skill_manage(action='patch', name=..., old_string=..., new_string=...)` works fine on in-repo skills.
- **Major rewrite:** `write_file` the whole SKILL.md. `skill_manage(action='edit')` also works but requires supplying the full new content.
- **Adding supporting files:** `write_file` to `skills/<category>/<name>/references/<file>.md`, `templates/<file>`, or `scripts/<file>`. `skill_manage(action='write_file')` also works and enforces the references/templates/scripts/assets subdir allowlist.
- **Always commit** the edit — in-repo skills are source, not runtime state.

## Common Pitfalls

1. **Using `skill_manage(action='create')` for an in-repo skill.** It writes to `~/.hermes/skills/`, not the repo tree. Use `write_file` for in-repo creation.

2. **Leading whitespace before `---`.** The validator checks `content.startswith("---")`; any leading blank line or BOM fails validation.

3. **Description too generic.** Peer descriptions start with "Use when ..." and describe the *trigger class*, not the one task. "Use when debugging X" > "Debug X".

4. **Forgetting the author/license/metadata block.** Not validator-enforced, but every peer has it; omitting makes the skill look half-finished.

5. **Writing a skill that duplicates a peer.** Before creating, `ls skills/<category>/` and open 2-3 peers. Prefer extending an existing skill to creating a narrow sibling.

6. **Expecting the current session to see the new skill.** It won't. The skill loader is initialized at session start. Verify in a fresh session or via `skill_view` using the exact path.

7. **Letting skills accumulate sediment.** A skill should get shorter or sharper over time. When adding a rule, remove the old wording it replaces; don't layer advice forever.

8. **Writing no-op prose.** "Be careful," "be thorough," and "use best practices" rarely change model behavior. Replace with a checkable completion criterion or a stronger leading word.

9. **Linking to skills that don't exist in-repo.** `related_skills: [some-user-local-skill]` works for you but breaks for other clones. Prefer only in-repo links.

10. **Naming plugin tools unclearly (Jul 2026).** A tool named `delegate_and_wait` was completely skipped by the tech-lead model — it fell back to manual `kanban_create` + sleep-polling instead. The model didn't understand from the name that it was supposed to CALL this tool rather than manually creating cards. The rename to `kanban_delegate` (with "This is the ONLY way to create dev/verifier cards" in the description) fixed it (5/5 validation). **Rule**: tool names should use the verb-noun pattern of existing kanban tools (`kanban_create`, `kanban_block`, `kanban_complete`) so the model recognizes them as first-class operations. Avoid vague names that don't communicate what the tool does or when to use it instead of manual alternatives.

11. **Stuffing skill descriptions with trigger synonyms (Jul 2026).** A skill description listed 4-5 trigger phrases that were all synonyms for the same branch: "plan this", "start a project", "build this", "what should we work on next." This is duplication — synonyms that rename a single branch should be collapsed into one trigger. Per the `writing-great-skills` principle: one trigger per branch, and keep the description to triggers plus any "when another skill needs…" reach clause. Every word in a description increases context load, so a description earns harder pruning than the body.

12. **Omitting leading words (Jul 2026).** Skills written without leading words (compact concepts like _tracer-bullet_, _minimal_, _tight_) lose both token efficiency and execution anchoring. A leading word recruits priors the model already holds, anchoring a whole region of behavior in the fewest tokens. Hunt for opportunities to collapse restated qualities into a single pretrained word.

13. **Claiming a skill is fixed without verifying (Jul 2026).** After rewriting `dev-dispatch` to remove hardcoded `--board startup`, the user asked "why it still ref `--board startup`?" — the reference was still there. The fix was applied to the skill body but a separate mention of `HERMES_KANBAN_BOARD` in the explanatory text was missed. **Rule**: after any skill edit, re-read the full file (via `skill_view`) and grep for the exact pattern you claimed to remove. Never claim "fixed" without evidence.

14. **Asking permission to fix issues the user already told you to fix (Jul 2026).** The user loaded `writing-great-skills` and said "did you follow this skill?" When the agent identified violations (duplicate triggers, no leading words, no-ops), it asked "Want me to rewrite both skills fixing these issues?" — the user responded "why ask? why not follow what I told you?" **Rule**: when the user gives a clear instruction (load a skill, follow it, fix the skills), execute the fix immediately. Asking for confirmation after a clear directive is corner-cutting, not collaboration.

15. **Creating design options where none exist (Jul 2026).** During a grilling session about per-project boards, the agent presented "Option A: dispatch card goes on the project board" vs "Option B: dispatch card goes on team board, but tells PO which project board to create cards on." The user responded: "why to make things unnecessary complex? PO gets card from board A, then it should just dispatch to board A." **Rule**: during design discussions, if the natural design has a single path (same board throughout, same data store, no branching), state it directly. Do not manufacture complexity by presenting options that introduce unnecessary coordination — the user will catch it every time.

16. **Repeatedly failing to read active-projects.json despite 10+ corrections (Jul 2026).** The workflow engine used `find_bead_projects()` to scan directories for `.beads/` dirs instead of reading `active-projects.json`. The user corrected this pattern more than 10 times across sessions, each time with increasing frustration. The final fix: delete `find_bead_projects()` entirely, replace with `load_projects()` that reads the JSON file, and treat an empty list as a silent exit. **Rule**: when a user has corrected the same behavior multiple times, do not patch incrementally — rewrite the function from scratch with the correct pattern baked in. Incremental patches to the same broken function are evidence of not listening.

17. **Letting session dump files accumulate and pollute search results (Jul 2026).** After running dozens of kanban tasks, `sessions/request_dump_*.json` files accumulated in profile directories. When grepping for old path references, these frozen historical records dominated the output, making it look like active files still had the old paths. **Rule**: when auditing for stale references, explicitly filter out `sessions/`, `cron/output/`, `.bak`, and `_archived/` paths. Historical session dumps are frozen records, not active config — they should never block a migration.

18. **Verifier passing with known bugs (Jul 2026).** The adversarial-review skill's PASS condition was "zero Critical/Important findings + all ACs verified." The verifier found a real bug (delay=0 rapid calls → multiple executions) that wasn't covered by any acceptance criterion. It said "PASS, but here's a bug" and merged code with a known defect. The user caught this: "isn't that the bug? we pass with 0 issues on first verify?" **Root cause**: acceptance criteria (what PO writes during planning) ≠ definition of done (is this code production-quality?). ACs can't anticipate every edge case. **Fix**: PASS now requires zero findings at ANY severity (Critical, Important, Minor, Note) — including edge cases beyond the ACs. A bug the tests miss is still a bug. The loop only stops when the verifier finds nothing. **Rule**: when writing verification skills, never let PASS coexist with a known finding. If the verifier found something, it's a FAIL regardless of whether an AC covers it.

19. **Moving shared config between sessions without updating all references (Jul 2026).** Moved `active-projects.json` from `~/.hermes-teams/startup/profiles/product-owner/config/` to `~/.hermes-teams/startup/` (team-level, shared across profiles). Found 29 references across scripts, skills, cron jobs, SOUL files, and reference docs — with at least 4 different path patterns. **Rule**: when moving a shared config file, grep ALL of `~/.hermes-teams/startup/` for every path pattern. Patch scripts first, then skills, then cron jobs.json. Filter out `sessions/`, `cron/output/`, `.bak`, `_archived/` — frozen historical records that should not block migration.

20. **Symlinked plugins need `realpath` not `abspath` for path bootstrapping (Jul 2026).** A plugin installed via symlink (`profiles/<p>/plugins/intercom → ../../../_shared/intercom/plugin`) used `os.path.abspath(__file__)` to locate its sibling packages. But `abspath` follows the symlink path literally — it resolves to `profiles/<p>/plugins/intercom/`, not the real `_shared/intercom/plugin/`. The import `from broker import IntercomClient` failed with `No module named 'broker'` because the broker package lived at the symlink target, not the symlink path. **Fix**: use `os.path.realpath(__file__)` — it resolves the symlink to the actual filesystem path, so `os.path.dirname` walks up from the real location. **Rule**: any plugin loaded via symlink that computes its own path must use `realpath`, not `abspath`. Test by enabling the plugin on a profile and checking the gateway log for import errors.

21. **Plugin toolsets must be explicitly listed in profile config (Jul 2026).** A plugin was enabled (`hermes plugins enable intercom`) and showed as enabled in `hermes plugins list`, but the tool wasn't available to the agent. The gateway log showed no errors. Root cause: the profile's `config.yaml` has a `toolsets:` list that whitelists which toolsets are active. The plugin provides the `intercom` toolset, but it wasn't in the list. The plugin was "enabled" (discoverable) but not "activated" (in the toolset whitelist). **Fix**: add `- intercom` under `toolsets:` in each profile's `config.yaml`, then restart the gateway. **Rule**: enabling a plugin via `hermes plugins enable` makes it discoverable, but if the profile has a `toolsets:` whitelist, the plugin's toolset must also be listed there. Check with `hermes tools list --profile <p>` — the toolset should show `✓ enabled`, not just appear in `hermes plugins list`.

22. **Eating your own dog food: use the dev workflow to build dev workflow features (Jul 2026).** The intercom feature was built entirely through the dev workflow pipeline: PO wrote PRD + beads, workflow engine dispatched, tech-lead delegated, developer built, verifier reviewed — 4 beads, 3 fix chains, 2 auto-resolved escalations, 47 tests, zero human intervention. The temptation to jump straight to coding (bypassing the workflow) is strong, especially when the feature IS the workflow. **Rule**: when building a new feature, resist the urge to code it manually. Run `dev-planning` → `to-prd` → `to-issues` → let the pipeline build it. The system building its own next feature is the ultimate test of the workflow.

## Verification Checklist

- [ ] File is at `skills/<category>/<name>/SKILL.md` (not in `~/.hermes/skills/`)
- [ ] Frontmatter starts at byte 0 with `---`, closes with `\n---\n`
- [ ] `name`, `description`, `version`, `author`, `license`, `metadata.hermes.{tags, related_skills}` all present
- [ ] Name ≤ 64 chars, lowercase + hyphens
- [ ] Description ≤ 1024 chars and starts with "Use when ..."
- [ ] Total file ≤ 100,000 chars (aim for 8-15k)
- [ ] Structure: `# Title` → `## Overview` → `## When to Use` → body → `## Common Pitfalls` → `## Verification Checklist`
- [ ] Each ordered step has a checkable completion criterion
- [ ] Description is trigger-focused and avoids duplicated body content
- [ ] Bulky or branch-specific reference is progressively disclosed in linked files
- [ ] No-op prose and duplicated rules removed
- [ ] `related_skills` references resolve in-repo (or are explicitly OK to be user-local)
- [ ] `git add skills/<category>/<name>/ && git commit` completed on the intended branch
