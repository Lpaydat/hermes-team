# Intercom Test Patterns

Two test levels: broker routing (fast, no LLM) and live agent memory (slow, real LLM).

## 1. Broker Routing Test

Tests message delivery, session ID determinism, and topic isolation using two `IntercomClient` instances. No Hermes agent involved.

```python
import sys, os, time
sys.path.insert(0, os.path.expanduser("~/.hermes-teams/_shared/intercom"))
from broker import IntercomClient

SOCK = os.path.expanduser("~/.hermes-teams/_shared/intercom/.intercom.sock")

def make_client(team, profile):
    c = IntercomClient(sock_path=SOCK)
    c.connect()
    c.register(team, profile)
    return c

po = make_client("team-alpha", "product-owner")
tl = make_client("team-alpha", "tech-lead")

# Send a message (note: positional order is to_profile, topic, content)
po.send("tech-lead", "memory-test", "Hello, remember the code: 42")
time.sleep(0.5)
msg = tl.wait_for(lambda m: m.get("type") in ("send", "ask"), timeout=3)
print(f"Received: {msg.get('content')}")
print(f"Session ID: {msg.get('session_id')}")

# Same topic → same session ID (per direction)
# Different topic → different session ID
po.close()
tl.close()
```

### What this verifies
- Messages route between connected clients
- Same `(team, from, to, topic)` produces identical session IDs
- Different topics produce different session IDs
- Presence broadcast on connect/disconnect

### What this does NOT verify
- Whether the target agent actually remembers previous messages
- Whether offline session spawning works
- Whether `pre_llm_call` injection works in a live session

## 2. Live Agent Memory Test

Tests whether the offline delivery path (broker spawns a Hermes chat session) actually accumulates context across rounds. **This is the test that catches real bugs.**

```python
import sys, os, time
sys.path.insert(0, os.path.expanduser("~/.hermes-teams/_shared/intercom"))
from broker import IntercomClient

SOCK = os.path.expanduser("~/.hermes-teams/_shared/intercom/.intercom.sock")

po = IntercomClient(sock_path=SOCK)
po.connect()
po.register("team-alpha", "product-owner")

def round_trip(text, topic, round_num):
    print(f"\n--- ROUND {round_num}: topic='{topic}' ---")
    print(f"PO sends: {text}")

    result = po.send_message({
        "type": "send",
        "from_team": "team-alpha",
        "from_profile": "product-owner",
        "to_team": "",
        "to_profile": "tech-lead",
        "topic": topic,
        "content": {"text": text},   # MUST be dict, not bare string
        "spawn": True,
    }, timeout=320)

    sid = result.get("hermes_session_id", "N/A")
    print(f"Broker: type={result.get('type')}, session={sid}")
    if result.get("detail"):
        print(f"  detail: {str(result['detail'])[:120]}")
    return result

# Round 1: Set a secret
r1 = round_trip(
    "I'm testing intercom. Secret code: BANANA-7291. Confirm you got it.",
    "memory-test-live", 1)

# Round 2: Ask about the secret (same topic → should resume)
r2 = round_trip(
    "What was the secret code I gave you? Reply with just the code.",
    "memory-test-live", 2)

# Round 3: Different topic (should NOT remember round 1-2)
r3 = round_trip(
    "What's the secret code I gave you earlier?",
    "completely-different-topic", 3)

# ANALYSIS: Check if r1 and r2 share the same hermes_session_id
# If they do AND the agent recalls the code → memory works
# If they don't → session resumption is broken
```

### Interpreting results

| Symptom | Likely cause | Status |
|---------|-------------|--------|
| `spawn_failed: could not parse session_id` | Spawner reads stdout, but Hermes writes `session_id:` to stderr (see known-issues.md) | ✅ Fixed — spawner now scans stderr+stdout |
| Empty message delivered to agent | Content sent as string instead of `{"text": "..."}` dict | ✅ Fixed — spawner now handles string content |
| Agent has no memory between rounds | Session ID not captured (can't resume), so every spawn = fresh session | ✅ Fixed — follows from bug 1 fix |
| Same topic, different session IDs for A→B vs B→A | Directionality: from/to baked into hash positionally | ✅ Fixed — profiles now sorted alphabetically in hash |

**If you see `spawn_failed` again after a code change:** The spawner runs `hermes -p <profile> chat -q <query> -Q --pass-session-id`. Verify Hermes still outputs `session_id:` to stderr by running the manual resume test below. If Hermes changes its output format, the spawner's parsing logic needs updating.

### Verifying session resume works (without the broker)

To isolate whether `hermes --resume` itself works:

```bash
# Start a session, note the ID
hermes -p tech-lead chat -q "Remember the code: APPLE-1234" -Q --pass-session-id 2>&1
# Output: "session_id: 20260708_XXXXXX_XXXXXX\nAPPLE-1234 noted."
# Note: session_id goes to STDERR, agent response goes to STDOUT

# Resume it
hermes -p tech-lead chat -q "What code did I give you?" -Q --pass-session-id --resume 20260708_XXXXXX_XXXXXX 2>&1
# Should recall APPLE-1234
```

This confirms that `hermes --resume` works correctly — the bug was in the broker's spawner not capturing the session ID, not in Hermes itself.

## 3. Post-Fix Verification: Full Memory Test

After the three offline-delivery bugs were fixed (beads `intercom-2ai`, `intercom-iq2`, `intercom-9qf`), this test confirmed agents now remember across rounds. Run this after any change to the broker, spawner, or protocol to verify end-to-end memory still works.

### Prerequisites
1. Kill and restart the broker: `pkill -f "broker.server"; sleep 1; rm -f ~/.hermes-teams/_shared/intercom/.intercom.sock; cd ~/.hermes-teams/_shared/intercom && python3 -m broker.server`
2. Verify socket exists: `ls ~/.hermes-teams/_shared/intercom/.intercom.sock`

### The test: 5-round conversation
Run the live agent memory test from section 2 above with 5 rounds:
- Rounds 1–4: same topic, secret code + additional info
- Round 5: different topic (isolation check)

### Pass criteria
- **Session stability:** Rounds 1–4 all return the same `hermes_session_id` (resumed, not re-spawned)
- **Content memory:** Direct-resume the session and ask "what do you remember?" — agent should recall both the secret code and the additional info
- **Topic isolation:** Round 5 gets a different session ID

### How to verify content memory directly
```bash
# After the 5-round test, resume the session directly and ask what it remembers
hermes -p tech-lead chat -q "Final memory check. List EVERYTHING you remember from our conversation." -Q --pass-session-id --resume <session_id_from_rounds_1-4>
```

The agent should produce a structured response recalling all shared facts with full context.

### Pre-fix baseline (for comparison)
Before the fixes, the same test produced:
- Every round: `spawn_failed: could not parse session_id`
- Agent: "I don't have any previous message containing a secret code"
- Agent: "I have no record of a secret code or deployment"

The contrast between pre-fix and post-fix output is the clearest signal that the offline delivery path is functional.
