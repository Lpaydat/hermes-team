---
name: transform
description: User-invoked, one-shot self-specialization. When the operator runs /transform on a fresh base clone, interview them (via a grilling session), then reconfigure THIS profile — SOUL specialty, skills, description, and command-approval/trust level — into the specialist they need. Self-disarms after one pass.
version: 2.3.0
disable-model-invocation: true
metadata:
  hermes:
    tags: [meta, specialization, bootstrap, self-configuration]
    category: meta
    related_skills: [report-to-base]
---

# transform — become the specialist you're needed as

You are reconfiguring **yourself**. In profile mode your file tools (`write_file`, `patch`, `terminal`) operate on your OWN profile directory (it is your `$HERMES_HOME`). Follow these steps exactly and in order. Your SOUL constitution is FROZEN — obey it and never edit it.

## Step 0 — Guard against re-running
Check whether `.bootstrap_complete` exists in your profile home (`$HERMES_HOME/.bootstrap_complete`). If it exists, STOP and tell the operator you are already specialized (name the specialty). Otherwise continue.

## Step 1 — Snapshot (safety)
Copy `SOUL.md` → `SOUL.md.bak.<timestamp>` and `config.yaml` → `config.yaml.bak.<timestamp>` in your profile home, using `date +%Y%m%d%H%M%S` for the timestamp. Confirm both `.bak` files exist before editing anything.

## Step 2 — Interview the operator (produce the job brief)
Do NOT fire off a flat list of questions. Run a real interview: load the **`grilling`** skill (`skill_view grilling`) and conduct a grilling session aimed squarely at defining THIS agent's specialty. Grill one question at a time, offering your own recommended answer each time, until you and the operator share a crisp understanding of:
- the ONE-SENTENCE role — what this agent is FOR;
- the domains, sources, or systems it works with;
- what a great outcome looks like (success criteria);
- hard constraints, tone, and things it must never do;
- anything you already know it will need (specific tools/skills).

Then summarize back a short **job brief** and get an explicit "yes" before you change anything.

## Step 3 — Compose the skill set (you START with base's curated kit)
You are a clone of `base`, so you already carry base's kit: a handful of **enabled** skills (this `transform` skill, `find-skills`, the `grill*` interview skills, `hermes-agent-skill-authoring`, and a few task skills) plus a **disabled reserve** listed under `skills.disabled` in `config.yaml`. Nothing bundled is ever auto-seeded into you — the environment disables that globally. To specialize, work three levers, and keep it lean (enable/add only what the role needs):

  (a) **Enable from the reserve** — for a skill already present but disabled, REMOVE its name from `skills.disabled` in `config.yaml`.

  (b) **Add a builtin on demand** — for a skill NOT already present, copy it in from the canonical catalog (browse it with `ls ~/.hermes/hermes-agent/skills/*/`):

        cp -r ~/.hermes/hermes-agent/skills/<category>/<skill> "$HERMES_HOME/skills/<category>/"

      Do NOT add it to `skills.disabled` — you copied it in because you want it on.

  (c) **Install third-party / author new** — `hermes skills install <url>` for skills outside the catalog, or author a task skill yourself with `write_file`. When authoring, load TWO references and use them together: **`hermes-agent-skill-authoring`** for the format (frontmatter, validator, directory structure) and **`writing-great-skills`** for the principles (predictability, information hierarchy, leading words, pruning). Format without principles produces well-structured slop; load both.

  (d) **Triage every inherited skill — MANDATORY, not optional.** This is the core of specialization: a clone carrying 50+ skills it will never use is just base with a different name. You MUST account for **every** skill you inherited from base, one of three verdicts each:

      - **ENABLE** — the role needs it. Leave it on (or remove from `skills.disabled` if currently off).
      - **DISABLE** — good skill, may need later, but not for this role. Keep the files on disk, ADD its frontmatter `name:` to `skills.disabled`. Zero context load, reversible.
      - **DELETE** — trash, totally unrelated to the role, or superseded. Remove the directory from `$HERMES_HOME/skills/`. Permanent.

      The decision rule: when in doubt between disable and delete, **disable**. But do not use disable as a shortcut to avoid deleting — if a skill is genuinely unrelated (e.g. a research skill on a coding-focused agent, a creative-writing skill on a DevOps agent), delete it. A profile stuffed with disabled-but-never-used skills is sediment.

      **Read-only skill directories:** Some inherited skill directories (e.g. mattpocock, ponytail) may be **immutable/read-only** — `rm -rf` will fail with "Permission denied." This is expected. Fall back to **DISABLE** for these — add the skill's frontmatter `name:` to `skills.disabled`. The files stay on disk but carry zero context load. Do NOT waste time trying to `chmod` or `sudo rm` — disabling achieves the same outcome (zero context impact).

      **Completion criterion:** every inherited skill has a verdict. Verify by listing `$HERMES_HOME/skills/` and confirming each entry is either (i) not in `skills.disabled` (enabled), (ii) in `skills.disabled` (disabled), or (iii) gone from disk (deleted). If any skill is unaccounted for, you are not done with Step 3.

