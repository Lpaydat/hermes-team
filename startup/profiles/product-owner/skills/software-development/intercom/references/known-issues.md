# Intercom Known Issues

Bugs discovered through live testing on 2026-07-08. All three fixed and verified the same day via a live 5-round agent memory test. Kept as fix history + debugging reference.

## Bug 1: Spawner reads stdout but Hermes writes session_id to stderr

**Status:** ✅ FIXED (bead `intercom-2ai`, commit `1e9b158`)
**Severity:** Was critical — broke all offline delivery (every spawn = fresh session, no memory)
**Found:** 2026-07-08
**Beads:** `intercom-2ai` (P0)

**The bug:**
`broker/spawner.py` line 41 parses `result.stdout` for a `session_id:` line:
```python
for line in result.stdout.strip().split("\n"):
    if line.startswith("session_id:"):
        return line.split(":", 1)[1].strip()
```

But Hermes CLI writes `session_id:` to **stderr**, not stdout:
```
STDOUT: <agent response text>
STDERR: \nsession_id: 20260708_194501_63c697\n
```

**Impact:** The spawner can never capture the session ID. Without it, `--resume <session_id>` is never passed. Every offline message spawns a fresh Hermes session with zero history. Agent has no memory of previous messages on the same topic.

**Evidence:** Live test on 2026-07-08 — sent 4 rounds to tech-lead on topic "memory-test-live". Agent responded to each message but could never recall the secret code from the previous round. All 4 spawns failed with `spawn_failed: could not parse session_id`.

**Fix:** Changed `spawner.py` to scan combined stdout+stderr (commits `e32ddde` + `1e9b158`). Now captures session_id correctly. Verified: all 4 rounds on same topic produced session `20260708_225052_c52a9c` (resumed, not re-spawned).

---

## Bug 2: Content shape mismatch in offline delivery

**Status:** ✅ FIXED (bead `intercom-9qf`, commit `e32ddde`)
**Severity:** Was high — produced empty messages to the target agent
**Found:** 2026-07-08
**Beads:** `intercom-9qf` (P2)

**The bug:**
`broker/server.py` line 493 extracts message text:
```python
content = delivered.get("content")
text = content.get("text", "") if isinstance(content, dict) else ""
```

The `IntercomClient.send()` method's `content` parameter accepts arbitrary values. If a caller passes a bare string (e.g. `"Hello"`), `isinstance(content, dict)` is False → `text = ""` → empty query to the agent.

**Impact:** Messages sent with bare-string content produce empty queries. The target agent receives `[intercom] Message from ... (topic: ...):\n` with no body and responds confused about an "empty message".

**Evidence:** First test attempt on 2026-07-08 — tech-lead responded "there's no message body — it looks like an empty or test message" even though PO had sent a full message.

**Fix:** Added `elif isinstance(content, str): text = content` branch in `server.py _spawn_offline_session`. Now handles dict, string, and None/missing content.

---

## Bug 3: Session ID directionality — conversation splits into two threads

**Status:** ✅ FIXED (bead `intercom-iq2`, commit `7a2b98b`)
**Severity:** Was medium — broke bidirectional conversation continuity
**Found:** 2026-07-08
**Beads:** `intercom-iq2` (P1, was blocked by `intercom-2ai`)

**The bug:**
Session ID format: `intercom-{team}-{from_profile}-{to_profile}-{topic}-{hash8}`

The hash is computed over `to_team|from_profile|to_profile|topic`. Since `from_profile` and `to_profile` are positional, the conversation `PO→TL` and `TL→PO` on the same topic produce different hashes:

```
PO→TL:  intercom-team-alpha-product-owner-tech-lead-memory-test-3322944d
TL→PO:  intercom-team-alpha-tech-lead-product-owner-memory-test-ce446f42
```

**Impact:** Even after bugs 1 and 2 are fixed, a back-and-forth conversation between two profiles on the same topic would use two different session IDs — one for each direction. PO's messages to TL accumulate in one session; TL's messages to PO accumulate in a separate session. The agents can't see each other's full conversation history.

**Fix:** Changed `conversation_key()` in `protocol.py` to sort the two profiles alphabetically before hashing. `PO→TL` and `TL→PO` now produce the same hash. Session ID format changed from `{from}-{to}` to `{sorted_profile_1}-{sorted_profile_2}`. No existing sessions needed migration since all prior spawns had failed (Bug 1 prevented any session IDs from being captured).

---

## Bug 4: Bidirectional spawn — wrong profile session resume

**Status:** ✅ FIXED (bead `intercom-am3`, commit `406a42b`)
**Severity:** Was medium — broke bidirectional offline conversations
**Found:** 2026-07-08, 14-category edge case stress test
**Beads:** `intercom-am3` (P1, discovered-from `intercom-iq2`)

**The bug:**
The symmetric key fix (Bug 3) made `A→B` and `B→A` share the same `conversation_key`. But the broker's `_spawned_sessions` dict mapped that key to a single Hermes session ID — and a Hermes session belongs to **one profile only**.

**Sequence:**
1. `scout→TL` (both offline) → spawns Hermes session for **tech-lead** → stores `{conv_key: "session_abc"}`
2. `TL→scout` (same topic) → broker looks up `conv_key` → finds `"session_abc"` → tries to resume it for **scout** → fails: `"Session not found"` (that session belongs to tech-lead, not scout)

**Fix:** Changed `_spawned_sessions` from `dict[str, str]` to `dict[tuple[str, str], str]`, keyed by `(conv_key, normalize(to_profile))`. Each profile gets its own spawned Hermes session within the same conversation. `lookup_spawned_session` and `remember_spawned_session` both now take a `profile` parameter. Verified: `scout→TL` spawns `session_X` for tech-lead, `TL→scout` spawns `session_Y` for scout — both succeed independently.

**Scope:** Offline spawn path only. Online path (pre_llm_call injection) was never affected.

---

## Design Limitation: Async-only (no real-time push)

**Status:** Architectural (requires Hermes core change)
**Severity:** Expected limitation for v1

The `pre_llm_call` hook fires reactively — only when the agent is already processing a turn. If the target agent is idle (waiting for user input), incoming messages sit in the plugin's inbound buffer until the next turn fires. There is no hook to proactively trigger a new turn.

**What works:** Async messaging (send, go away, receive on next turn or next session start).
**What doesn't work:** Live side-by-side chat (both profiles active simultaneously, real-time back-and-forth).

**To fix:** Would need a new Hermes hook (e.g. `on_intercom_message`) that can trigger a new agent turn when a message arrives. This is a Hermes core change, not a plugin-level change.
