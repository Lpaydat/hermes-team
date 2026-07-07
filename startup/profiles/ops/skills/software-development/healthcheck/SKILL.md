---
name: healthcheck
description: "Verify the agent dev environment is healthy: tools on PATH, profiles/gateways up, disk not full. Use when the user says 'healthcheck', 'check env', 'is everything ok', or runs on a cron. Silent when healthy; reports only what's broken."
metadata:
  hermes:
    tags: [health, ops, monitor, watchdog, environment]
    category: software-development
---

# healthcheck — dev-environment watchdog

Run periodic (cron) or on-demand checks of the agent team's environment. **Watchdog pattern: if everything is healthy, produce NO output.** Speak up only when something is broken or degraded, so a cron run is silent on a good day.

## Checks

Run each; collect failures. A check "fails" only if it would break agent work.

```bash
# 1. Required tools on PATH
for tool in bd pi zz codegraph graphify; do
  command -v "$tool" >/dev/null 2>&1 || echo "MISSING-TOOL: $tool"
done

# 2. Hermes profiles exist + team gateways are running
hermes profile list >/dev/null 2>&1 || echo "HERMES-CLI-DOWN"
systemctl --user list-units 'hermes-gateway-*.service' --state=failed --no-legend 2>/dev/null | awk '{print "GATEWAY-FAILED: "$1}'

# 3. Disk — /tmp and home not full (>95% = degraded, 100% = broken)
df -P /tmp ~ 2>/dev/null | awk 'NR>1 && $5+0 >= 95 {print "DISK-FULL: "$6" at "$5}'

# 4. Z.AI reachability (the agent's inference backend) — a 1305 here means the
#    "Hermes Agent" prompt-phrase filter is firing again; see refresh-hermes-zai-patch.
hermes auth status zai >/dev/null 2>&1 || echo "ZAI-AUTH-UNRESOLVED"
```

## Output rules

- **All checks pass → produce NO output** (silent watchdog). Do not print "all good".
- **Any failure → one consolidated markdown report**: each failing check on its own line with `CHECK: detail`, plus the single most-likely fix per check. Keep it to facts the user can act on.
- Save the report to `<HERMES_HOME>/reports/healthcheck-<date>.md` only if there are findings.

## Guardrails

- Never auto-"fix" anything — this skill reports, it does not repair. Point to the fixing skill/command instead (e.g. `dev-env-setup` for missing tools, `refresh-hermes-zai-patch` for the 1305 filter).
- A tool that's intentionally absent is not a failure — if the user retired a profile/tool, its absence is expected.
- Time-box: if a check hangs (>10s), treat it as a failure (`CHECK-HUNG`) and move on.

### Disk-full reporting: inspect before labeling, never suggest bulk deletion on inference

When `/tmp` or home is full, the instinct is to scan `du -sh /tmp/*` and call the biggest directories "disposable" or "abandoned." **Don't.** Cryptic dir names hide active work:

- `tdl-*` dirs may be **video downloads** (the `tdl` tool), not analysis artifacts.
- `parts-*` dirs may be **in-progress HLS stream captures** with `.ts` segments still being written.
- A dir with no running process is **not** necessarily finished — it may be a paused download or a job between batches.

**Rule**: when reporting disk pressure, list sizes + **what's actually inside** (`ls`, `file`, file extensions), and let the user decide what to delete. Never recommend deletion of paths you haven't inspected. If you must group them, label by observed content ("12G of `.mkv` video files"), not by guessed provenance ("abandoned analysis run").

**Don't hedge about downstream impact you haven't verified.** If you don't know whether a tool uses `/tmp`, whether a process depends on a directory, or whether an operation will fail on disk pressure — say "I haven't verified that" or run the check, rather than inventing a plausible-sounding caution. Speculative caveats waste the user's attention and erode trust in the facts you do have. One `ls` beats three sentences of "this might break."
