# Hermes permission & approval levers — full reference

This is the detailed schema behind the Permission Configuration step of `/transform`.
The step itself stays lean; this file holds every knob, its exact `hermes config set` syntax, and what it actually does at runtime.

## The three layers of Hermes command safety

Hermes gates shell commands through three layers, checked in order:

1. **Hardline blocklist** (`HARDLINE_PATTERNS`) — unconditional. Commands so catastrophic they NEVER run via the agent: `rm -rf /`, `mkfs`, `dd of=/dev/sd*`, fork bombs, `shutdown`, `kill -1`. Not affected by any approval setting, yolo, or cron mode. There is no lever to turn this off — by design.
2. **Dangerous-pattern detection** (`DANGEROUS_PATTERNS`) — flags commands that *might* be destructive (recursive delete, writes to `.env`/`config.yaml`/`/etc`, curl-piped-to-shell, etc.). What happens next depends on the approval mode below.
3. **Approval gate** — the layer you configure. Decides whether a flagged command is (a) auto-approved by a smart classifier, (b) prompted to the user, or (c) silently allowed.

The **permanent allowlist** (`command_allowlist`) sits beside layer 2: a command that matches a stored glob skips the approval gate entirely.

---

## Lever 1 — `approvals.mode` (the main trust dial)

**What it controls:** how Hermes reacts when a command is flagged as potentially dangerous.

```yaml
approvals:
  mode: manual   # manual | smart | off
```

| Mode | Behavior | Use when |
|------|----------|----------|
| `manual` (default) | Every flagged command prompts the user. CLI shows an interactive dialog; messaging queues a pending approval. | The agent runs interactively and the user is present to approve. Lowest risk, highest friction. |
| `smart` | An auxiliary LLM assesses each flagged command. Low-risk ones are auto-approved (session-persistent). Genuinely risky ones still escalate to the user. | The user wants autonomy on safe ops but a backstop on destructive ones. Best default for most specialists. |
| `off` | No approval prompts at all. Every flagged command runs. Equivalent to `--yolo`. | Fully trusted, sandboxed, or disposable environments ONLY. The hardline blocklist still applies. |

**Set it:**
```bash
hermes config set approvals.mode smart
```

**Note on YAML parsing:** YAML 1.1 treats a bare `off` as boolean `false`. Hermes normalizes this (`_normalize_approval_mode`), so writing `mode: off` or `mode: "off"` both work — but quote it (`"off"`) if you want to be explicit in the file.

**Note on `hermes config set` and boolean coercion:** the CLI setter coerces the strings `on`/`off`/`yes`/`no` to booleans and bare digits to int before writing. So `hermes config set approvals.mode off` stores `mode: false` in YAML (a bool, not the string `"off"`). It still works at runtime — `_normalize_approval_mode` maps `False` → `"off"` — but the stored value isn't what you typed. For a clean string `"off"` in the file, set it by editing `config.yaml` directly. The `smart` and `manual` values are unaffected (they stay strings).

---

## Lever 2 — `approvals.cron_mode` (cron-job trust dial)

**What it controls:** what happens when a *cron job* hits a flagged command. Cron jobs run headless with no user to prompt, so `manual` mode would block forever. This is a separate dial.

```yaml
approvals:
  cron_mode: deny   # deny | approve
```

| Mode | Behavior |
|------|----------|
| `deny` (default) | Flagged commands are blocked; the agent must find another way. Safe. |
| `approve` | All flagged commands auto-approve in cron jobs. Only for trusted cron jobs in disposable environments. |

**Set it:**
```bash
hermes config set approvals.cron_mode approve
```

---

## Lever 3 — `approvals.timeout`

**What it controls:** how long (seconds) an interactive approval prompt waits before timing out. After timeout, the command is denied.

```yaml
approvals:
  timeout: 60   # seconds (default)
```

**Set it:**
```bash
hermes config set approvals.timeout 120
```

---

## Lever 4 — `command_allowlist` (permanent per-command approval)

**What it controls:** a list of command patterns that are **permanently pre-approved** — they skip the approval gate entirely, regardless of `approvals.mode`. Each entry is a command string or shell glob (supports `*`, `?`, `[...]`).

```yaml
command_allowlist:
  - "git status"
  - "git log *"
  - "npm test*"
  - "podman *"
  - "rg *"
```

This is what gets written when a user clicks "Always Approve" on a prompt. You can also seed it during transform for commands the role will run constantly.

**Matching rules:**
- Exact match: `"git status"` matches only `git status`.
- Glob: `"git log *"` matches `git log --oneline -5`, `git log origin/main`, etc.
- Commands with shell operators (`&&`, `||`, `|`, `;`, backticks, `$(...)`) are **never** matched — the allowlist only covers single commands. This is a safety feature: compound commands are always re-checked.

**Set individual entries:**
The `hermes config set` CLI doesn't append to lists cleanly — it overwrites. For the allowlist, edit `config.yaml` directly with `write_file`/`patch`, or use the tool's own `skill_manage`-style approach. During transform, the cleanest path is:

