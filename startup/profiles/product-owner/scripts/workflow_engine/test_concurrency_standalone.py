"""Adversarial CONCURRENCY tests for the workflow engine.

Standalone runner: imports the FakeWorld harness from test_engine.py so these
tests exercise the *real* Engine/StateDB/kanban_adapter code, not a copy.
Run:  python3 test_concurrency_standalone.py
"""
import json
import sqlite3
import threading
import time
from pathlib import Path

# Import the shared harness + engine internals from the main test module.
import test_engine
from test_engine import FakeWorld, count_cards
from workflow_engine.runtime import (
    Engine, StateDB, NodeStatus, WorkflowInstance, NodeState,
)


def _make_second_engine(world):
    """Build a second Engine that shares the same templates dir + state DB."""
    eng = Engine(world.templates_dir)
    eng.state = StateDB(world.state_db_path)
    return eng


def _count_active_instances(state_db_path):
    conn = sqlite3.connect(str(state_db_path))
    try:
        return conn.execute(
            "SELECT count(*) FROM workflow_instances WHERE status = 'active'"
        ).fetchone()[0]
    finally:
        conn.close()


# --- TEST C1: two engines, same node, concurrent dispatch -> double card ---
def test_adv_concurrency_two_engines_double_dispatch():
    """Two Engine instances ticking concurrently against the same state DB
    must not create duplicate cards for one node.

    _dispatch_node does find_cards_by_idempotency_key (read) then create_card
    (write) in two separate connections with no transaction. Two concurrent
    ticks can both observe 'no existing card' and both create one.
    """
    world = FakeWorld()
    try:
        world.add_template({
            "id": "race", "name": "Race",
            "nodes": [{"id": "a", "profile": "qa", "skill": "live-testing",
                       "body_template": "x"}],
        })
        world.start("race")
        eng2 = _make_second_engine(world)

        # Force both threads past the idempotency-exists check before either
        # inserts, closing the TOCTOU window deterministically.
        barrier = threading.Barrier(2)
        real_create = world._fake_create_card

        def synced_create(board, title, assignee, body="", idempotency_key=None,
                          priority=None, workspace=None):
            barrier.wait(timeout=5)
            return real_create(board, title, assignee, body=body,
                               idempotency_key=idempotency_key,
                               priority=priority, workspace=workspace)

        import workflow_engine.runtime as rt
        rt.create_card = synced_create

        errors = []

        def run(eng):
            try:
                eng.tick()
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=run, args=(world.engine,))
        t2 = threading.Thread(target=run, args=(eng2,))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        assert not errors, f"threads raised unexpectedly: {errors}"
        n = count_cards(world.board_db)
        # CORRECT behavior: exactly 1 card. The check-then-create race lets
        # both engines through, so this FAILS and exposes the double dispatch.
        assert n == 1, (
            f"Two concurrent engines should create exactly 1 card for one node, "
            f"got {n} — check-then-create race allows double dispatch"
        )
    finally:
        world.cleanup()
    print("OK: test_adv_concurrency_two_engines_double_dispatch")


