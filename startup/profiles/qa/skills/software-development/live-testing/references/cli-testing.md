# CLI Tool Testing

## Build & install

See build system detection in SKILL.md. Install so the binary is on `$PATH` or find the built binary:

| Signal | Binary location |
|--------|----------------|
| `package.json` with `bin` | `npm install && npm link` (or `npm install -g .`) |
| `Cargo.toml` | `cargo build --release` → `target/release/<name>` |
| `pyproject.toml` with `[project.scripts]` | `pip install -e .` then use the entry point |
| Shell script | `chmod +x script.sh` |

## Confirm it's alive

```bash
<binary> --help
<binary> --version
<binary> -h
<binary> version
```

## Test patterns

### Exit codes
```bash
<binary> valid-command; echo "exit: $?"      # expect 0
<binary> --invalid-flag; echo "exit: $?"     # expect non-zero
<binary>; echo "exit: $?"                    # no args — depends on spec
```

### stdout vs stderr
```bash
<binary> valid-command 2>/dev/null           # stdout only — should show results
<binary> valid-command 1>/dev/null           # stderr only — should be empty on success
<binary> --bad-flag 1>/dev/null              # stderr only — should show error
```

### Structured output
```bash
<binary> --json | python3 -m json.tool       # JSON validity check
<binary> --json | jq .                       # jq parse
```

### Subcommands
```bash
<binary> <subcommand> --help
<binary> <subcommand> --invalid-flag
```

## CLI-specific edge cases

Cases beyond the universal categories in SKILL.md:

| Category | Tests |
|----------|-------|
| Missing/extra args | Run with no arguments; run with surplus positional arguments |
| Unknown flags | `--nonexistent`, `-Z`, `-` (single dash) |
| Flag values | `--flag=` (empty), `--flag=` with spaces, `--flag=` with special chars |
| stdin | Pipe empty input, pipe large input, pipe binary input, pipe with no newline |
| File arguments | Nonexistent file, directory as file, `/dev/null`, binary file, symlink, pipe as file arg |
| Environment vars | Required var missing, set to empty, set to garbage |
| Permissions | Run without read/write permission on target files |
| Paths | Relative, absolute, with spaces, unicode, very long (>4096 chars on Linux) |

## Evidence

- Full command with all flags
- Complete stdout and stderr
- Exit code
- Files created/modified (`ls -la` before/after)
