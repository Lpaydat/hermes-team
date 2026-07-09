# Platform Constraints for QA Swarm

Known limitations of `hermes kanban swarm` that affect QA workflow. Work around at the profile level — never edit platform source.

## 1. Worker skill name parsing

The CLI parses `--worker PROFILE:TITLE[:SKILL,SKILL]` by splitting on `:` with `maxsplit=2`. Literal brackets (`[`, `]`) in the skill position get captured in the skill name.

**Wrong:** `--worker qa:"Title"[:qa-functional]` → skill becomes `qa-functional]` → crash
**Right:** `--worker "qa:Title:qa-functional"` → skill becomes `qa-functional` → works

## 2. Hardcoded verifier and synthesizer skills

`kanban_swarm.py` creates:
- Verifier card with `skills=["requesting-code-review"]` (line ~192)
- Synthesizer card with `skills=["humanizer"]` (line ~211)

These are hardcoded for the original use case (code review → humanize output). If they don't exist on your profile, both crash on startup.

**Workaround:** Install thin stub skills on the QA profile:
- `skills/software-development/requesting-code-review/SKILL.md` — redirects to QA verifier role
- `skills/humanizer/SKILL.md` — redirects to QA synthesizer role

Both stubs are installed on this profile. Do NOT replace them with the real upstream versions — the real `humanizer` is a 30KB creative writing skill that would confuse the synthesizer.

## 3. Worker card bodies are generic

The swarm CLI creates worker cards with only the title + swarm protocol boilerplate. No claims, no container details, no ports. The orchestrator must post a blackboard comment on the root card after creating the swarm with all the context workers need.

## 4. max_in_progress_per_profile is global

The dispatcher reads `max_in_progress_per_profile` from the ROOT `~/.hermes/config.yaml` at gateway boot. Per-profile config blocks are NOT read by the dispatcher. The setting is one global value applied to every profile.

To get parallel QA workers: set `max_in_progress_per_profile: 5` in root config AND restart the gateway holding the dispatcher lock (check `fuser .dispatcher.lock` for which PID holds it).

## 5. Dispatcher lock

Only one gateway holds the dispatcher lock. Check with `fuser /home/lpaydat/.hermes-teams/startup/kanban/.dispatcher.lock`. That gateway is the one that spawns workers. Other gateways run but don't dispatch.

If the dispatcher gateway crashes, another gateway acquires the lock on its next tick (every 60s).

## 6. Swarm verifier checks for blackboard

The verifier card body says "Review every worker handoff and blackboard update. Gate the swarm: complete only with metadata {gate: pass} when evidence is sufficient." The verifier reads the root card's blackboard comments to check all workers posted results. If a worker crashed without posting, the verifier should block.
