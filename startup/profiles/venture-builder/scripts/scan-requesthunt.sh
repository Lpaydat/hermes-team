#!/usr/bin/env bash
# RequestHunt weekly deep scan — multi-platform demand signal collection
# Runs as a no-agent cron job with a guard script.
# Saves raw signals to ~/vault/ventures/signals/
# Upgrade path: when you move to requesthunt Pro, increase TOPICS or frequency.
set -euo pipefail

VAULT="$HOME/vault/ventures"
SIGNALS_DIR="$VAULT/signals"
mkdir -p "$SIGNALS_DIR"

TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUTFILE="$SIGNALS_DIR/requesthunt_${TIMESTAMP}.json"

# ─── Guard: check if already scanned this week ──────────────────────
WEEK=$(date +%Y-W%V)
MARKER="$VAULT/.last-requesthunt"
if [ -f "$MARKER" ] && [ "$(cat "$MARKER")" = "$WEEK" ]; then
  echo "Already scanned for $WEEK. Skipping."
  exit 0
fi

# ─── Check if requesthunt is configured ─────────────────────────────
if ! command -v requesthunt &>/dev/null; then
  echo "requesthunt CLI not installed. Skipping weekly deep scan."
  echo "To enable: curl -fsSL https://requesthunt.com/cli | sh"
  exit 0
fi

if ! requesthunt config show 2>/dev/null | grep -q 'resolved_api_key: [^n][^u][^l][^l]'; then
  echo "requesthunt not configured (no API key). Skipping weekly deep scan."
  echo "To enable: requesthunt auth login  OR  requesthunt config set-key \$KEY"
  echo "Signal buffer will rely on daily agent-driven scans only."
  exit 0
fi

# ─── Topic areas to scan ────────────────────────────────────────────
# Adjust these to match venture focus areas as they evolve.
# Cost: depth × platforms = credits per topic.
# Free tier budget: ~25 credits/week → 5 topics at depth=1 × 5 platforms
# Pro tier: 5000 credits/month → can scan daily with more topics/depth
TOPICS=(
  "ai-developer-tools|developer tools AI automation|reddit,github,youtube|1"
  "saas-pain-points|SaaS subscription management billing|reddit,x,github|1"
  "productivity-friction|productivity workflow automation friction|reddit,youtube|1"
  "creator-economy-tools|content creator monetization tools|reddit,x,youtube|1"
  "small-business-ops|small business operations invoicing CRM|reddit,linkedin|1"
)

echo "=== RequestHunt Weekly Deep Scan ==="
echo "Week: $WEEK"
echo "Timestamp: $TIMESTAMP"
echo "Topics: ${#TOPICS[@]}"
echo ""

TOTAL_CREDITS=0

echo "[" > "$OUTFILE"

for i in "${!TOPICS[@]}"; do
  IFS='|' read -r label query platforms depth <<< "${TOPICS[$i]}"

  IFS=',' read -ra PLAT_ARR <<< "$platforms"
  NUM_PLATFORMS=${#PLAT_ARR[@]}
  CREDITS=$((depth * NUM_PLATFORMS))
  TOTAL_CREDITS=$((TOTAL_CREDITS + CREDITS))

  echo "[$((i+1))/${#TOPICS[@]}] $label — platforms: $platforms, depth: $depth, cost: ${CREDITS} credits"

  RESULT=$(requesthunt scrape "$query" --platforms "$platforms" --depth "$depth" --toon 2>/dev/null || echo "{\"error\": \"scrape failed\", \"query\": \"$query\"}")

  if [ "$i" -lt $((${#TOPICS[@]} - 1)) ]; then
    echo "{\"topic\": \"$label\", \"query\": \"$query\", \"timestamp\": \"$TIMESTAMP\", \"result\": $RESULT}," >> "$OUTFILE"
  else
    echo "{\"topic\": \"$label\", \"query\": \"$query\", \"timestamp\": \"$TIMESTAMP\", \"result\": $RESULT}" >> "$OUTFILE"
  fi
done

echo "]" >> "$OUTFILE"

# ─── Update guard marker ────────────────────────────────────────────
echo "$WEEK" > "$MARKER"

echo ""
echo "=== Scan Complete ==="
echo "Credits used: ~${TOTAL_CREDITS}"
echo "Output: $OUTFILE"
echo "Marker updated: $MARKER → $WEEK"