Use **`find-skills`** to discover candidates in the open skills ecosystem — but as a **discovery tool only**, never an installer. The skill's own Step 6 suggests `npx skills add -g`, which installs to **user-level (global)** scope; ignore that — it would leak the specialization across every profile. Instead:

  - **Search and evaluate** with `find-skills` (Step 1–5: identify the domain, check the skills.sh leaderboard, run `npx skills find`, check install count + source reputation).
  - **Install profile-scoped.** Copy the chosen skill into `$HERMES_HOME/skills/<category>/` by hand (e.g. `cp -r` from its cloned repo, or `git clone` + `cp`), or author an equivalent yourself. The skill must live under `$HERMES_HOME/skills/`, never under a global path.
  - **Quality check against `writing-great-skills`.** Before accepting a third-party skill, verify it clears a low bar: a real `description` (not a stub), correct invocation mode (model-invoked only if the agent must reach it autonomously), and no glaring duplication or sprawl. Do NOT rewrite third-party skills to fully match the principles — they are upstream packages that `npx skills update` would clobber; a fork you can't maintain is worse than a skill with rough edges.

NEVER copy in the whole catalog — that bulk pollution is exactly what this design exists to prevent.

## Step 4 — Configure permissions (the trust dial)
Every clone inherits base's default `approvals.mode: manual` — every flagged command prompts the user. Tuning this to the role now means the operator never has to hand-allow commands one by one later.

The full schema for every lever (`approvals.*`, `command_allowlist`, `security.*`, confirm gates) with preset bundles and precedence rules lives in **`references/permissions.md`** — load it (`skill_view transform` → `file_path='references/permissions.md'`) if a role needs detail beyond the presets below.

  (a) **Ask one interview question.** Present the trust levels with your recommended pick and get confirmation — do NOT pick silently:

      > "How much autonomy should this agent have with shell commands?
      >  1. **manual** — prompt before anything flagged (safest; the inherited default).
      >  2. **smart** — auto-approve low-risk commands via classifier, escalate risky ones. *(recommended for most specialists)*
      >  3. **off** — no prompts at all (sandbox / disposable / fully-trusted ONLY; the hardline blocklist still blocks `rm -rf /` etc.)
      >
      >  My read of this role: **<your recommendation + one-line reasoning>**."

  (b) **Map to a preset, then confirm extras.** Apply the matching preset from `references/permissions.md`. Then ask whether the role needs any of these extras and fold them in before writing:
    - **`command_allowlist`** — commands the role runs constantly that should skip the gate entirely (e.g. `git status`, `git log *`, `pytest*`, `rg *` for a developer; `kubectl *`, `docker *` for DevOps). Every entry here is one less prompt the operator will see.
    - **`approvals.cron_mode: approve`** — only if the role will run scheduled jobs in a trusted environment.
    - **`security.allow_private_urls: true`** — only for DevOps/internal-infra roles hitting private endpoints.

  (c) **Apply via `hermes config set` (canonical path).** Run these with `terminal()`. Scalar keys use the dotted syntax:

      ```
      hermes config set approvals.mode smart
      hermes config set approvals.cron_mode deny
      hermes config set security.allow_private_urls true
      ```

      `command_allowlist` is a **list** — `hermes config set` overwrites rather than appends, so seed it by editing `$HERMES_HOME/config.yaml` directly with `patch`/`write_file`. Add a top-level `command_allowlist:` block. See `references/permissions.md` §Lever 4 for matching rules (globs, no compound commands) and §Preset bundles for ready-made lists per role archetype.

      **Config file write guard:** `write_file` and `patch` will **refuse** to write to `config.yaml` with the error "Refusing to write to Hermes config file." This is a security guard. Work around it: use `hermes config set` for scalar keys (it writes to config.yaml internally), and for list keys (`command_allowlist`, `skills.disabled`), use `terminal()` with `sed` or `cat << 'EOF'` heredoc to edit config.yaml directly. After any edit, parse the file as YAML to verify validity. Note: `hermes config set approvals.mode off` stores `false` (bool) not `"off"` (string) due to YAML coercion — the runtime normalizes it, but for a clean string in the file, edit config.yaml directly with `sed 's/^  mode: false/  mode: "off"/'`.

  (d) **Verify.** Read back `$HERMES_HOME/config.yaml` and confirm the `approvals` block and `command_allowlist` (if set) hold exactly what you wrote, and that the file still parses as valid YAML. The approval system reads config mtime-keyed, so changes take effect on the next command — no restart needed.

  **Completion criterion:** `approvals.mode` is set to the operator's explicit choice (not the inherited `manual` default), any role-specific `command_allowlist` / `cron_mode` / `allow_private_urls` overrides are applied, and `config.yaml` parses. If the operator chose `off`, you have stated the sandbox/trust caveat on the record.

