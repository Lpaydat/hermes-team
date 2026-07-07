# Harness Commands — Verified for pi v0.80.3

## Pi (the primary harness for this team)

### Print mode (non-interactive — preferred for loops)

```bash
timeout --signal=TERM --kill-after=30 <wall_secs> \
  pi --provider <provider> --model <model> \
    -p "<prompt>" \
    --tools read,write,edit,bash,grep,find,ls \
    --mode json
```

### Key facts (verified 2026-07-05)
- **NO `--max-turns` flag** — pi rejects it as unknown option. The `timeout` wrapper IS the only cap.
- **NO `--auto-test` flag** — also rejected.
- **NO `--allowedTools` flag** — that's Claude Code syntax. Pi uses `--tools` (comma-separated, no spaces).
- JSON output (`--mode json`) provides per-turn tool calls and final result.

### Warm resume (after review rejection)

```bash
timeout --signal=TERM --kill-after=30 <wall_secs> \
  pi --provider <provider> --model <model> \
    --session <session_id> \
    -p "<findings>" \
    --tools read,write,edit,bash,grep,find,ls \
    --mode json
```

- Sessions stored at `~/.pi/agent/sessions/<cwd-encoded>/`
- Resume is **cwd-scoped** — must run from the SAME directory as the original invocation
- Do NOT use `--session-dir` — let pi discover sessions by cwd automatically
- Session ID visible in the first JSONL line of output (`responseId` field)

### Built-in tool names
```
read   — Read file contents
bash   — Execute bash commands
edit   — Edit files with find/replace
write  — Write files (creates/overwrites)
grep   — Search file contents (read-only, off by default)
find   — Find files by glob pattern (read-only, off by default)
ls     — List directory contents (read-only, off by default)
```

## Zlaude / zz (Claude Code routed to Z.AI)

`zz` is a fish alias for `zlaude --permission-mode bypassPermissions`.
Zlaude wraps Claude Code v2.x with Z.AI's Anthropic-compatible endpoint.

```bash
timeout --signal=TERM --kill-after=30 <wall_secs> \
  zlaude -p "<prompt>" \
    --allowedTools "Read,Edit,Bash" \
    --max-turns <N> \
    --output-format json
```

- `--max-turns` works in Claude Code (but verify on every upgrade)
- `--allowedTools` (not `--tools` like pi)
- Config: `~/.claude-zai/settings.json` — model routing: haiku=glm-4.7, sonnet/opus=glm-5.2
- Sessions: `~/.claude-zai/projects/<cwd-encoded>/`
- Warm resume: `zlaude -p -r <session_id> "<findings>"`
