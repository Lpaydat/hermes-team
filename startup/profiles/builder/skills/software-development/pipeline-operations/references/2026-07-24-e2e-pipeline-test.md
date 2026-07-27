# E2E Pipeline Test — 2026-07-24

Full 10-card pipeline v3 run, start to finish. All 10 cards completed in ~4 hours.

## Fixes Applied During Test

### 1. queue-builds.sh eval quoting bug
- **Symptom:** Every `hermes kanban create` call failed silently — body text split on spaces by `eval`
- **Fix:** Replaced `eval hermes kanban ... $ARGS` with direct invocation passing `--body "$BODY"` as a single quoted argument
- **File:** `startup/profiles/builder/scripts/queue-builds.sh`

### 2. Self-grill blocks kanban card (needs_input)
- **Symptom:** Builder calls `kanban_block(needs_input)` when PO asks a question during self-grill, even though builder IS the founder. Dispatcher reclaims after ~1h stale timeout, costing a full cycle.
- **Fix:** Added "NEVER block the kanban card during self-grill" section to `shared-skills/self-grill/SKILL.md`
- **Impact:** Cards 1-5 hit this bug (each lost ~1h to reclaim). Cards 6-10 loaded the fixed skill and ran clean.

### 3. PO launch hangs without timeout
- **Symptom:** Bare `hermes -p product-owner --cli` produces no stdout for 300s+. Builder wastes cycles polling.
- **Fix:** Updated `grill-rpc-ops/SKILL.md` PO Launch Recipe to use `timeout 600 hermes -p product-owner --cli 2>&1 | tail -80`
- **Note:** glm-5.2 thinking alone can take 300s+. Timeout must be >=600s.

## Findings (Not Fixed Yet)

### 4. Prototype deliverable inconsistency
Only 2/10 prototypes shipped with README.md. 8 had index.html + grill-decisions.md but no review-ready docs. The kanban card body and self-grill skill should explicitly require README.md as a deliverable.

### 5. Dispatcher reclaim overhead
Each reclaim cycle adds ~10 min (re-read context, re-load skills, find grill state). Cards that blocked 2-3 times during grill took 30+ min longer than necessary.

### 6. Slug mismatch
LeadPilot created two prototype dirs: `leadpilot-ai-local-smb-lead-gen` (from idea-bank.md slug) and `leadpilot-local-smb-lead-gen` (from dossier filename). Slugs should be normalized between idea-bank.md and dossier paths.

## Pipeline Timing

| Card | Time | Notes |
|------|------|-------|
| LeadPilot | ~1h7m | Blocked 2x during grill, reclaimed twice |
| OSINT Desk | ~30m | Clean run |
| SMB Bookkeeping | ~30m | Clean run |
| WhatsApp Inbox | ~55m | Blocked 1x, reclaimed |
| Indie Distribution | ~1h | Blocked 2x, reclaimed |
| Dockerless CI | ~30m | Clean run |
| AI Interview | ~30m | Clean run |
| Scraper Micropay | ~30m | Clean run |
| Privacy-First | ~30m | Clean run |
| FlowGuard | ~30m | Clean run |

Total: ~4h (23:16 to 03:14)

## Verified Working

- queue-builds.sh: parses idea-bank.md, creates chained cards, dedup works
- Sequential chain: parent-child auto-promotion on completion
- Builder session: grill → build → portfolio update → card complete
- Gateway restart: max_iterations=999 applied
- Skill fixes: take effect on next builder session (after reclaim or new card)
