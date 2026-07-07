-- audit.sql — Post-test integrity check for cleanroom autonomous workflow test.
--
-- Any rows returned = manual intervention detected.
-- Usage: sqlite3 -json <kanban.db> < audit.sql
-- (with :test_start and :test_end replaced by epoch timestamps)
--
-- The key insight: dispatcher operations carry a run_id. Manual operations
-- (from PO's terminal or kanban tools) have run_id = NULL.

-- ═══ VERDICT ═══
SELECT '═══ AUDIT VERDICT ═══' AS header;

SELECT COUNT(*) AS manual_intervention_count,
    CASE WHEN COUNT(*) = 0
        THEN '✅ CLEAN — no manual intervention detected'
        ELSE '⚠️ CONTAMINATED — manual intervention detected'
    END AS verdict
FROM task_events
WHERE created_at >= :test_start AND created_at <= :test_end
  AND run_id IS NULL AND kind IN ('archived', 'unblocked', 'completed', 'blocked');

-- ═══ Manual card creation ═══
SELECT '─── Manual Card Creation ───' AS section;

SELECT t.id, substr(t.title, 1, 60), datetime(t.created_at, 'unixepoch'), t.created_by, t.idempotency_key
FROM tasks t
WHERE t.created_at >= :test_start AND t.created_at <= :test_end
  AND (t.idempotency_key IS NULL OR t.idempotency_key = '') AND t.created_by = 'user';

-- ═══ Manual state changes ═══
SELECT '─── Manual State Changes (no run_id) ───' AS section;

SELECT e.task_id, e.kind, datetime(e.created_at, 'unixepoch'), substr(e.payload, 1, 100)
FROM task_events e
WHERE e.created_at >= :test_start AND e.created_at <= :test_end
  AND e.run_id IS NULL AND e.kind IN ('archived', 'unblocked', 'completed', 'blocked')
ORDER BY e.created_at;

-- ═══ Full timeline ═══
SELECT '─── Full Task Timeline ───' AS section;

SELECT e.task_id, e.kind,
    CASE WHEN e.run_id IS NOT NULL THEN 'dispatcher' ELSE 'MANUAL' END AS source,
    datetime(e.created_at, 'unixepoch'), substr(e.payload, 1, 80)
FROM task_events e
WHERE e.created_at >= :test_start AND e.created_at <= :test_end
ORDER BY e.created_at LIMIT 200;