## Step 5 — Persist the changes (validate as you go)
For every file you change: write it, then re-read/parse it to confirm it is valid (YAML parses; the profile still resolves a model). If a write breaks validity, restore from the Step 1 `.bak` and report. Do these:

  (a) **SOUL.md** — leave the `CONSTITUTION` block AND the `## Team coordination` section byte-for-byte unchanged. Replace ONLY the content between `<!-- SPECIALTY:BEGIN -->` and `<!-- SPECIALTY:END -->` with the specialist identity from the job brief (who you are, what you do, how you work, what you must never do). Do NOT touch the markers, the constitution, the team-coordination note, or the "Until you are specialized" section — the `.bootstrap_complete` marker you write in Step 6 makes that section inert on the next session (per the SOUL's own conditional).

  (b) **Reload skills** — after editing `config.yaml`/`skills/`, rescan so your new set takes effect (via `skill_manage`, which clears the skill cache). Confirm the skills you enabled/added now load and the ones you disabled are gone.

  (c) **Marker backstop** — confirm `$HERMES_HOME/.no-bundled-skills` exists; if missing, create it (any short text). Bundled-skill seeding is already off globally via the environment, but this per-profile marker keeps you clean even in an environment where that env var is not set. Never delete it.

  (d) **description** — run `hermes profile describe <your-profile-name> --text "<one or two sentence role for kanban routing>"` (clones start description-less, so this is required; the kanban decomposer routes by description, not name).

## Step 6 — Disarm
Write `$HERMES_HOME/.bootstrap_complete` containing the date and a one-line summary of the specialty. This prevents re-transforming on the next session.

## Step 7 — Hand off
Tell the operator, verbatim intent: "I've reconfigured myself as **<specialty>**. My new identity loads on my NEXT session — please exit and relaunch me (e.g. `hermes -p <name>` or the `<name>` wrapper)." List exactly what you changed (skills enabled / added / disabled, permission mode chosen, specialty summary, description set).

## Never
- Never edit the `CONSTITUTION` block, the `## Team coordination` section, `.env`, approval/secret settings, or your own meta-skills (`transform`, and any future `hermes-self-evolve`). ("Approval/secret settings" here means the **self-modification safety gate** that protects the constitution, `.env`, and the meta-skills — NOT the runtime `approvals.*` command-approval dial in `config.yaml`, which is a normal user-facing config key tuned in Step 4.)
- Never copy in the whole skill catalog — add only what the job needs.
- Never skip Step 3(d) — the skill triage is mandatory. A specialized agent carrying its full inherited kit is unspecialized.
- Never install skills at global/user scope (`npx skills add -g`, or any path outside `$HERMES_HOME/skills/`). Specialization is per-profile; a global install leaks it across every clone.
- Never rewrite a third-party skill to match `writing-great-skills` principles — it's an upstream package that `npx skills update` would clobber. Quality-check, don't fork.
- Never delete the `.no-bundled-skills` marker (it keeps you clean even where the global env switch is absent).
- Never claim the new identity is active in the current session — it takes effect on the NEXT session.
