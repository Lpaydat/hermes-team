# Livetest Quality Verification — How to Check Builder Output

After a livetest completes, don't just check card statuses. Verify the builder actually followed mandated processes.

## 1. Check loop_engine / kanban_chains usage

The venture-prototype skill mandates loop_engine (2-phase: develop → verify). In the builder pipeline livetest, the builder SKIPPED it — built prototypes directly in a single pass. The engine delivered the instruction correctly via the card body ("Build prototype using loop_engine (MANDATORY)"), but the builder ignored it.

**This is a build-skill enforcement gap, not an engine bug.**

To verify (using all 3 signals — see CRITICAL PITFALL below):

**CRITICAL PITFALL:** The builder can use EITHER `loop_engine` OR `kanban_chains` to create phased builds. Both produce child cards with verifier gates, but with DIFFERENT card titles. `loop_engine` creates `Loop: <goal>` cards; `kanban_chains` creates `root/build/verify/README` cards. If you only check for `Loop:%` titles, you miss `kanban_chains` usage entirely — this caused 42% false-negative rate in testing.

Check all 3 signals:

```sql
-- Signal 1: Loop:% card idempotency keys (loop_engine root cards)
SELECT id, idempotency_key FROM tasks WHERE title LIKE 'Loop:%';
-- Key format: loop:<parent_card_id>:<hash> → extract parent

-- Signal 2: heartbeat events mentioning either tool
SELECT task_id FROM task_events
WHERE kind = 'heartbeat'
AND (payload LIKE '%loop_engine%' OR payload LIKE '%kanban_chains%');

-- Signal 3: completion events mentioning either tool
SELECT task_id FROM task_events
WHERE kind = 'completed'
AND (payload LIKE '%loop_engine%' OR payload LIKE '%kanban_chains%');
```

Only matching `Loop:%` titles gives massive false negatives.

## 2. Count grill questions and decisions

**CRITICAL: The correct grep patterns are `^Q[0-9]` for Q&A rounds and `D[0-9]+:` or `Lock D[0-9]+` for decisions. Do NOT use `^## Q` or `^## D` — grill files use `Q1`, `Q2`, `Lock D15` patterns, NOT markdown headers. Using wrong patterns gives wildly low counts (2-11 instead of 26-157).**

```bash
for slug in <slugs>; do
  ctx=~/projects/$slug/context
  # CORRECT: Q&A rounds (Q1, Q2, Q3...)
  q=$(grep -c "^Q[0-9]" "$ctx"/*.md 2>/dev/null | awk -F: '{sum+=$NF} END {print sum+0}')
  # CORRECT: decisions (Lock D15, D23:, etc.)
  d=$(grep -oP "D\d+:" "$ctx"/*.md 2>/dev/null | wc -l)
  d2=$(grep -o "Lock D[0-9]*" "$ctx"/*.md 2>/dev/null | wc -l)
  d=$((d > d2 ? d : d2))
  b=$(ls "$ctx"/*.md 2>/dev/null | grep -v "_state" | wc -l)
  echo "  $slug: $q Q&A rounds | $d decisions | $b branches"
done
```

Observed range from builder livetest (7 prototypes, correct patterns):
- LeadPilot: 26 Q&A | 66 decisions | 8 branches
- OSINT Desk: 52 Q&A | 104 decisions | 5 branches
- ChatGPT Ads: 38 Q&A | 89 decisions | 11 branches
- Healthcare Prior-Auth: 78 Q&A | 166 decisions | 6 branches
- WhatsApp ReplyDeck: 53 Q&A | 104 decisions | 3 branches
- Dockerless CI: 157 Q&A | 232 decisions | 7 branches
- Indie Builder Dist: 83 Q&A | 169 decisions | 2 branches

This is comparable to the original queue-builds.sh pipeline (30-164 decisions per prototype per portfolio entries).

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
