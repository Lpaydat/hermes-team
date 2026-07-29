#!/usr/bin/env bash
# queue-builds.sh — reads idea-bank.md, picks top 10 unbuilt ideas by score,
# creates kanban cards assigned to 'builder' for prototype builds.
#
# No AI needed — scores already exist. This is pure sorting + kanban creation.
# Runs as a no_agent cron job (shell only, zero tokens).
#
# Door D (User) ideas always included first, regardless of score.
#
# USAGE:
#   bash queue-builds.sh                                  # default: top 10 from bank
#   bash queue-builds.sh --board e2e-livetest-4           # use a specific board
#   bash queue-builds.sh --slugs slug1,slug2,slug3        # target specific ideas
#   bash queue-builds.sh --board e2e-livetest-4 --slugs slug1,slug2  # both
#   bash queue-builds.sh --force                           # bypass cooldown guard

set -euo pipefail
trap 'exit 0' PIPE  # hermes kanban list --json | python3 can SIGPIPE on large boards

BOARD="hermes-hq"
MAX_BUILDS=10
SLUGS=""
FORCE=false
MARKER="$HOME/vault/ventures/.last-queue"

# ── Parse args ──
while [[ $# -gt 0 ]]; do
    case "$1" in
        --board)  BOARD="$2"; shift 2 ;;
        --slugs)  SLUGS="$2"; shift 2 ;;
        --force)  FORCE=true; shift ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

TODAY=$(date +%Y-%m-%d)

# ── Guard: only run once per 6h window (skip if --force or --slugs) ──
if [ "$FORCE" = false ] && [ -z "$SLUGS" ]; then
    if [ -f "$MARKER" ]; then
        LAST=$(cat "$MARKER")
        NOW_EPOCH=$(date +%s)
        LAST_EPOCH=$(date -d "$LAST" +%s 2>/dev/null || echo 0)
        ELAPSED=$((NOW_EPOCH - LAST_EPOCH))
        if [ "$ELAPSED" -lt 21600 ]; then
            echo "Already queued within last 6h (last: $LAST). Skipping."
            exit 0
        fi
    fi
fi

IDEA_BANK="$HOME/vault/ventures/idea-bank.md"

if [ ! -f "$IDEA_BANK" ]; then
    echo "idea-bank.md not found at $IDEA_BANK. Skipping."
    exit 0
fi

# ── Build the idea list ──
# Normalize idea-bank rows: strip leading pipes so ||| and |||  prefixes don't break field splitting.
# All table rows end up as: | # | score | origin | name | dossier | status |
NORMALIZED_BANK=$(sed 's/^|*\([0-9]\)/| \1/' "$IDEA_BANK")

if [ -n "$SLUGS" ]; then
    # Targeted mode: specific slugs passed as comma-separated arg
    IDEAS_FILE="/tmp/queue_builds_ideas.tmp"
    > "$IDEAS_FILE"  # truncate
    IFS=',' read -ra SLUG_ARRAY <<< "$SLUGS"
    for target_slug in "${SLUG_ARRAY[@]}"; do
        target_slug=$(echo "$target_slug" | xargs) # trim whitespace
        # Look up score + name from idea bank
        ROW=$(awk -v target="$target_slug" '
            BEGIN { FS="|" }
            /^\| [0-9]+/ {
                dossier = $6
                if (match(dossier, /\[dossier\]\(ideas\/([^)]+)\.md\)/, slug_match)) {
                    slug = slug_match[1]
                    if (slug == target) {
                        score = $3; name = $5; status = $7
                        gsub(/^[ \t]+|[ \t]+$/, "", score)
                        gsub(/^[ \t]+|[ \t]+$/, "", name)
                        gsub(/^[ \t]+|[ \t]+$/, "", status)
                        split(score, parts, "/")
                        printf "%d\t%s\t%s\t%s\n", parts[1], slug, name, status
                        exit
                    }
                }
            }
        ' <<< "$NORMALIZED_BANK")
        if [ -n "$ROW" ]; then
            printf '%s\n' "$ROW" >> /tmp/queue_builds_ideas.tmp
        else
            # Slug not found in bank (common: bank slug differs from file-on-disk slug).
            # Fall back to reading the dossier file directly for the name.
            DOSSIER="$HOME/vault/ventures/ideas/${target_slug}.md"
            if [ -f "$DOSSIER" ]; then
                # Try H1 first, then first non-empty non-frontmatter line
                NAME=$(grep -m1 '^# ' "$DOSSIER" | sed 's/^# *//; s/ —.*$//; s/ |.*$//; s/ - .*Dossier.*$//')
                if [ -z "$NAME" ] || [ "$NAME" = "Idea Dossier" ]; then
                    NAME=$(sed -n '2,10p' "$DOSSIER" | grep -m1 'Working name\|working name\|working_name\|\*\*Slug' | sed 's/.*[Nn]ame[:*]* *//; s/ \*\*.*$//; s/"//g' | tr -d '"' || true)
                fi
                [ -z "$NAME" ] || [ "$NAME" = "Idea Dossier" ] && NAME="$target_slug"
                echo "WARN: '$target_slug' not in bank — using name: $NAME"
                printf '0\t%s\t%s\tunbuilt\n' "$target_slug" "$NAME" >> /tmp/queue_builds_ideas.tmp
            else
                echo "WARN: '$target_slug' not in bank and no dossier file found"
                printf '0\t%s\t%s\tunbuilt\n' "$target_slug" "$target_slug" >> /tmp/queue_builds_ideas.tmp
            fi
        fi
    done
    IDEAS=$(cat "$IDEAS_FILE")
    rm -f "$IDEAS_FILE"