```python
# Read current config.yaml, append entries, write back
import yaml, pathlib
p = pathlib.Path("$HERMES_HOME/config.yaml")
cfg = yaml.safe_load(p.read_text()) or {}
allow = cfg.setdefault("command_allowlist", [])
for entry in ["git status", "git log *", "npm test*"]:
    if entry not in allow:
        allow.append(entry)
p.write_text(yaml.dump(cfg, default_flow_style=False, sort_keys=False))
```

Or, since transform runs in profile mode where `config.yaml` is directly editable, use `patch` to add the `command_allowlist:` block if it doesn't exist.

---

## Lever 5 — confirm gates (slash commands & MCP reload)

Two boolean switches that gate specific high-friction, low-danger actions:

```yaml
approvals:
  mcp_reload_confirm: true         # confirm before /reload-mcp (cache-busting)
  destructive_slash_confirm: true  # confirm before /clear /new /reset /undo
```

| Key | Default | What it gates |
|-----|---------|---------------|
| `mcp_reload_confirm` | `true` | `/reload-mcp` — rebuilding MCP tools invalidates the prompt cache (expensive). Users click "Always Approve" to silence permanently, which flips this to `false`. |
| `destructive_slash_confirm` | `true` | `/clear`, `/new`, `/reset`, `/undo` — discard conversation state. Three-option prompt. |

Most specialists leave these `true`. Set to `false` only if the role never uses MCP or never needs session-history protection.

**Set them:**
```bash
hermes config set approvals.mcp_reload_confirm false
hermes config set approvals.destructive_slash_confirm false
```

---

## Lever 6 — `security` block (scanning & secret redaction)

Not approval per se, but related to what the agent is allowed to do:

```yaml
security:
  redact_secrets: true          # mask API-key-like strings in output (default on)
  tirith_enabled: true          # pre-exec scan via tirith binary (if installed)
  tirith_path: "tirith"
  tirith_timeout: 5
  tirith_fail_open: true        # allow command if tirith unavailable
  allow_private_urls: false     # allow requests to private/internal IPs
```

These are almost always left at defaults. `allow_private_urls: true` is the one a specialist might need — e.g. a DevOps agent working with OpenWrt routers, internal proxies, or VPN-protected services.

**Set it:**
```bash
hermes config set security.allow_private_urls true
```

---

## Preset bundles

Common role archetypes map to these settings. Use as a starting point, then adjust:

### Read-only analyst / researcher
Low risk: reads files, runs searches, maybe `git log`. Rarely destructive.
```yaml
approvals:
  mode: manual
  cron_mode: deny
command_allowlist: []
```

### Developer (the common case)
Writes code, runs tests, git operations. Wants autonomy on safe ops.
```yaml
approvals:
  mode: smart
  cron_mode: deny
command_allowlist:
  - "git status"
  - "git log *"
  - "git diff *"
  - "git show *"
  - "npm test*"
  - "npm run lint*"
  - "pytest*"
  - "ruff *"
  - "rg *"
```

### DevOps / SRE
Manages services, infra, internal endpoints. Needs private-URL access and broad command trust.
```yaml
approvals:
  mode: smart
  cron_mode: approve
command_allowlist:
  - "systemctl status *"
  - "kubectl *"
  - "docker *"
  - "podman *"
  - "terraform *"
  - "helm *"
security:
  allow_private_urls: true
```

### Sandbox / disposable / fully-trusted
The agent is in a container, VM, or throwaway environment and the user trusts it completely.
```yaml
approvals:
  mode: "off"
  cron_mode: approve
  destructive_slash_confirm: false
  mcp_reload_confirm: false
```
(The hardline blocklist still blocks `rm -rf /`, `mkfs`, etc. — nothing turns that off.)

---

## How these interact (precedence)

For any given command, Hermes checks in this order:

1. **Hardline blocklist** → BLOCKED unconditionally. Done.
2. **`command_allowlist`** (permanent allow) → matches? APPROVED, no prompt.
3. **`approvals.mode`**:
   - `off` → APPROVED (no check).
   - `smart` → run classifier; low-risk APPROVED, high-risk → prompt.
   - `manual` → always prompt.
4. If a prompt fires and times out (`approvals.timeout`) → DENIED.
5. For cron jobs specifically, step 3 is replaced by `approvals.cron_mode`.

The `--yolo` CLI flag and `/yolo` session toggle are equivalent to `approvals.mode: off` for the duration they're active, but they're process/session-scoped — they don't write to config. Configuring `approvals.mode` in `config.yaml` is the persistent equivalent.

---

## Verifying after transform

After applying permission settings, verify they landed:

```bash
hermes config show | grep -A5 approvals    # see the approvals block
grep command_allowlist "$HERMES_HOME/config.yaml"  # see the allowlist
```

Or read `config.yaml` directly — it's the source of truth. The approval system reads config mtime-keyed, so changes take effect on the next command without a restart.
