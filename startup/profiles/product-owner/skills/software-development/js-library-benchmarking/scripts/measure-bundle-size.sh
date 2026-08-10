#!/usr/bin/env bash
#
# Measure tree-shaken bundle size of a JS/TS library at multiple usage levels.
#
# Usage:
#   ./measure-bundle-size.sh <package-name> <entry-file-1> [<entry-file-2> ...]
#
# Prerequisites:
#   npm install <package-name> esbuild
#
# Each entry file should import a different usage level:
#   entry-sql-only.js     → import { sql } from '<pkg>'
#   entry-realistic.js    → import schema + query builder + driver
#   entry-full.js         → import everything
#
# The script bundles each entry with esbuild (--bundle --minify --format=esm),
# measures minified and gzipped size, and prints a comparison table.
#
# External deps (drivers like pg, mysql2) are marked --external automatically.

set -euo pipefail

PKG="${1:?Usage: measure-bundle-size.sh <package-name> <entry1.js> [entry2.js ...]}"
shift
ENTRIES=("$@")

if [ ${#ENTRIES[@]} -eq 0 ]; then
  echo "Error: provide at least one entry file"
  echo "Usage: measure-bundle-size.sh <package-name> <entry1.js> [entry2.js ...]"
  exit 1
fi

# Common driver deps to externalize
EXTERNALS="--external:pg --external:pg-pool --external:mysql2 --external:better-sqlite3 --external:libsql --external:@libsql/client --external:expo-sqlite --external:@neondatabase/serverless --external:@cloudflare/workers-types --external:bun:sqlite"

TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

echo "=== BUNDLE SIZE ANALYSIS: $PKG ==="
echo ""
printf "%-30s %15s %15s %15s\n" "ENTRY FILE" "MINIFIED" "GZIPPED" "TREE-SHAKE %"
printf "%-30s %15s %15s %15s\n" "----------" "--------" "--------" "------------"

BASELINE=0

for i in "${!ENTRIES[@]}"; do
  ENTRY="${ENTRIES[$i]}"
  LABEL=$(basename "$ENTRY" .js)
  OUT="$TMPDIR/bundle-$i.js"

  # Suppress esbuild's own output, capture errors
  if ! npx esbuild "$ENTRY" --bundle --minify --format=esm $EXTERNALS --outfile="$OUT" 2>/dev/null; then
    # Retry without externals that may not apply
    npx esbuild "$ENTRY" --bundle --minify --format=esm --outfile="$OUT" 2>&1 | grep -v "WARN" || true
  fi

  if [ ! -f "$OUT" ]; then
    printf "%-30s %15s\n" "$LABEL" "BUNDLE FAILED"
    continue
  fi

  MINIFIED=$(stat -c%s "$OUT" 2>/dev/null || stat -f%z "$OUT" 2>/dev/null)
  GZIPPED=$(gzip -c "$OUT" | wc -c)

  if [ $i -eq 0 ]; then
    BASELINE=$MINIFIED
    TREE_PCT="100.0%"
  else
    TREE_PCT=$(echo "scale=1; ($MINIFIED * 100) / $BASELINE" | bc 2>/dev/null || echo "n/a")
  fi

  printf "%-30s %12s B %12s B %15s\n" "$LABEL" "$MINIFIED" "$GZIPPED" "$TREE_PCT"
done

echo ""
echo "Notes:"
echo "  - MINIFIED: raw bytes after esbuild --minify --tree-shaking"
echo "  - GZIPPED: gzipped minified output (closer to wire transfer size)"
echo "  - TREE-SHAKE %: size relative to first entry (baseline)"