else
    # Default mode: parse idea-bank.md for all buildable ideas, sort by score
    IDEAS=$(awk '
    BEGIN { FS="|" }
    /^\| [0-9]+/ {
        num = $2
        score = $3
        origin = $4
        name = $5
        dossier = $6
        status = $7

        gsub(/^[ \t]+|[ \t]+$/, "", score)
        gsub(/^[ \t]+|[ \t]+$/, "", name)
        gsub(/^[ \t]+|[ \t]+$/, "", status)
        gsub(/^[ \t]+|[ \t]+$/, "", dossier)

        if (score ~ /^[0-9]+\/25$/) {
            split(score, parts, "/")
            numeric_score = parts[1]

            if (match(dossier, /\[dossier\]\(ideas\/([^)]+)\.md\)/, slug_match)) {
                slug = slug_match[1]
            } else {
                slug = name
                gsub(/[^a-zA-Z0-9]+/, "-", slug)
                tolower(slug)
            }

            if (status ~ /BUILT_AWAITING_REVIEW/ || status ~ /IN_GRILL/ || status ~ /building/) {
                next
            }

            printf "%d\t%s\t%s\t%s\t%s\n", numeric_score, slug, name, status, origin
        }
    }
    ' <<< "$NORMALIZED_BANK")

    if [ -z "$IDEAS" ]; then
        echo "No buildable ideas found in idea-bank.md."
        echo "$TODAY" > "$MARKER"
        exit 0
    fi

    # Sort by score descending, take top N
    IDEAS=$(echo "$IDEAS" | sort -t$'\t' -k1 -nr | head -n "$MAX_BUILDS")
fi

# ── Verify dossiers exist ──
MISSING=0
while IFS=$'\t' read -r score slug name status; do
    [ -z "$slug" ] && continue
    # Try multiple slug variants (bank slug vs file-on-disk slug may differ)
    DOSSIER_PATH="$HOME/vault/ventures/ideas/${slug}.md"
    if [ ! -f "$DOSSIER_PATH" ]; then
        echo "WARN: Dossier not found at ~/vault/ventures/ideas/${slug}.md"
        MISSING=$((MISSING + 1))
    fi
done <<< "$IDEAS"

if [ "$MISSING" -gt 0 ]; then
    echo "WARN: $MISSING dossier(s) missing. Cards will still be created — builder will handle."
fi

# ── Check existing kanban cards on target board — don't create duplicates ──
EXISTING=$(hermes kanban --board "$BOARD" list --json 2>/dev/null || echo "[]")

# Create kanban cards for each idea
CREATED=0

