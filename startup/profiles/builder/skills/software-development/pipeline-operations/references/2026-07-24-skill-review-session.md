# 2026-07-24 Skill Review Session

## Skills reviewed and updated this session

### self-grill (symlinked — patched via `patch` tool, not skill_manage)
- **ADDED: Grill output per-branch persistence section** — root cause fix for missing grill docs. Grill scripts write to `/tmp/grill-<slug>/context/` (ephemeral). Skill now mandates copying per-branch files to `~/projects/<slug>/grill/` before completing the card, with a completion criterion (`ls ~/projects/<slug>/grill/*.md | wc -l` must match branch count in `_state.md`).
- **ADDED: NEVER put project artifacts in ~/vault/** — vault is Obsidian second brain only. Pipeline intake (signals, idea-bank, dossiers, portfolio) stays in vault. Everything else goes to `~/projects/<slug>/`.
- **DISCLOSED: venture brief template** → `references/venture-brief-template.md` (was inline, bloating the skill).
- **REMOVED no-op: "Pitfall: never make the grill optional"** — sediment from one historical mistake. SOUL.md enforces grill requirement.
- **REMOVED no-op: "Known issues"** (skill_manage quirk, config caching) — agent-admin noise, not grill behavior.
- **RESTORED (after over-pruning):** Three pillar definitions, "not a raw idea" leading phrase, NEVER-block rationale (reclaim cycle, fragmenting state).

### grill-rpc-ops (patched via `patch` tool)
- **ADDED: timeout 600 wrapper** on PO launch recipe — `--cli` hangs silently for 300s+ without timeout. User said: "200s is way too low. thinking alone can go up to 300s."

### venture-prototype (new skill, created via skill_manage)
- **POC gate** — check riskiest assumption type (technical vs market). Only build POC for technical risks.
- **Prototype type selection** — HTML/API/CLI/concierge/MCP. Don't default to HTML for everything.
- **Mandatory README template** — 9 sections including "How to Review" with click-by-click steps.
- **NEVER block the card during build**, NEVER skip README, NEVER put prototypes in ~/vault/.
- **Reads grill from `~/projects/<slug>/grill/`** (per-branch files), not a single file.

### pipeline-operations (patched via skill_manage)
- **Updated pitfalls** with 7 new entries from this session: grill output persistence, cross-profile edits, git revert for misunderstandings, sed backreference pitfall, two project-promotion dirs, prototype deliverable consistency.

## Key user corrections encoded

1. **~/vault/ is Obsidian ONLY** — user said "I kept telling you to don't use ~/vault as that's obsidian location." Encoded in self-grill, venture-prototype, pipeline-operations, and SOUL.md. Full cross-profile audit done (builder, tech-lead, developer, advisor, qa).

2. **Grill output per-branch, not single file** — user pointed out original grill used CONTEXT.md which would become gigantic. Agreed to split to per-branch files. But builder sessions ignored this and wrote single files (or nothing). Root cause: skill never told builder to persist.

3. **PO timeout minimum 600s** — user said "thinking alone can go up to 300s." We had 200s.

4. **2-card-per-idea was a misunderstanding** — user meant "split grill PHASE and build PHASE," not "two cards per idea." Reverted the structural change, kept venture-prototype skill.

5. **Matt Pocock's prototype skill doesn't fit** — it's for in-codebase technical prototyping (logic TUIs, UI variant switchers). Our use case is standalone venture demos for founder review. Created venture-prototype instead.

## Overlap noted
- `venture-research` and `venture-dossier-research` overlap significantly with self-grill's `references/web-evidence-gathering.md`. Curator should consolidate.
