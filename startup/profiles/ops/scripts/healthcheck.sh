#!/usr/bin/env bash
# ops healthcheck — watchdog. Silent when healthy; prints findings only when
# something is broken or degraded. Runs as a no_agent cron job (no LLM call).
set -uo pipefail
export PATH="$HOME/.local/bin:$HOME/.hermes-teams/startup/hermes-agent/venv/bin:$PATH"

findings=()

# 1. Required tools on PATH
for tool in bd pi zz codegraph graphify; do
  command -v "$tool" >/dev/null 2>&1 || findings+=("MISSING-TOOL: $tool not on PATH")
done

# 2. Team gateways — any failed?
while read -r svc; do
  [ -n "$svc" ] && findings+=("GATEWAY-FAILED: $svc")
done < <(systemctl --user list-units 'hermes-gateway-*.service' --state=failed --no-legend 2>/dev/null | awk '{print $1}')

# 3. Disk — /tmp and home at/over 95%
while read -r mount pct; do
  findings+=("DISK-FULL: $mount at $pct")
done < <(df -P /tmp "$HOME" 2>/dev/null | awk 'NR>1 && ($5+0) >= 95 {gsub(/%/,"",$5); print $6" "$5"%"}')

# 4. Z.AI auth resolves (the inference backend)
hermes auth status zai >/dev/null 2>&1 || findings+=("ZAI-AUTH-UNRESOLVED: hermes auth status zai failed")

# Watchdog output: silent if healthy
if [ "${#findings[@]}" -eq 0 ]; then
  exit 0
fi

echo "⚠️ ops healthcheck — ${#findings[@]} finding(s) at $(date -u +%FT%TZ):"
for f in "${findings[@]}"; do echo "  - $f"; done
echo "— fix via: dev-env-setup (tools), systemctl --user restart (gateways), rm/clear (disk), refresh-hermes-zai-patch (1305 filter)"
exit 0