while IFS=$'\t' read -r score slug name status; do
    [ -z "$slug" ] && continue

    # Skip if already has a kanban card for this idea.
    # Match on slug in title or body, OR idea name in title.
    HAS_CARD=$(echo "$EXISTING" | python3 -c "
import json, sys
tasks = json.load(sys.stdin)
if isinstance(tasks, dict): tasks = tasks.get('tasks', [])
slug_l = '${slug}'.lower()
name_l = '''${name}'''.lower()
for t in tasks:
    title = (t.get('title','') or '').lower()
    body  = (t.get('body','') or '').lower()
    combined = title + ' ' + body
    if slug_l in combined or name_l in title:
        sys.exit(0)
sys.exit(1)
" 2>/dev/null && echo "yes" || echo "no")

    if [ "$HAS_CARD" = "yes" ]; then
        echo "SKIP: $name (already has a kanban card on $BOARD)"
        continue
    fi

    # ── Card A: Grill ──
    GRILL_TITLE="Grill: $name"

    GRILL_BODY="Score: ${score}/25 | Slug: ${slug}

A dossier exists at ~/vault/ventures/ideas/${slug}.md — read it first.

YOUR JOB — Grill ONLY. Do NOT build the prototype (that is the next card).

1. Grill with REAL PO using self-grill skill (REQUIRED — answer as founder).
   - CRITICAL: env -u HERMES_KANBAN_TASK before launching PO (see grill-rpc-ops skill)
   - Persist grill output to ~/projects/${slug}/context/ (per-branch files)
   - Run validation: bash ~/.hermes-teams/shared-skills/self-grill/scripts/validate-grill-output.sh ${slug}
2. Write grill decisions summary to ~/projects/${slug}/.context/grill/decisions.md
3. Copy dossier to ~/projects/${slug}/.context/dossier.md

Complete this card when grill validation passes.
Do NOT build the prototype — that is the next card.
NEVER put artifacts in ~/vault/ (Obsidian only). Everything goes in ~/projects/${slug}/."

    GRILL_RESULT=$(hermes kanban --board "$BOARD" create "$GRILL_TITLE" \
        --assignee builder \
        --body "$GRILL_BODY" \
        --json 2>/dev/null || echo "{}")

    GRILL_ID=$(echo "$GRILL_RESULT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('id',''))" 2>/dev/null || echo "")

    if [ -z "$GRILL_ID" ]; then
        echo "FAILED (grill card): $name"
        continue
    fi

    # ── Card B: Build (parent = grill card, waits for grill to complete) ──
    BUILD_TITLE="Build: $name"

    BUILD_BODY="Slug: ${slug}

The dossier and grill are DONE. Do NOT re-grill or re-research.
Read grill decisions at ~/projects/${slug}/context/
Read decisions summary at ~/projects/${slug}/.context/grill/decisions.md

YOUR JOB — Build ONLY. This card exists to isolate loop_engine in a fresh context.

1. Build prototype using loop_engine (MANDATORY — see venture-prototype skill).
   - Write verify script at /tmp/verify-${slug}.py BEFORE building
   - Parse every decision from ~/projects/${slug}/context/*.md
   - Use loop_engine with 2 phases: (1) build prototype, (2) write README
   - Each phase has a verifier gate — if verify fails, replan
   - Drop in ~/projects/${slug}/prototype/
2. Write README.md at ~/projects/${slug}/README.md (all 9 sections — see venture-prototype template).
3. Write review handoff (see prototype-review-handoff skill — portfolio entry + kanban comment).
   Update ~/vault/ventures/portfolio.md 'Awaiting Review' section.

This card's ONLY job is to build with loop_engine. Do not skip it.
NEVER put artifacts in ~/vault/ (Obsidian only). Everything goes in ~/projects/${slug}/."

    BUILD_RESULT=$(hermes kanban --board "$BOARD" create "$BUILD_TITLE" \
        --assignee builder \
        --body "$BUILD_BODY" \
        --parent "$GRILL_ID" \
        --json 2>/dev/null || echo "{}")

    BUILD_ID=$(echo "$BUILD_RESULT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('id',''))" 2>/dev/null || echo "")

    if [ -n "$BUILD_ID" ]; then
        CREATED=$((CREATED + 2))
        echo "CREATED [grill:$GRILL_ID] [build:$BUILD_ID]: [$score] $name"
    else
        CREATED=$((CREATED + 1))
        echo "PARTIAL [grill:$GRILL_ID] [build FAILED]: [$score] $name"
    fi

done <<< "$IDEAS"

# Update marker (only in default mode)
if [ "$FORCE" = false ] && [ -z "$SLUGS" ]; then
    echo "$(date -Iseconds)" > "$MARKER"
fi

echo ""
echo "=== Queue Builds Complete ==="
echo "Created: $CREATED kanban cards for builder"
echo "Board: $BOARD"
if [ "$FORCE" = false ] && [ -z "$SLUGS" ]; then
    echo "Marker updated: $MARKER"
fi
