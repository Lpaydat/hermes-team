#!/bin/bash
# Cron store backup — no_agent watchdog (zero tokens).
# Insurance against jobs.json loss (venture-builder's store vanished 2026-07-03
# despite atomic saves — cause unconfirmed). Keeps 7 rotations per profile.
# Silent when all good (watchdog pattern): output only on problems.

for jobs_file in "$HOME"/.hermes/profiles/*/cron/jobs.json; do
    [ -f "$jobs_file" ] || continue
    profile=$(basename "$(dirname "$(dirname "$jobs_file")")")
    dest_dir="$HOME/.hermes/profiles-backup/$profile/cron"
    mkdir -p "$dest_dir"
    if ! python3 -c "import json; json.load(open('$jobs_file'))" 2>/dev/null; then
        echo "WARNING: $profile/cron/jobs.json is corrupt JSON — NOT backing up over good copies."
        continue
    fi
    cp "$jobs_file" "$dest_dir/jobs.json.$(date +%Y%m%d%H%M)"
    cp "$jobs_file" "$dest_dir/jobs.json"
    ls -t "$dest_dir"/jobs.json.2* 2>/dev/null | tail -n +8 | xargs -r rm --
done

# Alert if any profile that has cron scripts/history lost its jobs.json
for cron_dir in "$HOME"/.hermes/profiles/*/cron; do
    profile=$(basename "$(dirname "$cron_dir")")
    if [ -d "$cron_dir/output" ] && [ ! -f "$cron_dir/jobs.json" ] && [ -f "$HOME/.hermes/profiles-backup/$profile/cron/jobs.json" ]; then
        echo "ALERT: $profile/cron/jobs.json is MISSING but a backup exists at ~/.hermes/profiles-backup/$profile/cron/jobs.json — restore it."
    fi
done
