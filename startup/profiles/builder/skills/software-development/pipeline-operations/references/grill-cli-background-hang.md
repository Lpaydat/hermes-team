# Grill PO Launch: --cli Background Hang

**Discovered:** 2026-07-23 E2E pipeline test (LeadPilot prototype build)
**Affects:** grill-rpc-ops skill, any builder session launching PO for self-grill

## Symptom

Launching PO via `hermes -p product-owner --skills grill-rpc -z "..." --cli` in **background mode** (`terminal(background=true)`) produces zero output. The process starts, consumes CPU, but never writes to stdout. `process(action='poll')` returns `timeout` after every 60s wait.

## Root Cause

The `--cli` flag launches an interactive CLI session that expects stdin. In background mode, stdin is never provided (no human to type), so the process hangs waiting for input that never arrives.

## Fix: Foreground + Timeout Wrapper

Replace the bare `hermes ... --cli` call with a foreground `timeout` wrapper:

```bash
timeout 300 hermes -p product-owner \
  --skills grill-rpc \
  -z "Grill the builder on: <idea>..." \
  --cli 2>&1 | tail -80
```

This blocks the builder session for up to 300s (glm-5.2 takes 60-200s for the first response), but produces actual output.

## Pattern for Subsequent RPC Calls

After the initial launch, use `hermes --resume <SESSION_ID> -z "answer" --cli` wrapped in `timeout`:

```bash
timeout 400 hermes -p product-owner \
  --resume "$SESSION_ID" \
  -z "[GRILL STATE...] answer text" \
  --cli 2>&1 | tail -80
```

## What NOT to Do

- Do NOT use `terminal(background=true)` for the initial PO launch with `--cli`
- Do NOT use `process(action='wait', timeout=60)` expecting output — it will timeout repeatedly
- Do NOT kill the PO process and retry with the same approach — the same hang will recur

## grill-rpc-ops Skill Status

The grill-rpc-ops skill is **pinned** and could not be patched in this session (background curator refuses pinned skills). The SKILL.md PO Launch Recipe still shows the bare `hermes ... --cli` without `timeout`. When the skill is unpinned, add the `timeout 300` wrapper to the recipe and add this hang as a pitfall.
