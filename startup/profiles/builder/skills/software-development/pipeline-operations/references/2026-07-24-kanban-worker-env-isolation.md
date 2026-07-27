# Kanban Worker Environment Isolation

**Date:** 2026-07-24
**Problem:** When a kanban worker (builder) launches a subprocess for another profile (PO), the subprocess inherits the worker's `HERMES_KANBAN_*` environment variables. The subprocess then loads the kanban task protocol, thinks it's the task worker, and behaves as the wrong agent.

## How it manifests

The builder's kanban task session has these env vars set by the dispatcher:

```
HERMES_KANBAN_TASK=t_xxx
HERMES_KANBAN_WORKSPACE=/path/to/workspace
HERMES_KANBAN_RUN_ID=xxx
HERMES_KANBAN_CLAIM_LOCK=xxx
HERMES_KANBAN_BOARD=xxx
HERMES_KANBAN_DB=/path/to/kanban.db
HERMES_PROFILE=builder
```

When the builder runs `terminal("hermes -p product-owner --cli ...")`, the PO process inherits ALL of these. PO sees `HERMES_KANBAN_TASK`, calls `kanban_show`, reads the task body, and loads the kanban task protocol into its system prompt. It then behaves as if IT is the assigned worker.

In the E2E test, PO loaded the builder's self-grill skill (symlinked into PO's skills dir) and fabricated the entire grill — writing both PO questions AND builder answers in a single pass without any real RPC loop.

## Fix: env -u before launching subprocess

```bash
env -u HERMES_KANBAN_TASK \
    -u HERMES_KANBAN_WORKSPACE \
    -u HERMES_KANBAN_RUN_ID \
    -u HERMES_KANBAN_CLAIM_LOCK \
    -u HERMES_KANBAN_BOARD \
    -u HERMES_KANBAN_DB \
    -u HERMES_PROFILE \
    timeout 600 hermes -p product-owner --skills grill-rpc --cli
```

The `env -u` command unsets each variable before exec'ing the child process. This prevents PO from inheriting the builder's kanban identity.

## Additional defense: skill isolation

Remove builder-specific skills from PO's skills directory. PO should only have the skills it needs for its role:
- `grill-rpc` (the griller skill)
- NOT `self-grill` (the builder's workflow skill)
- NOT `grill-rpc-ops` (the builder's operational skill)

A symlink from `product-owner/skills/coordination/self-grill` → `shared-skills/self-grill` was found and removed.

## Detection: query PO's session DB for real questions

The definitive check for self-play is to query the PO session database:

```python
import sqlite3
conn = sqlite3.connect("~/.hermes-teams/startup/profiles/product-owner/state.db")
c = conn.cursor()
c.execute("""SELECT COUNT(*) FROM messages 
    WHERE session_id=? AND role='assistant' AND content LIKE '%<Q>%'""", (session_key,))
questions = c.fetchone()[0]
# 0 questions = self-play. 5+ = real grill happened.
```

This check is now embedded in `validate-grill-output.sh` (check 6).
