# Unhappy-path / error-handling tests

A distinct test class that sits between happy-path tests (everything goes right)
and adversarial bug-finders (try to break the engine). Each test verifies the
engine **handles a known error condition gracefully**: no crash, returns a list
(not raises), reports the condition in actions, and doesn't leave zombies.

## Test posture (how these differ from adversarial tests)

| Test class | Goal | Pass when engine is... | Assertion style |
|---|---|---|---|
| Happy-path | Verify correct forward progress | correct | "DISPATCHED / DONE / COMPLETE in actions" |
| **Unhappy-path** | Verify graceful handling of a *known* error condition | **hardened** | "no exception, returns list, WARNING/SKIP reported" |
| Adversarial | *Find* bugs by stressing seams | buggy (test FAILS = bug report) | "BUG: ... — fix the engine, then test becomes guard" |

Unhappy-path tests **should be all-green.** If one fails, either the engine
has a genuine crash-on-error bug, or the assertion encoded behavior the engine
has since changed — triage the same way as the dual-nature adversarial tests.

## The 10-condition error surface (reusable checklist)

When asked to write unhappy-path tests for the engine, cover at least these.
Each is a distinct failure mode in the engine's external surface.

1. **Nonexistent board** — `start_manual(board="no-such-board")`, then tick.
   Engine's deleted-board guard (`board_db_path().exists()`) should detect the
   missing DB, mark the instance complete, and NOT zombie-cycle. Assert 0
   active instances after the tick.
2. **Card-creation failure** — monkey-patch `runtime.create_card` to return
   `(False, "database is locked")`. Tick should report FAILED, not crash. No
   card created. Restore the function and tick again → dispatch succeeds
   (retry works because the node stayed PENDING).
3. **Missing/unknown profile** — node `profile: "ghost-profile-xyz"`. Engine
   doesn't validate profile existence, so the card dispatches normally. Across
   multiple ticks while the card stays `todo`, engine should wait patiently —
   no error, no spam, instance stays active. (This is correct behavior: the
   dispatcher's job to claim, not the engine's.)
4. **Error card status** — set a dispatched card's status to `gave_up` /
   `timed_out` (neither `done` nor `blocked`). Engine's phase-1 switch has no
   case for it → falls through to the `("todo","ready","running")` WARNING
   branch. Node stays DISPATCHED (not DONE), downstream nodes don't dispatch.
   No crash. Assert node state != "done" and downstream card not created.
5. **Board schema mismatch** — create `kanban.db` with an unrelated table but
   NO `tasks` table (the DB exists, schema is wrong). The engine's board guard
   sees the file exists so doesn't skip; queries fail with `no such table`.
   The outer `try/except` in `tick()` catches it → returns
   `["ERROR tick: no such table: tasks"]`. Assert the tick returns a list
   (graceful), not an unhandled traceback.
6. **Nonexistent skill** — node `skill: "this-skill-does-not-exist"`. Engine
   doesn't validate skills (correct — that's the agent's problem). Card
   dispatches with the skill name baked into the title. Assert DISPATCHED +
   card count == 1.
7. **Empty / all-unresolved body template** — `body_template: ""` or
   `"${nodes.x.output.y} ${trigger.z}"`. `resolve_template` strips unresolved
   vars to `""`. `create_card` skips `--body` when body is falsy. Card still
   creates and dispatches. Assert DISPATCHED for both the empty and the
   all-unresolved cases.
8. **Empty-string profile** — `profile: ""`. Engine doesn't crash. Card either
   dispatches with empty assignee or the adapter rejects it — either way no
   unhandled exception. Assert tick returns a list.
9. **Spam tick (no duplicates)** — dispatch a node, set its card to `running`,
   then call `tick()` 10 more times. Idempotency key (`wf:<inst>:<node>`) +
   `find_cards_by_idempotency_key` pre-check prevent re-dispatch. Assert card
   count stays at 1 and instance stays active. Downstream nodes must NOT
   dispatch while the dep card is still running.
10. **Out-of-order completion** — diamond/fan-in: `a` and `b` both feed `c`.
    Complete `b` before `a`. After `b` done, `c` must NOT dispatch (a not done).
    After `a` done, `c` dispatches. Assert the dependency gate holds regardless
    of completion order, and the workflow completes once all deps are done.

## Conventions for these tests

- **Reuse the FakeWorld fixture** — same monkey-patches (`KANBAN_HOME`,
  `runtime.create_card`), same fake-board schema, same `set_card_status` helper.
  A separate `test_unhappy.py` can re-define FakeWorld or import it from
  `test_engine.py`; importing avoids drift.
- **Every test ends with `world.cleanup()`** to restore monkey-patches (no
  cross-test bleed, important when the suite runs in one process).
- **Assert on `tick()` return value shape, not on logging.** `tick()` returns a
  `list[str]`; a crash raises. `assert isinstance(actions, list)` is the
  primary "didn't crash" guard. Secondary: assert specific WARNING/FAILED/SKIP
  substrings appear in the returned actions.
- **For the error-status test, read node state from the state DB directly** —
  `SELECT status FROM node_states WHERE node_id = 'a'` — to prove the node did
  not advance to DONE, which is the correctness signal.
- **The schema-mismatch test legitimately produces a STDERR log line**
  (`tick failed: no such table: tasks`). That is the engine logging inside its
  `try/except`, not a crash. The test passes; treat the STDERR as expected
  evidence, not a failure.
