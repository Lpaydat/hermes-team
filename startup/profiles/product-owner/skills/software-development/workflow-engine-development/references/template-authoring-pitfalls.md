# Template Authoring Pitfalls

Learned from building dev-dispatch, qa-test templates and the stateless engine rewrite.

## 1. Verify output schemas against real profiles

Before writing `output.schema` on a node, read the target profile's SOUL.md + skills to confirm the actual verdict values.

**Failure case:** dev-dispatch route-bug expected `root-caused`/`cannot-reproduce`. Debugger actually outputs `fixed`/`escalated-design`/`blocked-hitl`. Mismatched schemas silently break downstream edges — the edge condition checks a verdict that never appears.

**Fix:** Read SOUL.md for each profile that produces a verdict. The verdict vocabulary is fragmented across the pipeline:
- verifier: `PASS` / `FAIL` / `ESCALATE`
- debugger: `fixed` / `escalated-design` / `blocked-hitl`
- scout: `done`
- architect: `decided` / `needs-more-info`
- ops: `done`

## 2. Trigger context is limited

`${trigger.*}` resolves to: `card_id`, `board`, `assignee`, `title`, plus metadata fields spread flat. Nothing else.

- NO `${trigger.merged_commit_sha}` — git data needs a command node
- NO `${trigger.project_dir}` — resolve from active-projects.json

## 3. Plugins are universal — never assume profile-specific

| Plugin | Used by |
|--------|---------|
| loop_engine | architect, builder, debugger |
| kanban_chains | ALL profiles |
| skill_enforcer | most profiles |

Never claim a plugin is "X-only" without checking each profile's `config.yaml`.

## 4. Research before replacing cron phases

Before migrating a cron phase to a template, read BOTH:
1. The cron script (every condition it checks, in order)
2. The skill the card references (the full protocol)

**Failure case:** The old cron's QA trigger used a two-signal check:
1. `git rev-parse HEAD` changed AND code files in the diff
2. Verifier/debugger card completed in the last hour

A naive template only checked card completion — lost the entire git verification layer.

## 5. Cron-to-template migration pattern

| Cron responsibility | Template equivalent |
|---------------------|-------------------|
| Card-level signals (assignee, status, metadata) | Trigger conditions |
| Environment signals (git HEAD, beads, API state) | Command node scripts |
| Dedup state files | Engine idempotency keys |
| Card body | Task node body_template (keep full, don't compress) |

Steps:
1. Read the original cron script in full
2. Map every condition to trigger or command node
3. Keep the card body detailed — reference all phases of the skill
4. Test side-by-side before disabling the cron phase

## 6. Back-edge annotation uses DFS discovery order

In a 2-node cycle (build↔review), only the cycle-closing edge is marked as back-edge. The forward edge `build→review` is NOT a back-edge.

Original SCC-based annotation marked both edges in a cycle, causing incorrect resets. Fixed by switching to DFS discovery times.

Self-loops: `dst_disc <= src_disc AND from == to` → always a back-edge.

## 7. Command nodes host scripts

A command node's `command` field can call a Python script at `startup/scripts/workflow_engine/scripts/`. The script outputs JSON; the command node parses it via `json.loads(stdout)`.

Pattern for replacing cron polling:
```
check-merge (command) → runs check-merge.py → outputs {should_test, commit_sha}
  ├── should_test == 'true'  → qa-test (task)
  └── should_test != 'true'  → skip (command exit)
```

## 8. Verdict vocabulary is fragmented

There is no unified verdict enum across the pipeline. Each profile defines its own:

| Profile | Verdicts | Where defined |
|---------|---------|---------------|
| verifier | PASS, FAIL, ESCALATE | adversarial-review/SKILL.md |
| debugger | fixed, escalated-design, blocked-hitl | debug-loop/SKILL.md §7 |
| scout | done | (implicit) |
| architect | decided, needs-more-info | architecture-gate/SKILL.md |
| ops | done | (implicit) |
| qa | PASS, FAIL | live-testing/SKILL.md |

Templates must use the correct vocabulary for each profile.
