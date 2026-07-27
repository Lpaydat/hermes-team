# E2E Pipeline Verification Recipe

Step-by-step recipe for verifying the full pipeline v3 from config reload through card creation to dispatcher pickup. Run this after any pipeline change (config, scripts, skills).

## Step 0: Gateway restart (if config.yaml changed)

```bash
# Check the config value on disk
grep -i 'max_iterations' ~/.hermes-teams/startup/config.yaml

# Check gateway uptime — if started before the config change, it has stale cached values
hermes gateway status --profile builder | head -5

# Restart to pick up new config
hermes gateway restart --profile builder

# Verify it's fresh
hermes gateway status --profile builder | grep 'Active:'
```

## Step 1: Run queue-builds.sh

```bash
# Remove cooldown marker for testing
rm -f ~/vault/ventures/.last-queue

# Run the queue script
cd ~/.hermes-teams/startup/profiles/builder/scripts && bash queue-builds.sh
```

Expected: 10 `CREATED [t_xxx]` lines, sorted by score descending.

## Step 2: Verify cards on board

```bash
# DO NOT use --json on the full board (1.8M+ chars)
hermes kanban --board hermes-hq list 2>&1 | grep -i 'Build prototype'
```

Expected: 10 lines — first card `running` or `ready`, rest `todo`.

## Step 3: Verify parent-child chaining

```bash
# Show the first card — should have children
hermes kanban --board hermes-hq show <first-card-id> 2>&1 | grep -E 'parents|children'

# Show the second card — should have parents pointing to first
hermes kanban --board hermes-hq show <second-card-id> 2>&1 | grep -E 'parents|children'
```

Expected: First card has `children: <second-id>`, second card has `parents: <first-id>` and `children: <third-id>`.

## Step 4: Verify idempotency (dedup)

```bash
rm -f ~/vault/ventures/.last-queue
cd ~/.hermes-teams/startup/profiles/builder/scripts && bash queue-builds.sh
# Should output: Created: 0 kanban cards for builder (all SKIP)
```

## Step 5: Verify dispatcher pickup

```bash
# Check that the first card was claimed and is running
hermes kanban --board hermes-hq show <first-card-id> 2>&1 | grep -E 'status|spawned|heartbeat|run'
```

Expected: `status: running`, with heartbeat events.

## Step 6: Run the verification script

```bash
bash ~/.hermes-teams/startup/profiles/builder/skills/software-development/pipeline-operations/scripts/verify-queue-builds.sh
```

Expected: `ALL CHECKS PASSED` (5/5).

## Known gotchas

- **kanban_list/kanban_show tools default to `default` board.** Cards on `hermes-hq` appear missing. Use CLI with `--board hermes-hq` explicitly.
- **`hermes kanban --board hermes-hq list --json`** on a 190-task board produces 1.8M+ chars. Never pipe to a tool without filtering first.
- **`eval` with multi-line --body** destroys the argument (word-splitting). The queue-builds.sh script was fixed to pass args directly.
- **`.last-queue` marker** has a 6h cooldown. Remove it to force re-runs during testing.
