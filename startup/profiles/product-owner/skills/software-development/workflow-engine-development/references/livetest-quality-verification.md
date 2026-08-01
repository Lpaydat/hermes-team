# Livetest Quality Verification — How to Check Builder Output

After a livetest completes, don't just check card statuses. Verify the builder actually followed mandated processes.

## 1. Check loop_engine / kanban_chains usage

The venture-prototype skill mandates loop_engine (2-phase: develop → verify). In the builder pipeline livetest, the builder SKIPPED it — built prototypes directly in a single pass. The engine delivered the instruction correctly via the card body ("Build prototype using loop_engine (MANDATORY)"), but the builder ignored it.

**This is a build-skill enforcement gap, not an engine bug.**

To verify:
```bash
# Search build card comments for loop_engine evidence
sqlite3 <board-db> "SELECT body FROM task_comments WHERE task_id='<build-card-id>'" \
  | grep -i "loop_engine\|kanban_chains"

# Check if loop_engine child cards were created on ANY board during the livetest
for db in ~/.hermes-teams/startup/kanban/boards/*/kanban.db; do
  sqlite3 "$db" "SELECT title FROM tasks WHERE (title LIKE '%loop%' \
    OR title LIKE '%develop%' OR title LIKE '%phase%') \
    AND created_at > <livetest-start-epoch>"
done
```

If zero results: the builder skipped the mandated loop_engine process.

## 2. Count grill questions and decisions

```bash
for slug in <slugs>; do
  ctx=~/projects/$slug/context
  q=$(grep -c "^## Q" "$ctx"/*.md 2>/dev/null | awk -F: '{sum+=$NF} END {print sum+0}')
  d=$(grep -c "^## D\|^### D\|^- D" "$ctx"/*.md 2>/dev/null | awk -F: '{sum+=$NF} END {print sum+0}')
  echo "  $slug: Questions=$q Decisions=$d"
done
```

Observed range from builder livetest:
- Shallow: 2-3 questions, 2-3 decisions (Indie Builder Dist, WhatsApp)
- Deep: 8-11 questions, 8-11 decisions (LeadPilot, ChatGPT Ads)

Note: portfolio entries may show much higher decision counts (30-164) than the context files — the builder may count decisions differently in the portfolio summary vs the branch files.

## 3. Verify portfolio entries

After build + handoff phases, check `~/vault/ventures/portfolio.md` for "Awaiting Review" entries:

```bash
grep -i "<slug>" ~/vault/ventures/portfolio.md
grep "Awaiting Review" ~/vault/ventures/portfolio.md
```

Each entry should have: name, score, grill decision count, description, prototype path, aha-moment instruction.

## 4. Check verify scripts

```bash
for slug in <slugs>; do
  ls -la /tmp/verify-$slug.py 2>/dev/null
done
```

Verify scripts should exist (builder creates them before building). But existence ≠ usage — check if they actually ran as part of a structured develop→verify loop.

## Livetest checklist

1. [ ] Parse ran (check engine log for `command_run` + `node_done`)
2. [ ] Cards dispatched with correct titles (`Grill: <name>` not `[grill] task`)
3. [ ] Agent gateway claimed cards (check `ready → running` transition)
4. [ ] Cards completed with real agent work (check card comments, not just status)
5. [ ] Engine detected completion and advanced (`node_done` in log)
6. [ ] Next phase dispatched independently (foreach subworkflow — no barrier)
7. [ ] loop_engine was used inside build cards (check for kanban_chains/loop_engine cards)
8. [ ] Portfolio entries created with full details
