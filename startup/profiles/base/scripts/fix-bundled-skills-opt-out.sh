#!/usr/bin/env bash
# fix-bundled-skills-opt-out.sh
#
# Re-applies the bundled-skills opt-out after a fresh install, `hermes update`,
# or profile import on a new machine. This is the portable fix for the recurring
# regression where bundled skills (dogfood, polymarket, etc.) get re-seeded
# into ~/.hermes/skills/ and cloned profiles despite per-profile opt-out markers.
#
# ROOT CAUSE: The global ~/.hermes/ dir (the "default" profile) has no
# .no-bundled-skills marker, so sync_skills() re-seeds it on every update.
# Cloned profiles inherit the polluted skills/ dir before their own marker
# can protect them.
#
# This script:
#   1. Writes the global marker at ~/.hermes/.no-bundled-skills
#   2. Ensures every named profile under ~/.hermes/profiles/ has its marker
#   3. Cleans any manifest-tracked bundled skills from the global dir
#   4. Cleans any manifest-tracked bundled skills from each profile
#
# Usage:
#   bash ~/.hermes/profiles/base/scripts/fix-bundled-skills-opt-out.sh
#
# Safe to re-run (idempotent). User-installed and hub skills are never touched.

set -euo pipefail

HERMES_ROOT="${HERMES_HOME:-$HOME/.hermes}"

# If HERMES_HOME points inside profiles/, use the real root for the global marker
if [[ "$HERMES_ROOT" == *"/profiles/"* ]]; then
    HERMES_ROOT="$HOME/.hermes"
fi

echo "=== Bundled-skills opt-out restoration ==="
echo "Hermes root: $HERMES_ROOT"
echo ""

# --- Layer 1: Global marker ---
GLOBAL_MARKER="$HERMES_ROOT/.no-bundled-skills"
if [[ ! -f "$GLOBAL_MARKER" ]]; then
    echo "→ Writing global marker at $GLOBAL_MARKER"
    cat > "$GLOBAL_MARKER" << 'MARKER'
This profile (the default/global ~/.hermes) opted out of bundled-skill
seeding. The named profiles under ~/.hermes/profiles/ each manage their own
opt-out markers. Delete this file to re-enable global sync on the next
`hermes update`.
MARKER
else
    echo "✓ Global marker already present"
fi

# --- Layer 2: Per-profile markers ---
PROFILES_DIR="$HERMES_ROOT/profiles"
if [[ -d "$PROFILES_DIR" ]]; then
    for profile_dir in "$PROFILES_DIR"/*/; do
        [[ -d "$profile_dir" ]] || continue
        pname=$(basename "$profile_dir")
        marker="$profile_dir/.no-bundled-skills"
        if [[ ! -f "$marker" ]]; then
            echo "→ Writing marker for profile: $pname"
            cat > "$marker" << 'MARKER'
Bundled-skill seeding disabled per-profile.
Delete this file to re-enable sync on the next `hermes update`.
MARKER
        else
            echo "✓ Profile '$pname' already opted out"
        fi
    done
fi

# --- Layer 3: Clean pollution from global dir ---
echo ""
echo "=== Cleaning bundled skills from global dir ==="
if command -v hermes &>/dev/null; then
    # Use the official tool — it only removes manifest-tracked + unmodified skills
    HERMES_HOME="$HERMES_ROOT" hermes skills opt-out --remove --yes 2>&1 | grep -E "^(Removed|Will remove|Already)" || true
else
    echo "⚠ hermes CLI not found — skipping automated cleanup"
    echo "  Run manually: HERMES_HOME=$HERMES_ROOT hermes skills opt-out --remove --yes"
fi

# --- Layer 4: Clean pollution from each profile ---
if [[ -d "$PROFILES_DIR" ]]; then
    for profile_dir in "$PROFILES_DIR"/*/; do
        [[ -d "$profile_dir" ]] || continue
        pname=$(basename "$profile_dir")
        if [[ -f "$profile_dir/.no-bundled-skills" ]]; then
            echo "=== Cleaning profile: $pname ==="
            if command -v hermes &>/dev/null; then
                HERMES_HOME="$profile_dir" hermes skills opt-out --remove --yes 2>&1 | grep -E "^(Removed|Will remove|Already)" || true
            fi
        fi
    done
fi

echo ""
echo "=== Done. Verification: ==="
echo "Global marker: $( [[ -f "$GLOBAL_MARKER" ]] && echo 'present ✓' || echo 'MISSING ✗' )"
if [[ -d "$PROFILES_DIR" ]]; then
    for profile_dir in "$PROFILES_DIR"/*/; do
        [[ -d "$profile_dir" ]] || continue
        pname=$(basename "$profile_dir")
        marker="$profile_dir/.no-bundled-skills"
        status=$( [[ -f "$marker" ]] && echo 'present ✓' || echo 'MISSING ✗' )
        dogfood=$( [[ -d "$profile_dir/skills/dogfood" ]] && echo 'PRESENT ⚠' || echo 'clean ✓' )
        echo "  $pname: marker=$status | dogfood=$dogfood"
    done
fi