# --- TEST C2: concurrent read-modify-write on same node -> lost update ---
def test_adv_concurrency_concurrent_state_writes():
    """update_node_state is a non-atomic read-modify-write. Two concurrent
    updates that each omit a different field (one sets card_id, one sets
    output) both read the stale row and clobber each other: one field is lost.
    """
    world = FakeWorld()
    try:
        world.add_template({
            "id": "rmw", "name": "RMW",
            "nodes": [{"id": "a", "profile": "qa", "skill": "live-testing",
                       "body_template": "x"}],
        })
        inst_id = world.start("rmw")

        barrier = threading.Barrier(2)

        def rmw_update(set_card):
            conn = sqlite3.connect(str(world.state_db_path))
            try:
                row = conn.execute(
                    "SELECT card_id, output FROM node_states "
                    "WHERE instance_id = ? AND node_id = ?",
                    (inst_id, "a"),
                ).fetchone()
                cur_card = row[0] if row else None
                cur_output = json.loads(row[1]) if row and row[1] else {}
                barrier.wait(timeout=5)  # both hold stale values now
                if set_card:
                    cur_card = "card_1"
                    status = NodeStatus.DISPATCHED.value
                else:
                    cur_output = {"verdict": "PASS"}
                    status = NodeStatus.DONE.value
                conn.execute(
                    "UPDATE node_states SET status = ?, card_id = ?, output = ? "
                    "WHERE instance_id = ? AND node_id = ?",
                    (status, cur_card, json.dumps(cur_output), inst_id, "a"),
                )
                conn.commit()
            finally:
                conn.close()

        t1 = threading.Thread(target=rmw_update, args=(True,))
        t2 = threading.Thread(target=rmw_update, args=(False,))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        conn = sqlite3.connect(str(world.state_db_path))
        row = conn.execute(
            "SELECT card_id, output FROM node_states "
            "WHERE instance_id = ? AND node_id = ?", (inst_id, "a"),
        ).fetchone()
        conn.close()
        final_card = row[0]
        final_output = json.loads(row[1]) if row[1] else {}

        # CORRECT: both updates survive (card_id set AND verdict set).
        # Last-write-wins loses one, so this FAILS and exposes the lost update.
        assert final_card == "card_1" and final_output.get("verdict") == "PASS", (
            f"Concurrent read-modify-write lost an update: "
            f"card_id={final_card!r} output={final_output!r} — "
            f"update_node_state is not atomic"
        )
    finally:
        world.cleanup()
    print("OK: test_adv_concurrency_concurrent_state_writes")


# --- TEST C3: trigger dedup race -> duplicate workflow instances ---
def test_adv_concurrency_trigger_dedup_race():
    """Two engines detecting the same trigger card concurrently must start at
    most one workflow instance.

    _check_triggers calls _trigger_key_exists (read), then _start_from_trigger
    (creates instance), then _record_trigger_key (write) across three separate
    connections with no transaction. Two concurrent ticks can both see 'no key'
    and both start an instance.
    """
    world = FakeWorld()
    try:
        world.add_template({
            "id": "trig", "name": "Trig",
            "trigger": {"source": "card_completed",
                        "condition": {"assignee": "dev"}},
            "nodes": [{"id": "a", "profile": "qa", "skill": "live-testing",
                       "body_template": "x"}],
        })
        world.add_card("devcard", assignee="dev", status="done",
                       completed_at=int(time.time()), metadata={"k": 1})
        eng2 = _make_second_engine(world)

        barrier = threading.Barrier(2)
        orig_record = world.engine.state._record_trigger_key

        def synced_record(key):
            barrier.wait(timeout=5)
            orig_record(key)

        world.engine.state._record_trigger_key = synced_record
        eng2.state._record_trigger_key = synced_record

        errors = []

        def run(eng):
            try:
                eng.tick()
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=run, args=(world.engine,))
        t2 = threading.Thread(target=run, args=(eng2,))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        assert not errors, f"threads raised unexpectedly: {errors}"
        n = _count_active_instances(world.state_db_path)
        # CORRECT: one trigger card -> one instance. The race produces two, so
        # this FAILS and exposes duplicate workflow instances.
        assert n == 1, (
            f"One trigger card should start exactly one instance, got {n} — "
            f"trigger dedup check-then-act race creates duplicates"
        )
    finally:
        world.cleanup()
    print("OK: test_adv_concurrency_trigger_dedup_race")


# --- TEST C4: overlapping ticks on the same engine -> double dispatch ---
def test_adv_concurrency_overlapping_ticks():
    """Calling tick() on the same Engine from two threads concurrently is not
    safe: tick() snapshots active instances up front, then mutates state. With
    overlapping ticks, the second tick's stale snapshot lets it re-dispatch a
    node the first tick already dispatched.
    """
    world = FakeWorld()
    try:
        world.add_template({
            "id": "overlap", "name": "Overlap",
            "nodes": [{"id": "a", "profile": "qa", "skill": "live-testing",
                       "body_template": "x"}],
        })
        world.start("overlap")

        barrier = threading.Barrier(2)
        real_create = world._fake_create_card

        def synced_create(board, title, assignee, body="", idempotency_key=None,
                          priority=None, workspace=None):
            barrier.wait(timeout=5)
            return real_create(board, title, assignee, body=body,
                               idempotency_key=idempotency_key,
                               priority=priority, workspace=workspace)

        import workflow_engine.runtime as rt
        rt.create_card = synced_create

        errors = []

        def run():
            try:
                world.tick()
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=run)
        t2 = threading.Thread(target=run)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        assert not errors, f"overlapping ticks raised unexpectedly: {errors}"
        n = count_cards(world.board_db)
        # CORRECT: tick() must be reentrant — one node, one card. The stale
        # snapshot produces two, so this FAILS.
        assert n == 1, (
            f"Overlapping ticks on one engine should create 1 card, got {n} — "
            f"tick() snapshots then mutates with no locking, double dispatch"
        )
    finally:
        world.cleanup()
    print("OK: test_adv_concurrency_overlapping_ticks")


