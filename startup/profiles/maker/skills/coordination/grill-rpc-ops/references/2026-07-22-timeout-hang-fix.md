# Timeout Hang Fix — Coding Horoscope Grill (2026-07-22)

## Incident

During a real grill session on "GitHub coding horoscope web page", ~20 turns into the Q&A loop, `answer.sh` hung indefinitely. The terminal tool's `process(wait)` kept timing out at 60s but the underlying bash process never exited.

## Root Cause

Line 85 of answer.sh wrapped `hermes --resume` in `$(...)` (command substitution) with `|| true`:

```bash
RAW_OUTPUT=$(hermes -p product-owner --resume "$SESSION_ID" \
    -z "${PREFIX}

${ANSWER}" --cli 2>&1) || true
```

- `$(...)` blocks until the child process exits
- `|| true` only catches non-zero exit codes, not infinite hangs
- The PO model (glm-5.2) either stalled at the provider level or the API dropped the connection without closing it
- Result: infinite block, no output, no exit

## Fix Applied

1. **Timeout wrapper**: wrapped the hermes call in `timeout "$GRILL_TIMEOUT"` (default 600s / 10m, overridable via `HERMES_GRILL_TIMEOUT` env var)
2. **Empty-output guard**: after the hermes call, if RAW_OUTPUT is empty, exit 1 with diagnostic message instead of silently continuing

```bash
GRILL_TIMEOUT="${HERMES_GRILL_TIMEOUT:-600}"
RAW_OUTPUT=$(timeout "$GRILL_TIMEOUT" hermes -p product-owner --resume "$SESSION_ID" \
    -z "${PREFIX}

${ANSWER}" --cli 2>&1) || true

if [[ -z "$RAW_OUTPUT" ]]; then
    echo "ERROR: hermes --resume produced no output — likely timed out after ${GRILL_TIMEOUT}s or API dropped." >&2
    exit 1
fi
```

## Verification

Ad-hoc script tested 9 checks: bash syntax, timeout presence, env var override, 600s default, no stale 300s, empty-output guard, simulated hang (mock hermes that sleeps 999s — timeout fired in 2s, guard detected empty output). All 9 passed.

## Lesson

Never wrap an external model/API call in `$(...)` without a `timeout` wrapper. The `|| true` pattern is insufficient — it catches exit codes but not hangs. This applies to any `hermes --resume` or `hermes --cli` call in a script.

## Timeout calibration (user guidance 2026-07-22)

The 600s (10m) default is calibrated to the FULL response cycle of thinking/reasoning models, not just generation:

- **Thinking phase**: up to 5 minutes alone for complex prompts (chain-of-thought, long context)
- **Tool calling**: additional overhead if the model calls tools before responding
- **Text generation**: the actual response text output

Setting timeout to 120s or less kills the model mid-think. Some models need the full 5 minutes just for the thinking phase before they produce any output. Always set the internal timeout to account for all three phases. The 600s default covers this; bump to 900s for complex prompts.
