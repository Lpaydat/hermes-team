#!/usr/bin/env bash
# Batch HTTP-status probe for candidate URLs.
# Screens many URLs at once before committing to a full content fetch —
# use when a doc site may have restructured (multiple likely-dead URLs)
# or when you have a list of candidate mirrors to triage.
#
# Usage:
#   probe-urls.sh "https://url1" "https://url2" ...
#   printf '%s\n' "${URLS[@]}" | probe-urls.sh    # stdin, one URL per line
#
# Output: "<http_code>  <url>" for each, sorted by status.
# Exit 0 always — the point is the output, not pass/fail.
#
# Status codes to act on:
#   200 → fetch content (curl+grep per tactics.md §8, or browser_navigate for JS pages)
#   404 → dead — try path-segment shift (§4) or Wayback Machine
#   403 → paywalled/bot-blocked — try official mirror (§3) or browser tools
#   000 → DNS failure / timeout — domain may be gone; check Wayback

set -euo pipefail
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

# Read URLs from args or stdin
urls=()
if [[ $# -gt 0 ]]; then
  urls=("$@")
else
  while IFS= read -r line; do
    [[ -n "$line" ]] && urls+=("$line")
  done
fi

if [[ ${#urls[@]} -eq 0 ]]; then
  echo "Usage: $0 <url> [<url> ...]" >&2
  exit 1
fi

for url in "${urls[@]}"; do
  code=$(curl -sL --max-time 12 -o /dev/null -w "%{http_code}" -A "$UA" "$url" 2>/dev/null || echo "000")
  echo "${code}  ${url}"
done