# --- TEST C5: state DB locked by another writer -> tick crashes ---
def test_adv_concurrency_db_locked():
    """If the state DB is locked by another writer, the engine's tick should
    degrade gracefully (skip/log), not raise and kill the tick loop. StateDB
    opens a fresh connection per call and never catches sqlite3.OperationalError,
    so a 'database is locked' error propagates straight out of tick().
    """
    world = FakeWorld()
    import workflow_engine.runtime as rt
    orig_connect = rt.sqlite3.connect
    try:
        world.add_template({
            "id": "locked", "name": "Locked",
            "nodes": [{"id": "a", "profile": "qa", "skill": "live-testing",
                       "body_template": "x"}],
        })
        world.start("locked")

        def locked_connect(*a, **k):
            raise sqlite3.OperationalError("database is locked")

        rt.sqlite3.connect = locked_connect

        crashed = False
        try:
            world.tick()
        except sqlite3.OperationalError:
            crashed = True
        except Exception:
            crashed = True

        # CORRECT: a locked DB must not crash the tick. StateDB has no error
        # handling, so this FAILS (crashed == True).
        assert not crashed, (
            "Engine crashed on 'database is locked' — StateDB/tick have no "
            "OperationalError handling, a contended DB kills the tick loop"
        )
    finally:
        rt.sqlite3.connect = orig_connect
        world.cleanup()
    print("OK: test_adv_concurrency_db_locked")


# --- TEST C6: partial write — instance created, trigger key lost -> dup ---
def test_adv_concurrency_partial_write_trigger_key():
    """If the engine creates a workflow instance but the trigger dedup key is
    never persisted (crash between create_instance and _record_trigger_key),
    the next tick starts a DUPLICATE instance for the same trigger card. The
    create-then-record sequence is not atomic.
    """
    world = FakeWorld()
    try:
        world.add_template({
            "id": "partial", "name": "Partial",
            "trigger": {"source": "card_completed",
                        "condition": {"assignee": "dev"}},
            "nodes": [{"id": "a", "profile": "qa", "skill": "live-testing",
                       "body_template": "x"}],
        })
        world.add_card("devcard", assignee="dev", status="done",
                       completed_at=int(time.time()), metadata={"k": 1})

        # Simulate the dedup-key write being lost (partial write / crash).
        world.engine.state._record_trigger_key = lambda key: None

        world.tick()   # instance created, key NOT persisted
        world.tick()   # key absent -> engine re-triggers the same card

        n = _count_active_instances(world.state_db_path)
        # CORRECT: one trigger card -> at most one instance even after a lost
        # dedup write. The non-atomic create-then-record produces two, so this
        # FAILS.
        assert n == 1, (
            f"Lost trigger-key write caused duplicate instances: {n} — "
            f"create_instance and _record_trigger_key are not atomic"
        )
    finally:
        world.cleanup()
    print("OK: test_adv_concurrency_partial_write_trigger_key")


if __name__ == "__main__":
    tests = [
        test_adv_concurrency_two_engines_double_dispatch,
        test_adv_concurrency_concurrent_state_writes,
        test_adv_concurrency_trigger_dedup_race,
        test_adv_concurrency_overlapping_ticks,
        test_adv_concurrency_db_locked,
        test_adv_concurrency_partial_write_trigger_key,
    ]
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"FAIL: {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR: {test.__name__}: {type(e).__name__}: {e}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed, {len(tests)} total")
    import sys
    sys.exit(0 if failed == 0 else 1)
